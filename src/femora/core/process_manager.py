# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union
import weakref

from femora.components.analysis.analysis import Analysis
from femora.core.action_base import Action
from femora.core.constraint_base import MPConstraint, SPConstraint
from femora.core.pattern_base import Pattern
from femora.core.recorder_base import Recorder

if TYPE_CHECKING:
    from femora.core.model import Model

ProcessComponent = Union[SPConstraint, MPConstraint, Pattern, Recorder, Analysis, Action]


class ProcessManager:
    """Order solver operations through ``model.process`` before Tcl export.

    Steps can contain constraints, patterns, recorders, analyses, or actions.
    Adding a step schedules its Tcl emission; it does not run an analysis.
    Unlike a Jobs Workflow, this sequence lives inside one solver script.

    Actions are held directly. Other supported objects are weakly referenced
    and must remain alive, normally through their owning model manager.

    Example:
        ```python
        from femora import Model

        model = Model()
        index = model.process.add_step(model.actions.set_time(0.0), "Start clock")
        assert index == 0
        assert "setTime" in model.process.to_tcl()
        ```
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "add_step",
            "insert_step",
            "remove_step",
            "get_steps",
            "get_step",
            "clear",
            "to_tcl",
        ],
    }

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self.steps: List[Dict] = []
        self.current_step = -1

    def __iter__(self):
        return iter(self.steps)

    def __len__(self):
        return len(self.steps)

    def add_step(
        self,
        component: Union[ProcessComponent, List[ProcessComponent]],
        description: str = "",
    ) -> int:
        """Append an operation, or append each operation in a list in order.

        Args:
            component: Supported process object or list of such objects.
            description (str): Comment written before each operation's Tcl.

        Returns:
            int: Zero-based index of the final appended step; -1 for an empty list.

        Raises:
            TypeError: An object is not a supported process component. Earlier
                items in a list may already have been appended when this occurs.
        """
        if isinstance(component, list):
            last_index = -1
            for comp in component:
                last_index = self.add_step(comp, description)
            return last_index

        component_ref = self._store_component_ref(component)

        step = {
            "component": component_ref,
            "description": description,
        }

        self.steps.append(step)
        return len(self.steps) - 1

    def insert_step(
        self,
        index: int,
        component: Union[ProcessComponent, List[ProcessComponent]],
        description: str = "",
    ) -> bool:
        """Insert an operation or ordered list at a step position.

        Args:
            index (int): Insertion position; negative positions are adjusted by
                ``len(steps) + 1``, so -1 appends.
            component: Supported process object or list of objects.
            description (str): Comment applied to each inserted operation.

        Returns:
            bool: Whether insertion succeeded. An out-of-range position returns
            False. List insertion is not transactional.

        Raises:
            TypeError: A component is unsupported at a valid insertion position.
        """
        if isinstance(component, list):
            success = True
            for comp in reversed(component):
                success = success and self.insert_step(index, comp, description)
            return success

        if index < 0:
            index += len(self.steps) + 1

        if 0 <= index <= len(self.steps):
            component_ref = self._store_component_ref(component)

            step = {
                "component": component_ref,
                "description": description,
            }

            self.steps.insert(index, step)

            if index <= self.current_step:
                self.current_step += 1

            return True
        return False

    def remove_step(self, index: int) -> bool:
        """Remove a step without deleting its component from its owning manager.

        Args:
            index (int): Nonnegative zero-based step index.

        Returns:
            bool: True when removed, False for an invalid or negative index.
        """
        if 0 <= index < len(self.steps):
            del self.steps[index]

            if index <= self.current_step:
                self.current_step -= 1

            return True
        return False

    def clear(self) -> None:
        """Empty the sequence and reset its current-step index to -1.

        Model components and output files are not deleted. This does not send
        ``wipe`` or any other command to a running solver.
        """
        self.steps.clear()
        self.current_step = -1

    def get_steps(self) -> List[Dict]:
        """Return the live step list, not a detached snapshot.

        Returns:
            list[dict]: Entries with ``component`` and ``description`` keys.
            Non-action components are stored as weak references. Prefer the
            insertion/removal methods over direct mutation of this list.
        """
        return self.steps

    def get_step(self, index: int) -> Optional[Dict]:
        """Look up the live record for a nonnegative zero-based index.

        Args:
            index (int): Step position; negative indices are not supported.

        Returns:
            dict | None: Stored record, or None when out of range. Component
            values follow the same reference convention as ``get_steps()``.
        """
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def to_tcl(self) -> str:
        """Render all steps, in order, with their description comments.

        Returns:
            str: Combined Tcl, or an empty string for an empty process.

        Note:
            Referenced components must still exist. This method neither runs
            the Tcl nor validates solver convergence or command compatibility.
        """
        tcl_script = ""
        for step in self.steps:
            component = step["component"]
            if isinstance(component, weakref.ref):
                component = component()
            description = step["description"]
            tcl_script += f"# {description} ======================================\n\n"
            tcl_script += f"{component.to_tcl()}\n\n\n"
        return tcl_script

    @staticmethod
    def _store_component_ref(component: ProcessComponent):
        if isinstance(component, Action):
            return component
        if isinstance(
            component,
            (SPConstraint, MPConstraint, Pattern, Recorder, Analysis),
        ):
            return weakref.ref(component)
        raise TypeError(
            f"Invalid component type: {type(component)}. Must be one of the allowed types."
        )
