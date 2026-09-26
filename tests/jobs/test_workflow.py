"""Behavioral tests for staged local workflow execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile

import pytest

import femora as fm


def write_value(ctx):
    value = ctx.inputs["value"]
    (ctx.output_dir / "value.txt").write_text(str(value), encoding="ascii")
    return value


def double_previous(ctx):
    value = ctx.result("first", "write") * 2
    (ctx.output_dir / "double.txt").write_text(str(value), encoding="ascii")
    return value


def read_same_stage(ctx):
    return ctx.result("sequential", "write") + 1


def record_interval(ctx):
    started = time.monotonic()
    time.sleep(0.7)
    return (started, time.monotonic())


def fail(ctx):
    (ctx.output_dir / "partial.txt").write_text("partial", encoding="ascii")
    raise RuntimeError("deliberate failure")


def test_stages_pass_results_and_select_artifacts(tmp_path: Path) -> None:
    workflow = fm.Workflow("simple")
    workflow.add("first", tasks=[fm.tasks.Python("write", write_value)])
    workflow.add("second", tasks=[fm.tasks.Python("double", double_previous)])
    workflow.outputs("second/**/*.txt")

    run = fm.execute(workflow, workspace=tmp_path, inputs={"value": 7})

    assert run.result("second", "double") == 14
    assert [path.relative_to(tmp_path) for path in run.artifacts] == [
        Path("second/double/double.txt")
    ]
    assert json.loads(run.manifest.read_text(encoding="utf-8"))["stages"]["second"]["double"]["status"] == "finished"


def test_sequential_tasks_see_prior_results_in_same_stage(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add(
        "sequential",
        tasks=[fm.tasks.Python("write", write_value), fm.tasks.Python("read", read_same_stage)],
    )

    run = fm.execute(workflow, workspace=tmp_path, inputs={"value": 2})

    assert run.result("sequential", "read") == 3


def test_parallel_stage_runs_tasks_concurrently(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add(
        "parallel",
        parallel=True,
        tasks=[fm.tasks.Python("a", record_interval), fm.tasks.Python("b", record_interval)],
    )

    run = fm.execute(workflow, workspace=tmp_path, cores=2)
    a = run.result("parallel", "a")
    b = run.result("parallel", "b")

    assert max(a[0], b[0]) < min(a[1], b[1])


def test_parallel_stage_rejects_oversubscription(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add(
        "parallel",
        parallel=True,
        tasks=[fm.tasks.Python("a", write_value, cores=2), fm.tasks.Python("b", write_value, cores=2)],
    )

    with pytest.raises(fm.jobs.WorkflowExecutionError, match="requires 4 cores"):
        fm.execute(workflow, workspace=tmp_path, cores=3)


def test_failure_keeps_partial_output_and_manifest(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add("broken", tasks=[fm.tasks.Python("failure", fail)])
    workflow.outputs("broken/**/*.txt")

    with pytest.raises(fm.jobs.WorkflowExecutionError, match="stage 'broken' failed") as error:
        fm.execute(workflow, workspace=tmp_path)

    assert [path.name for path in error.value.run.artifacts] == ["partial.txt"]
    manifest = json.loads(error.value.run.manifest.read_text(encoding="utf-8"))
    assert manifest["stages"]["broken"]["failure"]["status"] == "failed"


def test_output_patterns_cannot_escape_workspace() -> None:
    with pytest.raises(ValueError, match="relative"):
        fm.Workflow().outputs("../private/**")
    with pytest.raises(ValueError, match="relative"):
        fm.Workflow().outputs("C:private/**")


def test_command_runs_in_task_directory_and_keeps_log(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add(
        "commands",
        tasks=[
            fm.tasks.Command(
                "write",
                [
                    sys.executable,
                    "-c",
                    "import os; from pathlib import Path; "
                    "Path('result.txt').write_text(os.environ['WORKFLOW_TEST_VALUE'])",
                ],
                env={"WORKFLOW_TEST_VALUE": "hello"},
            )
        ],
    )
    workflow.outputs("commands/**/*.txt", "commands/**/stdout.log")

    run = fm.execute(workflow, workspace=tmp_path)

    assert (run.result("commands", "write").output_dir / "result.txt").read_text() == "hello"
    assert {path.name for path in run.artifacts} == {"result.txt", "stdout.log"}


def test_failed_command_keeps_log_and_stops_workflow(tmp_path: Path) -> None:
    workflow = fm.Workflow()
    workflow.add(
        "fail",
        tasks=[fm.tasks.Command("run", [sys.executable, "-c", "print('bad'); exit(7)"])],
    )
    workflow.add("later", tasks=[fm.tasks.Python("write", write_value)])
    workflow.outputs("fail/**/stdout.log")

    with pytest.raises(fm.jobs.WorkflowExecutionError, match="stage 'fail' failed") as error:
        fm.execute(workflow, workspace=tmp_path)

    assert "bad" in error.value.run.artifacts[0].read_text()
    assert "later" not in error.value.run.results


def test_local_opensees_rejects_multiple_ranks(tmp_path: Path) -> None:
    workflow = fm.Workflow().add(
        "solve", tasks=[fm.tasks.OpenSees("model", "model.tcl", ranks=2)]
    )

    with pytest.raises(fm.jobs.WorkflowExecutionError, match="multi-rank OpenSees"):
        fm.execute(workflow, workspace=tmp_path, cores=2)


def test_opensees_requires_workspace_relative_script(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative"):
        fm.tasks.OpenSees("model", "../model.tcl")
    workflow = fm.Workflow().add(
        "solve", tasks=[fm.tasks.OpenSees("model", "missing.tcl")]
    )

    with pytest.raises(fm.jobs.WorkflowExecutionError, match="stage 'solve' failed") as error:
        fm.execute(workflow, workspace=tmp_path)
    assert "script was not found" in json.loads(error.value.run.manifest.read_text())["stages"]["solve"]["model"]["error"]


def test_bundle_replays_source_inputs_and_data(tmp_path: Path) -> None:
    source = tmp_path / "small_workflow.py"
    source.write_text(
        "import femora as fm\n"
        "def make(ctx):\n"
        "    value = int((ctx.workspace / 'input.txt').read_text()) + ctx.inputs['offset']\n"
        "    (ctx.output_dir / 'answer.txt').write_text(str(value))\n"
        "    return value\n"
        "def build_workflow(inputs):\n"
        "    return fm.Workflow('bundled').add('calculate', tasks=[fm.tasks.Python(inputs['task_name'], make)]).outputs('calculate/**/*.txt')\n",
        encoding="ascii",
    )
    (tmp_path / "input.txt").write_text("5", encoding="ascii")
    package = fm.jobs.bundle(
        source=source,
        destination=tmp_path / "workflow.zip",
        inputs={"offset": 3, "task_name": "make"},
        files=["input.txt"],
    )

    run = fm.jobs.replay(package, workspace=tmp_path / "new_workspace")

    assert run.result("calculate", "make") == 8
    assert (run.workspace / "input.txt").read_text() == "5"
    assert [path.name for path in run.artifacts] == ["answer.txt"]
    with pytest.raises(FileExistsError, match="workspace must be empty"):
        fm.jobs.replay(package, workspace=run.workspace)


def test_bundle_rejects_escaping_data_path_and_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    source.write_text("def build_workflow(): pass\n", encoding="ascii")
    with pytest.raises(ValueError, match="relative"):
        fm.jobs.bundle(
            source=source, destination=tmp_path / "bad.zip", inputs={}, files=["../secret.txt"]
        )

    package = fm.jobs.bundle(source=source, destination=tmp_path / "workflow.zip", inputs={})
    with ZipFile(package) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents["workflow.py"] = b"def build_workflow(): return 1\n"
    with ZipFile(package, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match="checksum"):
        fm.jobs.replay(package, workspace=tmp_path / "new_workspace")


@pytest.mark.skipif(not os.environ.get("FEMORA_OPENSEES"), reason="requires a local OpenSees executable")
def test_tiny_opensees_workflow(tmp_path: Path) -> None:
    from examples.workflows.tiny_opensees import build_workflow

    run = fm.execute(
        build_workflow(),
        workspace=tmp_path,
        inputs={"moduli": {"soft": 2.0e9, "stiff": 4.0e9}},
        cores=2,
    )

    assert run.result("compare", "summary") == pytest.approx(
        {"soft": -1.0 / 600.0, "stiff": -1.0 / 1200.0}, rel=0.01
    )
    assert (tmp_path / "compare" / "summary" / "comparison.txt").exists()
    assert len(run.artifacts) == 7
    assert {path.name for path in run.artifacts} == {
        "soft.tcl", "stiff.tcl", "tip_displacement.out", "stdout.log", "comparison.txt"
    }

    package = fm.jobs.bundle(
        source=Path(__file__).parents[2] / "examples/workflows/tiny_opensees.py",
        destination=tmp_path / "tiny.zip",
        inputs={"moduli": {"soft": 2.0e9, "stiff": 4.0e9}},
    )
    replayed = fm.jobs.replay(package, workspace=tmp_path / "replayed", cores=2)
    assert replayed.result("compare", "summary") == pytest.approx(
        run.result("compare", "summary")
    )
