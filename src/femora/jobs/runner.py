"""Local execution of ordered workflow stages."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from .tasks import Command, OpenSees, Python, Task, TaskContext
from .workflow import Workflow


class WorkflowExecutionError(RuntimeError):
    """A workflow task failed; the run manifest remains in the workspace."""

    def __init__(self, message: str, run: RunResult) -> None:
        super().__init__(message)
        self.run = run


@dataclass(frozen=True)
class RunResult:
    workspace: Path
    results: Mapping[str, Mapping[str, Any]]
    artifacts: tuple[Path, ...]
    manifest: Path

    def result(self, stage: str, task: str) -> Any:
        return self.results[stage][task]


@dataclass(frozen=True)
class ProcessResult:
    output_dir: Path
    log: Path
    returncode: int


def _run_process(argv: list[str], context: TaskContext, env: Mapping[str, str] | None = None) -> ProcessResult:
    log = context.output_dir / "stdout.log"
    environment = {**os.environ, **env} if env else None
    try:
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(
                argv,
                cwd=context.output_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except OSError as exc:
        raise RuntimeError(f"could not start {argv[0]}: {exc}") from exc

    tail: deque[str] = deque(maxlen=20)
    analysis_error = False
    with log.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            tail.append(line.rstrip())
            analysis_error |= line.startswith("FEMORA_PROGRESS|ERROR|")
    if completed.returncode != 0 or analysis_error:
        detail = "\n".join(tail)
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}; log: {log}\n{detail}"
        )
    return ProcessResult(context.output_dir, log, completed.returncode)


def _run_task(task: Task, context: TaskContext) -> Any:
    context.output_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(task, Python):
        return task.function(context)
    if isinstance(task, Command):
        return _run_process(list(task.argv), context, task.env)

    script = (context.workspace / task.script).resolve()
    if not script.is_relative_to(context.workspace) or not script.is_file():
        raise FileNotFoundError(f"OpenSees script was not found in workspace: {task.script}")
    configured = task.executable or os.environ.get("FEMORA_OPENSEES") or "OpenSees"
    executable = shutil.which(str(configured))
    if executable is None:
        raise FileNotFoundError(
            f"OpenSees executable was not found: {configured}; set FEMORA_OPENSEES"
        )
    return _run_process([executable, str(script)], context)


def _collect_artifacts(workspace: Path, patterns: tuple[str, ...]) -> tuple[Path, ...]:
    found: set[Path] = set()
    for pattern in patterns:
        for path in workspace.glob(pattern):
            if path.is_file() and path.resolve().is_relative_to(workspace):
                found.add(path.resolve())
    return tuple(sorted(found))


def execute(
    workflow: Workflow,
    *,
    workspace: str | Path,
    inputs: Mapping[str, Any] | None = None,
    cores: int | None = None,
) -> RunResult:
    """Run a workflow locally, using separate processes for its tasks.

    A parallel stage starts all of its tasks concurrently. It is rejected if
    the sum of task core reservations exceeds ``cores``. Local OpenSees tasks
    are serial; multi-rank execution requires a remote backend.
    """
    if not isinstance(workflow, Workflow):
        raise TypeError("workflow must be an fm.Workflow")
    capacity = os.cpu_count() if cores is None else cores
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise ValueError("cores must be a positive integer")
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.json"
    results: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, dict[str, Any]]] = {}

    def snapshot() -> RunResult:
        artifacts = _collect_artifacts(root, workflow.output_patterns)
        payload = {
            "workflow": workflow.name,
            "stages": records,
            "artifacts": [str(path.relative_to(root)) for path in artifacts],
        }
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return RunResult(root, results, artifacts, manifest)

    for stage in workflow.stages:
        if any(isinstance(task, OpenSees) and task.ranks != 1 for task in stage.tasks):
            raise WorkflowExecutionError(
                f"stage '{stage.name}' requests multi-rank OpenSees, which the local runner does not support",
                snapshot(),
            )
        required = sum(task.cores for task in stage.tasks) if stage.parallel else max(task.cores for task in stage.tasks)
        if required > capacity:
            raise WorkflowExecutionError(
                f"stage '{stage.name}' requires {required} cores, but only {capacity} are available",
                snapshot(),
            )
        records[stage.name] = {}
        results[stage.name] = {}
        prior = {name: dict(values) for name, values in results.items() if name != stage.name}
        workers = len(stage.tasks) if stage.parallel else 1
        with ProcessPoolExecutor(max_workers=workers) as pool:
            if stage.parallel:
                futures = {}
                for task in stage.tasks:
                    available = {**prior, stage.name: dict(results[stage.name])}
                    context = TaskContext(root, root / stage.name / task.name, dict(inputs or {}), available)
                    records[stage.name][task.name] = {"status": "running", "cores": task.cores}
                    futures[pool.submit(_run_task, task, context)] = task
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        results[stage.name][task.name] = future.result()
                        records[stage.name][task.name]["status"] = "finished"
                    except Exception as exc:
                        records[stage.name][task.name].update(status="failed", error=str(exc))
            else:
                for task in stage.tasks:
                    available = {**prior, stage.name: dict(results[stage.name])}
                    context = TaskContext(root, root / stage.name / task.name, dict(inputs or {}), available)
                    records[stage.name][task.name] = {"status": "running", "cores": task.cores}
                    try:
                        results[stage.name][task.name] = pool.submit(_run_task, task, context).result()
                        records[stage.name][task.name]["status"] = "finished"
                    except Exception as exc:
                        records[stage.name][task.name].update(status="failed", error=str(exc))
                        break
        failed = [name for name, record in records[stage.name].items() if record["status"] == "failed"]
        run = snapshot()
        if failed:
            raise WorkflowExecutionError(
                f"stage '{stage.name}' failed: {', '.join(failed)}", run
            )
    return snapshot()


__all__ = ["ProcessResult", "RunResult", "WorkflowExecutionError", "execute"]
