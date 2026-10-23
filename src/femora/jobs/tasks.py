"""Task definitions for Femora workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Callable, Mapping, Sequence


def _positive_cores(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("task cores must be a positive integer")


def _task_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip() or name in {".", ".."}:
        raise ValueError("task name must be a nonempty directory name")
    if "/" in name or "\\" in name:
        raise ValueError("task name must not contain path separators")


@dataclass(frozen=True)
class TaskContext:
    """Paths and available completed-task results supplied to a Python callback.

    Attributes:
        workspace (Path): Shared run root. Use this to locate other tasks' files.
        output_dir (Path): This task's directory, ``workspace/stage/task``.
        inputs (Mapping[str, Any]): Workflow-level inputs passed by execute or replay.
        results (Mapping[str, Mapping[str, Any]]): Return values from earlier stages
            and completed earlier siblings in a sequential stage.

    Note:
        The runner supplies this object; do not construct it for ordinary runs.
        Parallel siblings cannot use each other's return values. In a sequential
        stage, results from earlier completed siblings are also available.
    """

    __doc_controls__ = {"summary": True, "members": ["result"]}

    workspace: Path
    output_dir: Path
    inputs: Mapping[str, Any]
    results: Mapping[str, Mapping[str, Any]]

    def result(self, stage: str, task: str) -> Any:
        """Read an available completed task's return value.

        Args:
            stage (str): Earlier stage, or the current stage for a completed sequential sibling.
            task (str): Task name within that stage.

        Returns:
            value (Any): The callback value or a ProcessResult for an external process.

        Raises:
            KeyError: The stage or task is not available.

        Example:
            ```python
            def postprocess(context):
                model_info = context.result("build", "model")
                return model_info
            ```
        """
        return self.results[stage][task]


@dataclass(frozen=True)
class Python:
    """Run function(context, **kwargs) in its own process.

    Use an importable function and pickleable argument values. Context is passed
    by the runner; kwargs supplies task-specific values, not workflow inputs.

    Args:
        name (str): Unique directory-safe task name within its stage.
        function (Callable): Top-level callback accepting context as its first argument.
        cores (int): Positive core reservation; this does not parallelize the callback.
        kwargs (Mapping[str, Any]): Keyword arguments passed to the callback.

    Raises:
        ValueError: Name or core reservation is invalid.
        TypeError: The callback is not callable or kwargs is not a string-keyed mapping.

    Example:
        ```python
        from femora.jobs.tasks import Python
        def report(context, label):
            return {"label": label, "workspace": str(context.workspace)}
        task = Python("report", report, kwargs={"label": "case-a"})
        ```

    Note:
        Return values must be transferable between processes. Keep callback
        functions importable and protect execution with a main guard. The TACC
        backend permits Python callbacks only in sequential stages with cores=1.
    """

    __doc_controls__ = {"members": []}

    name: str
    function: Callable[..., Any]
    cores: int = 1
    kwargs: Mapping[str, Any] = field(default_factory=dict, kw_only=True)

    def __post_init__(self) -> None:
        _task_name(self.name)
        if not callable(self.function):
            raise TypeError("task function must be callable")
        _positive_cores(self.cores)
        if not isinstance(self.kwargs, Mapping):
            raise TypeError("Python task kwargs must be a mapping")
        if any(not isinstance(key, str) for key in self.kwargs):
            raise TypeError("Python task kwargs keys must be strings")
        object.__setattr__(self, "kwargs", dict(self.kwargs))


@dataclass(frozen=True)
class Command:
    """Run an executable without a shell in the task output directory.

    Set ranks and matching cores for an MPI-aware executable, including Python
    scripts using mpi4py. MPI execution requires an allocation backend.

    Args:
        name (str): Directory-safe task name.
        argv (Sequence[str | Path]): Executable followed by individual arguments.
        cores (int): Positive reservation; must equal ranks for an MPI command.
        env (Mapping[str, str] | None): Environment overrides added to the inherited environment.
        ranks (int | None): MPI rank count, or None for a serial command.

    Raises:
        ValueError: Name, argv, cores, or ranks is invalid or inconsistent.
        TypeError: Arguments or environment values have invalid types.

    Example:
        ```python
        import sys
        from femora.jobs.tasks import Command
        task = Command("check", [sys.executable, "-c", "print('ready')"])
        ```

    Note:
        Shell syntax such as pipes, redirection, and wildcard expansion is not
        interpreted. Use absolute paths for scripts outside the task directory.
        Logs and the process return code are exposed through ProcessResult.
    """

    __doc_controls__ = {"members": []}

    name: str
    argv: Sequence[str | Path]
    cores: int = 1
    env: Mapping[str, str] | None = None
    ranks: int | None = None

    def __post_init__(self) -> None:
        _task_name(self.name)
        _positive_cores(self.cores)
        if self.ranks is not None:
            _positive_cores(self.ranks)
            if self.cores != self.ranks:
                raise ValueError("MPI Command cores must equal ranks")
        if isinstance(self.argv, (str, Path)) or not self.argv:
            raise ValueError("command argv must contain an executable")
        if any(not isinstance(arg, (str, Path)) for arg in self.argv):
            raise TypeError("command arguments must be strings or paths")
        object.__setattr__(self, "argv", tuple(str(arg) for arg in self.argv))
        if self.env is not None and any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.env.items()
        ):
            raise TypeError("command environment keys and values must be strings")


@dataclass(frozen=True)
class OpenSees:
    """Run one Tcl model. Multi-rank execution needs a remote backend.

    ``executable`` overrides the app or environment default for this task only.
    On a cluster, use a path visible and executable from every compute node.

    Args:
        name (str): Directory-safe task name.
        script (str | Path): Tcl path relative to the workflow workspace.
        ranks (int): Positive solver rank count; the local runner requires one.
        executable (str | Path | None): Executable override. Otherwise use
            FEMORA_OPENSEES, then OpenSees locally or OpenSeesMP with the backend.

    Raises:
        ValueError: Name, script path, executable, or rank count is invalid.
        TypeError: An executable override is not a string or Path.

    Example:
        ```python
        from femora.jobs.tasks import OpenSees
        solve = OpenSees("solve", "build/model/model.tcl", ranks=98)
        ```

    Note:
        This defines a task; it neither builds Tcl nor installs the solver.
        The example requires an allocation backend and an appropriate MPI build.
    """

    __doc_controls__ = {"members": ["cores"]}

    name: str
    script: str | Path
    ranks: int = 1
    executable: str | Path | None = None

    def __post_init__(self) -> None:
        _task_name(self.name)
        _positive_cores(self.ranks)
        if self.executable is not None:
            if not isinstance(self.executable, (str, Path)):
                raise TypeError("OpenSees executable must be a string or path")
            executable = str(self.executable)
            if not executable.strip():
                raise ValueError("OpenSees executable must not be empty")
            object.__setattr__(self, "executable", executable)
        script = str(self.script)
        path = PurePath(script)
        if (
            not script
            or path.is_absolute()
            or PureWindowsPath(script).drive
            or ".." in path.parts
            or "\\" in script
        ):
            raise ValueError("OpenSees script must be relative to the workflow workspace")
        object.__setattr__(self, "script", script)

    @property
    def cores(self) -> int:
        """Reserved core slots, equal to the solver rank count."""
        return self.ranks


Task = Python | Command | OpenSees


__all__ = ["Command", "OpenSees", "Python", "Task", "TaskContext"]
