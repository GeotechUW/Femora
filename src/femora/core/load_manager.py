# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from femora.core.load_base import Load
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.components.load.element_load import ElementLoad
    from femora.components.load.node_load import NodeLoad
    from femora.components.load.sp_load import SpLoad


class LoadManager:
    """Create load commands through ``model.load`` for attachment to Plain patterns.

    A load describes nodal forces, element loading, or prescribed motion. Its
    time variation comes from the containing pattern's time series. Registering
    a load alone neither attaches it to a pattern nor applies it to the solver.

    Example:
        ```python
        from femora import Model

        model = Model()
        load = model.load.node(node_tag=1, values=[0.0, 0.0, -10.0])
        series = model.time_series.constant()
        gravity = model.pattern.plain(series)
        gravity.add_load_instance(load)
        model.process.add_step(gravity, "Apply gravity")
        assert "pattern Plain" in model.process.to_tcl()
        ```

    The example demonstrates definitions and command ordering; node 1 must exist
    with a compatible DOF layout in a real assembled model. Mass is not created
    by a force load, and assigning mass does not automatically create weight.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "node",
            "element",
            "sp",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "load", None)
        if isinstance(existing_manager, LoadManager):
            raise ValueError("mesh_maker already owns a load manager")

        self._mesh_maker = mesh_maker
        mesh_maker.load = self
        self._loads: Dict[int, Load] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Load]()

    def __len__(self) -> int:
        return len(self._loads)

    def __iter__(self):
        return iter(self._loads.values())

    def add(self, load: Load) -> Load:
        """Register a load and return the same object with a local registry tag.

        Args:
            load (Load): Unmanaged object or one already owned here.

        Raises:
            TypeError: Input is not a Load.
            ValueError: Foreign ownership or tag conflict.

        A registry tag is not the loaded node/element tag or the pattern tag.
        """
        if not isinstance(load, Load):
            raise TypeError("load must be a Load instance")
        if load._owner is None:
            load._owner = self
        elif load._owner is not self:
            raise ValueError("load already belongs to another manager")
        try:
            load.tag = self._tagging.assign_tag(self._loads, load, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Load tag {load.tag} already exists") from exc
        self._loads[load.tag] = load
        return load

    def node(
        self,
        *,
        values: list[float],
        node_tag: int | None = None,
        node_mask: object | None = None,
        pids: list[int] | None = None,
    ) -> NodeLoad:
        """Create a nodal load component.

        Args:
            values: Nodal force or moment values corresponding to the active
                degrees of freedom (DOFs) at the node.
            node_tag: Optional explicit tag of the target node.
            node_mask: Optional NodeMask object to apply the load to multiple
                nodes.
            pids: Optional processor partition IDs for parallel executions.

        Raises:
            ValueError: If neither `node_tag` nor `node_mask` is specified,
                if `node_mask` is not a NodeMask instance, or if any input
                parameter fails validation.

        Returns:
            component (NodeLoad): Registered definition; no solver is launched.
        """
        from femora.components.load.node_load import NodeLoad

        component = NodeLoad(values=values, node_tag=node_tag, node_mask=node_mask, pids=pids)
        self.add(component)
        return component

    def element(
        self,
        *,
        kind: str,
        params: dict[str, float],
        ele_tags: list[int] | None = None,
        ele_range: tuple[int, int] | None = None,
        element_mask: object | None = None,
        pid: int | None = None,
    ) -> ElementLoad:
        """Create an element load component.

        Args:
            kind: Type of element load. Must be either `'beamUniform'` or `'beamPoint'`.
            params: Dictionary of load parameters. For `'beamUniform'`: `Wy`
                (required), `Wz` (optional), `Wx` (optional). For `'beamPoint'`:
                `Py` (required), `xL` (required, relative distance from node I),
                `Pz` (optional), `Px` (optional).
            ele_tags: Optional list of explicit element tags.
            ele_range: Optional tuple of `(start, end)` element tags defining a range.
            element_mask: Optional ElementMask object to apply the load to.
            pid: Optional processor partition ID for parallel execution.

        Raises:
            ValueError: If constructor arguments are invalid or conflict.

        Returns:
            component (ElementLoad): Registered definition; no solver is launched.
        """
        from femora.components.load.element_load import ElementLoad

        component = ElementLoad(
            kind=kind,
            params=params,
            ele_tags=ele_tags,
            ele_range=ele_range,
            element_mask=element_mask,
            pid=pid,
        )
        self.add(component)
        return component

    def sp(
        self,
        *,
        dof: int,
        value: float,
        node_tag: int | None = None,
        node_mask: object | None = None,
        pids: list[int] | None = None,
    ) -> SpLoad:
        """Create a single-point load component.

        Args:
            dof: 1-indexed degree of freedom (DOF) to apply the value to.
            value: Numerical value of the applied single-point excitation.
            node_tag: Optional explicit tag of the target node.
            node_mask: Optional NodeMask object to apply this load to multiple
                nodes.
            pids: Optional processor partition IDs for parallel execution.

        Raises:
            ValueError: If neither `node_tag` nor `node_mask` is specified,
                if `node_mask` is not a NodeMask, or if input validation fails.

        Returns:
            component (SpLoad): Registered definition; no solver is launched.
        """
        from femora.components.load.sp_load import SpLoad

        component = SpLoad(dof=dof, value=value, node_tag=node_tag, node_mask=node_mask, pids=pids)
        self.add(component)
        return component

    def get(self, tag: int) -> Optional[Load]:
        """Return a load by integer-convertible registry tag, or None if absent."""
        return self._loads.get(int(tag))

    def get_all(self) -> Dict[int, Load]:
        """Return a shallow tag-to-load snapshot; load objects remain shared."""
        return dict(self._loads)

    def remove(self, tag: int) -> None:
        """Detach a load, clear its pattern tag, and retag remaining loads.

        Args:
            tag (int): Current registry tag; absent entries are ignored.

        This does not remove an existing object's reference from a PlainPattern
        or edit exported Tcl. Rebuild affected patterns after registry changes.
        """
        load = self._loads.pop(int(tag), None)
        if load is not None:
            load.tag = None
            load._owner = None
            load.pattern_tag = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach all loads and clear their registry and pattern tags.

        Patterns themselves remain registered and may still reference the old
        objects. This is not a coordinated whole-model or solver-domain reset.
        """
        for load in list(self._loads.values()):
            load.tag = None
            load._owner = None
            load.pattern_tag = None
        self._loads.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive load registry origin and retag existing loads.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. Loaded node/element tags are unchanged.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._loads, self._start_tag)


__all__ = ["LoadManager"]
