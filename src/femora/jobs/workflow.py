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
    """Define ordered stages without executing their tasks.

    Args:
        name (str): Nonempty workflow name used in the run manifest.

    Example:
        ```python
        from femora.jobs import Workflow, tasks
        workflow = Workflow("analysis")
        workflow.add("solve", tasks=[tasks.OpenSees("model", "model.tcl")])
        workflow.outputs("solve/model/*.log")
        ```

    Note:
        All tasks in one stage finish before the next stage starts. No automatic
        task retry or resume is provided. Use a fresh workspace for each run.
    """

    __doc_controls__ = {"summary": True, "members": ["stages", "output_patterns", "add", "outputs"]}

    def __init__(self, name: str = "workflow") -> None:
        if not name or not name.strip():
            raise ValueError("workflow name must not be empty")
        self.name = name
        self._stages: list[_Stage] = []
        self._outputs: list[str] = []

    @property
    def stages(self) -> tuple[_Stage, ...]:
        """Ordered stage definitions as an immutable tuple; inspect, do not modify."""
        return tuple(self._stages)

    @property
    def output_patterns(self) -> tuple[str, ...]:
        """Workspace-relative artifact glob patterns selected by ``outputs()``."""
        return tuple(self._outputs)

    def add(
        self, name: str, *, tasks: Sequence[Task], parallel: bool = False
    ) -> Workflow:
        """Append a named stage after all existing stages.

        Args:
            name (str): Unique directory-safe stage name.
            tasks (Sequence[Task]): Nonempty sequence of Python, Command, or OpenSees tasks.
            parallel (bool): Start all tasks together rather than sequentially.

        Returns:
            workflow (Workflow): This workflow, for chained calls.

        Raises:
            ValueError: Stage/task names are invalid or duplicated, or tasks is empty.
            TypeError: A task type or the parallel flag is invalid.

        Note:
            A parallel stage must fit its combined core reservations inside the
            execution capacity. Dependencies belong in separate ordered stages.
        """
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
        """Select artifacts by glob, relative to the job workspace.

        Args:
            *patterns (str): Relative glob patterns without parent traversal or backslashes.

        Returns:
            workflow (Workflow): This workflow, for chained calls.

        Raises:
            ValueError: A pattern can escape the workspace or is empty.

        Example:
            ```python
            from femora.jobs import Workflow
            workflow = Workflow().outputs("postprocess/**/*.csv", "**/*.log")
            ```
        """
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
