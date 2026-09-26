"""Ordered stages and artifact selection for a workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath, PureWindowsPath
from typing import Sequence

from .tasks import Command, OpenSees, Python, Task


@dataclass(frozen=True)
class _Stage:
    name: str
    tasks: tuple[Task, ...]
    parallel: bool


class Workflow:
    """A sequence of stages; tasks in a parallel stage start together."""

    def __init__(self, name: str = "workflow") -> None:
        if not name or not name.strip():
            raise ValueError("workflow name must not be empty")
        self.name = name
        self._stages: list[_Stage] = []
        self._outputs: list[str] = []

    @property
    def stages(self) -> tuple[_Stage, ...]:
        return tuple(self._stages)

    @property
    def output_patterns(self) -> tuple[str, ...]:
        return tuple(self._outputs)

    def add(
        self, name: str, *, tasks: Sequence[Task], parallel: bool = False
    ) -> Workflow:
        """Append a stage after all existing stages."""
        if not name or not name.strip() or name in {".", ".."}:
            raise ValueError("stage name must be a nonempty directory name")
        if "/" in name or "\\" in name:
            raise ValueError("stage name must not contain path separators")
        if any(stage.name == name for stage in self._stages):
            raise ValueError(f"duplicate stage name: {name}")
        chosen = tuple(tasks)
        if not chosen:
            raise ValueError("a stage must contain at least one task")
        if not isinstance(parallel, bool):
            raise TypeError("parallel must be a boolean")
        if any(not isinstance(task, (Python, Command, OpenSees)) for task in chosen):
            raise TypeError("tasks must be fm.tasks.Python, Command, or OpenSees")
        names = [task.name for task in chosen]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate task name in stage {name}")
        if any(task.name in {".", ".."} or "/" in task.name or "\\" in task.name for task in chosen):
            raise ValueError("task names must be directory names")
        self._stages.append(_Stage(name, chosen, parallel))
        return self

    def outputs(self, *patterns: str) -> Workflow:
        """Select artifacts by glob, relative to the job workspace."""
        for pattern in patterns:
            path = PurePath(pattern)
            if (
                not pattern
                or path.is_absolute()
                or PureWindowsPath(pattern).drive
                or ".." in path.parts
                or "\\" in pattern
            ):
                raise ValueError("output patterns must be relative and stay inside the workspace")
            self._outputs.append(pattern)
        return self


__all__ = ["Workflow"]
