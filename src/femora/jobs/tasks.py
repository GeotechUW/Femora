"""Task definitions for Femora workflows."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Paths and preceding task results passed to a running task."""

    workspace: Path
    output_dir: Path
    inputs: Mapping[str, Any]
    results: Mapping[str, Mapping[str, Any]]

    def result(self, stage: str, task: str) -> Any:
        return self.results[stage][task]


@dataclass(frozen=True)
class Python:
    """Run a Python function in its own process."""

    name: str
    function: Callable[[TaskContext], Any]
    cores: int = 1

    def __post_init__(self) -> None:
        _task_name(self.name)
        if not callable(self.function):
            raise TypeError("task function must be callable")
        _positive_cores(self.cores)


@dataclass(frozen=True)
class Command:
    """Run an executable without a shell in the task output directory."""

    name: str
    argv: Sequence[str | Path]
    cores: int = 1
    env: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        _task_name(self.name)
        _positive_cores(self.cores)
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
    """Run one Tcl model. Multi-rank execution needs a remote backend."""

    name: str
    script: str | Path
    ranks: int = 1
    executable: str | Path | None = None

    def __post_init__(self) -> None:
        _task_name(self.name)
        _positive_cores(self.ranks)
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
        return self.ranks


Task = Python | Command | OpenSees


__all__ = ["Command", "OpenSees", "Python", "Task", "TaskContext"]
