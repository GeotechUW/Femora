"""Test TACC launch planning without access to a TACC allocation."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import femora as fm
from femora.jobs import backends, runner
from femora.jobs.tasks import TaskContext


@pytest.fixture
def allocation(monkeypatch):
    # Replace this module's os reference, not the global os.name used by pathlib.
    monkeypatch.setattr(backends, "os", SimpleNamespace(name="posix", environ={
        "SLURM_JOB_ID": "123", "SLURM_NTASKS": "5",
    }))
    monkeypatch.setattr(backends.shutil, "which", lambda name: str(name))
    return backends.TACC()


def test_allocation_validation(allocation):
    assert allocation.capacity(None) == 5
    assert allocation.capacity(3) == 3
    for value in (0, True, 6):
        with pytest.raises(ValueError):
            allocation.capacity(value)
    backends.os.environ["SLURM_CPUS_PER_TASK"] = "2"
    with pytest.raises(ValueError, match="one CPU"):
        allocation.capacity(None)


def test_requires_allocation(allocation):
    backends.os.environ.pop("SLURM_JOB_ID")
    with pytest.raises(ValueError, match="allocation"):
        allocation.capacity(None)


def test_requires_launcher(allocation, monkeypatch):
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="ibrun"):
        allocation.capacity(None)


def test_launch_arguments(allocation):
    task = fm.tasks.Command("mpi", ["python", "program.py"], cores=3, ranks=3)
    assert allocation.launch(list(task.argv), task, 2) == [
        "ibrun", "-n", "3", "-o", "2", "task_affinity", "python", "program.py",
    ]


def test_offsets_reset_and_stages_wait(allocation, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(runner, "ProcessPoolExecutor", ThreadPoolExecutor)

    def process(argv, context, env=None):
        if context.output_dir.parent.name == "after":
            assert len(calls) == 2
        calls.append((context.output_dir.name, argv, env))
        return runner.ProcessResult(context.output_dir, context.output_dir / "stdout.log", 0)

    monkeypatch.setattr(runner, "_run_process", process)
    (tmp_path / "model.tcl").write_text("wipe")
    workflow = fm.Workflow().add("parallel", parallel=True, tasks=[
        fm.tasks.OpenSees("a", "model.tcl", ranks=2),
        fm.tasks.Command("b", ["python", "mpi.py"], cores=3, ranks=3),
    ]).add("after", tasks=[fm.tasks.Command("c", ["echo", "done"])])
    run = fm.execute(workflow, workspace=tmp_path, backend=allocation)
    commands = {name: argv for name, argv, _ in calls}
    assert commands["a"][:6] == ["ibrun", "-n", "2", "-o", "0", "task_affinity"]
    assert commands["b"][:6] == ["ibrun", "-n", "3", "-o", "2", "task_affinity"]
    assert commands["c"][:6] == ["ibrun", "-n", "1", "-o", "0", "task_affinity"]
    assert all(env["OMP_NUM_THREADS"] == "1" for _, _, env in calls)
    assert json.loads(run.manifest.read_text())["stages"]["parallel"]["b"]["offset"] == 2


def test_preflight_prevents_partial_execution(allocation, tmp_path):
    workflow = fm.Workflow().add("first", tasks=[fm.tasks.Command("a", ["echo", "no"])])
    workflow.add("too_big", tasks=[fm.tasks.OpenSees("b", "model.tcl", ranks=6)])
    with pytest.raises(fm.jobs.WorkflowExecutionError, match="requires 6 cores"):
        fm.execute(workflow, workspace=tmp_path, backend=allocation)
    assert not (tmp_path / "first").exists()


def test_parallel_callbacks_rejected(allocation, tmp_path):
    workflow = fm.Workflow().add("callbacks", parallel=True, tasks=[fm.tasks.Python("a", str)])
    with pytest.raises(fm.jobs.WorkflowExecutionError, match="sequential"):
        fm.execute(workflow, workspace=tmp_path, backend=allocation)


def test_local_mpi_command_rejected(tmp_path):
    workflow = fm.Workflow().add("mpi", tasks=[fm.tasks.Command("a", ["python"], ranks=1)])
    with pytest.raises(fm.jobs.WorkflowExecutionError, match="MPI Command"):
        fm.execute(workflow, workspace=tmp_path)


def test_launcher_failure_preserves_log(allocation, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ProcessPoolExecutor", ThreadPoolExecutor)

    def fail(argv, **kwargs):
        kwargs["stdout"].write("launcher failed\n")
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(runner.subprocess, "run", fail)
    workflow = fm.Workflow().add("mpi", tasks=[fm.tasks.Command("a", ["program"], ranks=1)])
    workflow.add("later", tasks=[fm.tasks.Command("b", ["program"])])
    with pytest.raises(fm.jobs.WorkflowExecutionError) as error:
        fm.execute(workflow, workspace=tmp_path, backend=allocation)
    assert "launcher failed" in (tmp_path / "mpi/a/stdout.log").read_text()
    assert "later" not in error.value.run.results


def test_smoke_model_generation_and_comparison(tmp_path):
    from examples.workflows.tacc_mpi_smoke import CASES, create, compare

    context = TaskContext(tmp_path, tmp_path, {}, {})
    create(context)
    results = {"single": {}, "parallel": {}}
    for name, ranks in CASES.items():
        assert f"if {{$np != {ranks}}}" in (tmp_path / "models" / f"{name}.tcl").read_text()
        stage = "single" if name == "single" else "parallel"
        directory = tmp_path / stage / name
        directory.mkdir(parents=True)
        for rank in range(ranks):
            (directory / f"rank_{rank}.txt").write_text(f"{rank} {ranks} 0.001")
        results[stage][name] = runner.ProcessResult(directory, directory / "stdout.log", 0)
    compare(TaskContext(tmp_path, tmp_path, {}, results))
    assert "pair_b: 3 ranks" in (tmp_path / "comparison.txt").read_text()


def test_replay_forwards_backend(monkeypatch, tmp_path):
    import importlib
    packaging = importlib.import_module("femora.jobs.bundle")
    source = tmp_path / "source.py"
    source.write_text("import femora as fm\ndef build_workflow():\n    return fm.Workflow()\n")
    package = fm.jobs.bundle(source=source, destination=tmp_path / "bundle.zip", inputs={})
    selected = backends.TACC()
    seen = {}

    def execute(workflow, **kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(packaging, "execute", execute)
    assert fm.jobs.replay(package, workspace=tmp_path / "replayed", backend=selected, cores=5) == "ok"
    assert seen["backend"] is selected
    assert seen["cores"] == 5


@pytest.mark.skipif(os.environ.get("FEMORA_TEST_TACC_MPI") != "1", reason="requires a TACC allocation with five slots")
def test_real_tacc_bundle(tmp_path):
    package = fm.jobs.bundle(
        source=Path(__file__).parents[2] / "examples/workflows/tacc_mpi_smoke.py",
        destination=tmp_path / "mpi.zip", inputs={},
    )
    run = fm.jobs.replay(package, workspace=tmp_path / "results", backend=backends.TACC(), cores=5)
    assert "pair_b: 3 ranks" in (run.workspace / "compare/summary/comparison.txt").read_text()
