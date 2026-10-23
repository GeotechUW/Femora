"""The workflow guide's runnable example must work without a solver."""

from pathlib import Path
import json
import re

import femora as fm
import pytest


SOURCE = Path(__file__).parents[2] / "examples/workflows/workflow_basics.py"


@pytest.mark.parametrize("number", [4, 7])
def test_tutorial_bundle_replays_and_preserves_return_values(tmp_path, number):
    archive = fm.jobs.bundle(
        source=SOURCE,
        destination=tmp_path / "tutorial.zip",
        inputs={"base_value": number},
    )
    workspace = tmp_path / "run"
    run = fm.jobs.replay(archive, workspace=workspace, cores=1)

    assert run.result("prepare", "write_base_value") == workspace / "prepare/write_base_value/base_value.txt"
    assert run.result("calculate", "double") == number * 2
    assert run.result("calculate", "triple") == number * 3
    report = workspace / "report/write_summary/summary.txt"
    assert run.result("report", "write_summary") == report
    assert report.read_text() == f"double: {number * 2:.1f}\ntriple: {number * 3:.1f}\n"
    assert set(run.artifacts) == {
        report,
        workspace / "calculate/double/value.txt",
        workspace / "calculate/triple/value.txt",
    }
    assert run.manifest.is_file()
    record = json.loads(run.manifest.read_text())
    assert set(record) == {"workflow", "backend", "capacity", "stages", "artifacts"}
    assert record["backend"] == "local" and record["capacity"] == 1
    assert record["stages"]["prepare"]["write_base_value"] == {
        "status": "finished", "cores": 1, "offset": None}
    assert not list(workspace.rglob("stdout.log"))


def test_tutorial_failure_has_the_documented_partial_workspace(tmp_path):
    archive = fm.jobs.bundle(source=SOURCE, destination=tmp_path / "failure.zip",
                             inputs={"base_value": "invalid"})
    workspace = tmp_path / "failed-run"
    with pytest.raises(fm.jobs.WorkflowExecutionError) as captured:
        fm.jobs.replay(archive, workspace=workspace, cores=1)
    error = captured.value
    assert "stage 'calculate' failed: double" in str(error)
    record = json.loads(error.run.manifest.read_text())
    assert record["stages"] == {
        "prepare": {"write_base_value": {"status": "finished", "cores": 1, "offset": None}},
        "calculate": {"double": {"status": "failed", "cores": 1, "offset": None,
                                  "error": "could not convert string to float: 'invalid'"}},
    }
    assert record["artifacts"] == []
    jobs_concept = (SOURCE.parents[2] / "website/docs/concepts/jobs.md").read_text(encoding="utf-8")
    documented_failure = json.loads(re.findall(r"```json\n(.*?)```", jobs_concept, re.S)[0])
    assert record["stages"]["calculate"]["double"] == documented_failure
    assert (workspace / "prepare/write_base_value/base_value.txt").read_text() == "invalid"
    assert (workspace / "calculate/double").is_dir()
    assert not (workspace / "calculate/double/value.txt").exists()
    assert not (workspace / "calculate/triple").exists()
    assert not (workspace / "report").exists()
    assert not list(workspace.rglob("stdout.log"))
    with pytest.raises(KeyError):
        error.run.result("calculate", "double")
