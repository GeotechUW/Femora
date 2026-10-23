# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC
from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence

import numpy as np
from numpy.typing import ArrayLike

from femora.core.event_bus import FemoraEvent

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.core.meshpart_base import MeshPart
    from femora.core.region_base import RegionBase
    from femora.components.interface.embedded_beam_solid_interface import EmbeddedBeamSolidInterface
    from femora.components.interface.embedded_node_interface import EmbeddedNodeInterface


class _BoundaryNamespace:
    """Boundary-specialized interface registration namespace."""

    def __init__(self, manager: "InterfaceManager") -> None:
        self._manager = manager

    def absorber(
        self,
        *,
        num_layers: Optional[int] = None,
        num_partitions: Optional[int] = None,
        partition_algo: Optional[str] = None,
        geometry: Optional[str] = None,
        boundary_type: Optional[str] = None,
        rayleigh_damping: Optional[float] = None,
        match_damping: Optional[bool] = None,
        progress_callback: Callable[..., None] | None = None,
        numLayers: int | None = None,
        numPartitions: int | None = None,
        partitionAlgo: str | None = None,
        type: str | None = None,
        rayleighDamping: float | None = None,
        matchDamping: bool | None = None,
    ) -> None:
        """Queue a rectangular absorbing boundary for the post-assembly stage.

        Args:
            num_layers (int | None): Absorber layer count passed to normalization.
            num_partitions (int | None): Absorber partition count, not a scheduler request.
            partition_algo (str | None): Absorber partitioner selection.
            geometry (str | None): Geometry selector supported by the boundary component.
            boundary_type (str | None): Absorber formulation selector.
            rayleigh_damping (float | None): Boundary damping configuration.
            match_damping (bool | None): Whether boundary damping matches the host.
            progress_callback (Callable | None): Boundary-generation progress callback.
            numLayers: Compatibility alias for num_layers.
            numPartitions: Compatibility alias for num_partitions.
            partitionAlgo: Compatibility alias for partition_algo.
            type: Compatibility alias for boundary_type.
            rayleighDamping: Compatibility alias for rayleigh_damping.
            matchDamping: Compatibility alias for match_damping.

        Returns:
            result (None): Configuration is queued, not added as a named interface.

        Note:
            Omitted defaults and validation follow the boundary component. Queued
            requests are consumed during post-assembly processing; requeue them
            when rebuilding a fresh assembly. Failure is not transactional.
        """
        from femora.components.interface.boundary_absorber import _normalize_absorber_kwargs

        legacy = {
            key: value
            for key, value in {
                "numLayers": numLayers,
                "numPartitions": numPartitions,
                "partitionAlgo": partitionAlgo,
                "type": type,
                "rayleighDamping": rayleighDamping,
                "matchDamping": matchDamping,
            }.items()
            if value is not None
        }
        config = _normalize_absorber_kwargs(
            num_layers=num_layers,
            num_partitions=num_partitions,
            partition_algo=partition_algo,
            geometry=geometry,
            boundary_type=boundary_type,
            rayleigh_damping=rayleigh_damping,
            match_damping=match_damping,
            progress_callback=progress_callback,
            **legacy,
        )
        self._manager._register_boundary_absorber(config)


class InterfaceBase(ABC):
    """Extension base for model-owned, lifecycle-aware interface definitions.

    Args:
        name (str): Interface registry key.
        owners (list[str]): Component names participating in the interface.

    Concrete subclasses subscribe to model events when registered and release
    subscriptions when removed. Ordinary scripts use ``model.interface`` factories.
    This base itself generates no coupling elements or solver commands.
    """

    __doc_controls__ = {"members": []}

    def __init__(self, name: str, owners: List[str]) -> None:
        self.name = name
        self.owners = owners
        self._owner: Optional["InterfaceManager"] = None

    def _bind_manager(self, manager: "InterfaceManager") -> None:
        if self._owner is not None and self._owner is not manager:
            raise ValueError("interface already belongs to another manager")
        self._owner = manager
        self._subscribe_events()

    def _model_events(self):
        return self._owner._mesh_maker.events

    def _subscribe_events(self) -> None:
        pass

    def _unsubscribe_events(self) -> None:
        pass


class InterfaceManager:
    """Register component connections through ``model.interface``.

    Factories create named definitions bound to this model's mesh-part registry.
    Concrete interface implementations use assembly/export lifecycle hooks to
    generate their connection data. Declare them before assembly unless a
    concrete interface explicitly documents another supported lifecycle.

    Attributes:
        boundary: Absorber configuration namespace; see ``boundary.absorber``
            below. Queued boundaries are separate from the named interface registry.

    Prefer interface objects over manually manipulating their generated elements.
    Keep component nodes distinct where the interface formulation requires it.
    Penalty stiffness, spatial resolution, and explicit-step stability must be
    checked for the full coupled model, not inferred from registration success.

    Example:
        ```python
        from femora import Model

        model = Model()
        assert model.interface.get("pile_soil") is None
        assert model.interface.get_all() == {}
        ```

    See Also:
        The Components interface pages provide concrete geometry, parameter,
        recorder, and solver-build requirements for each connection type.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "beam_solid_interface",
            "node_interface",
            "add",
            "get",
            "get_all",
            "require",
            "require_registered",
            "remove",
            "clear",
        ],
    }

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        self._interfaces: Dict[str, InterfaceBase] = {}
        self._embeddedinfo_list: list = []
        self._beam_solid_count = 0
        self._beam_solid_conflict_subscribed = False
        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing = getattr(mesh_maker, "interface", None)
        if isinstance(existing, InterfaceManager) and existing is not self:
            raise ValueError("mesh_maker already owns an interface manager")
        self._mesh_maker = mesh_maker
        mesh_maker.interface = self
        self.boundary = _BoundaryNamespace(self)
        self._boundary_absorbers: list[dict] = []
        self._boundary_post_assemble_subscribed = False

    def _register_boundary_absorber(self, config: dict) -> None:
        self._boundary_absorbers.append(config)
        self._ensure_boundary_absorber_subscribed()

    def _ensure_boundary_absorber_subscribed(self) -> None:
        if self._boundary_post_assemble_subscribed:
            return
        self._mesh_maker.events.subscribe(
            FemoraEvent.POST_ASSEMBLE,
            self._apply_boundary_absorbers,
        )
        self._boundary_post_assemble_subscribed = True

    def _release_boundary_absorber_subscription(self) -> None:
        if not self._boundary_post_assemble_subscribed:
            return
        self._mesh_maker.events.unsubscribe(
            FemoraEvent.POST_ASSEMBLE,
            self._apply_boundary_absorbers,
        )
        self._boundary_post_assemble_subscribed = False

    def _apply_boundary_absorbers(self, assembled_mesh=None, **kwargs) -> None:
        if not self._boundary_absorbers:
            return
        from femora.components.interface.boundary_absorber import apply_rectangular_absorbing_layer

        pending = list(self._boundary_absorbers)
        self._boundary_absorbers.clear()
        for config in pending:
            apply_rectangular_absorbing_layer(self._mesh_maker, config)

    def add(self, interface: InterfaceBase) -> InterfaceBase:
        """Bind a definition to this manager, subscribe its hooks, and retain it.

        Args:
            interface (InterfaceBase): Concrete interface object.

        Returns:
            interface (InterfaceBase): Same registered object.

        Raises:
            TypeError: Object is not an InterfaceBase.
            ValueError: Name conflict or an object already owned by another manager.
        """
        if not isinstance(interface, InterfaceBase):
            raise TypeError("interface must be an InterfaceBase instance")
        if interface.name in self._interfaces and self._interfaces[interface.name] is not interface:
            raise ValueError(f"Interface with name '{interface.name}' already exists")
        interface._bind_manager(self)
        self._interfaces[interface.name] = interface
        from femora.components.interface.embedded_beam_solid_interface import (
            EmbeddedBeamSolidInterface,
        )

        if isinstance(interface, EmbeddedBeamSolidInterface):
            self._register_beam_solid_interface()
        return interface

    def beam_solid_interface(
        self,
        *,
        name: str,
        beam_part: MeshPart | str | int,
        solid_parts: List[MeshPart | str | int] | None = None,
        shape: str = "circle",
        radius: float = 0.5,
        radius_y: float | None = None,
        radius_z: float | None = None,
        width: float | None = None,
        height: float | None = None,
        section_points: Sequence[Sequence[float]] | None = None,
        n_peri: int = 8,
        n_long: int = 10,
        penalty_param: float = 1000000000000.0,
        g_penalty: bool = True,
        scale_start: float = 1.0,
        scale_end: float = 1.0,
        selection_margin: float = 0.35,
        _diagnostic_geometry: bool = False,
        _diagnostic_line_mesh: bool = False,
        region: RegionBase | None = None,
        write_connectivity: bool = False,
        write_interface: bool = False,
    ) -> EmbeddedBeamSolidInterface:
        """Create an EmbeddedBeamSolidInterface.

        Args:
            name: Unique name of the contact interface.
            beam_part: The beam part instance, name, or tag.
            solid_parts: Optional list of solid part instances, names, or tags.
            shape: Shape profile of the beam cross-section. Production OpenSees
                export currently supports only "circle". Defaults to "circle".
            radius: Radius of the circular beam interface geometry. Defaults to 0.5.
            radius_y: Internal diagnostic ellipse semi-axis in the local section y direction.
            radius_z: Internal diagnostic ellipse semi-axis in the local section z direction.
            width: Internal diagnostic rectangle width in the local section y direction.
            height: Internal diagnostic rectangle height in the local section z direction.
            section_points: Internal diagnostic polygon vertices as local ``(y, z)`` pairs.
            n_peri: Number of points along the perimeter of the circular section. Defaults to 8.
            n_long: Number of points along the longitudinal axis of the beam. Defaults to 10.
            penalty_param: Penalty stiffness parameter for the constraint. Defaults to 1.0e12.
            g_penalty: If True, uses the geometric penalty formulation. Defaults to True.
            scale_start: Internal diagnostic interface envelope scale at the first
                endpoint of the beam path. Production export requires 1.0.
            scale_end: Internal diagnostic interface envelope scale at the second
                endpoint of the beam path. Production export requires 1.0.
            selection_margin: Fraction of each candidate solid cell bounding radius
                allowed outside the interface envelope during fast solid discovery.
                Smaller values select tighter neighborhoods. Defaults to 0.35.
            _diagnostic_geometry: Internal flag used by visual diagnostics to
                exercise non-exported envelope shapes and tapered discovery.
            _diagnostic_line_mesh: Internal flag used by visual diagnostics to
                allow generic line-cell meshparts that are not export-ready.
            region: Optional region bounding the interface. Not implemented yet.
            write_connectivity: If True, outputs boundary connectivity maps to file. Defaults to False.
            write_interface: If True, outputs boundary mesh surfaces to file. Defaults to False.

        Raises:
            ValueError: If `beam_part` cannot be resolved or if shape is unsupported.
            TypeError: If argument types are invalid (e.g. `beam_part` is not a line mesh).
            NotImplementedError: If unsupported parameter configurations are provided.

        Returns:
            interface (EmbeddedBeamSolidInterface): Registered definition bound to this Model.

        Note:
            The owning mesh-part manager is supplied automatically; callers do not
            provide meshpart. Constructor validation and lifecycle behavior are unchanged.
        """
        from femora.components.interface.embedded_beam_solid_interface import (
            EmbeddedBeamSolidInterface,
        )

        interface = EmbeddedBeamSolidInterface(
            name=name,
            beam_part=beam_part,
            solid_parts=solid_parts,
            shape=shape,
            radius=radius,
            radius_y=radius_y,
            radius_z=radius_z,
            width=width,
            height=height,
            section_points=section_points,
            n_peri=n_peri,
            n_long=n_long,
            penalty_param=penalty_param,
            g_penalty=g_penalty,
            scale_start=scale_start,
            scale_end=scale_end,
            selection_margin=selection_margin,
            _diagnostic_geometry=_diagnostic_geometry,
            _diagnostic_line_mesh=_diagnostic_line_mesh,
            region=region,
            write_connectivity=write_connectivity,
            write_interface=write_interface,
            meshpart=self._mesh_maker.meshpart,
        )
        self.add(interface)
        return interface


    def node_interface(
        self,
        *,
        name: str,
        constrained_node: MeshPart | str | int,
        retained_nodes: List[MeshPart | str | int] | None = None,
        rot: bool = False,
        p: bool = False,
        K: float | None = None,
        KP: float | None = None,
        offset: float | None = None,
        use_mesh_part_points: bool = True,
        normal_filter: ArrayLike | Callable[[np.ndarray, np.ndarray], ArrayLike] | None = None,
        filter_tolerance: float = 0.98,
        contact: bool = False,
        Kn: float = 100000000.0,
        Kt: float = 100000000.0,
        mu: float = 0.5,
        int_type: int = 1,
        area_scaled: bool = False,
    ) -> EmbeddedNodeInterface:
        """Create and register an EmbeddedNodeInterface.

        Args:
            name: Unique name of the node interface.
            constrained_node: The constrained node part instance, name, or tag.
            retained_nodes: Optional list of retained node part instances, names, or tags.
                If None, uses all mesh parts in the model except the constrained node.
            rot: If True, constrains rotational degrees of freedom. Defaults to False.
            p: If True, activates pressure-dof constraints. Defaults to False.
            K: Penalty stiffness parameter for translation constraints.
            KP: Penalty stiffness parameter for rotational constraints.
            offset: Geometric normal offset for locating coupling nodes. Defaults to None.
            use_mesh_part_points: If True, uses mesh part nodal points directly. Defaults to True.
            filter_tolerance: Direction cosine tolerance for the normal filter. Defaults to 0.98.
            contact: If True, creates a frictional ``EmbeddedNodeContact``
                interface. Otherwise, creates a tied ``ASDEmbeddedNodeElement``
                interface. Defaults to False.
            Kn: Normal penalty stiffness for contact. Defaults to 1e8.
            Kt: Tangential penalty stiffness for contact. Defaults to 1e8.
            mu: Friction coefficient for contact. Defaults to 0.5.
            int_type: Contact integration type: 0 for implicit or 1 for
                IMPL-EX. Defaults to 1.
            area_scaled: If True, ``Kn`` and ``Kt`` are stiffnesses per unit area
                (force / length / area) and each contact node receives
                ``Kn * A`` and ``Kt * A``, with ``A`` its tributary area on the
                selected part of the constrained surface. Defaults to False.
            normal_filter: Either a 3-vector (nodes whose surface normal is within
                ``filter_tolerance`` of it) or a function
                ``f(points, normals) -> bool array`` called with the surface points
                and their face normals; see above.

        Raises:
            ValueError: If `offset` is negative or if constrained node matches retained node tag.

        Returns:
            interface (EmbeddedNodeInterface): Registered definition bound to this Model.

        Note:
            The owning mesh-part manager is supplied automatically; callers do not
            provide meshpart. Constructor validation and lifecycle behavior are unchanged.
        """
        from femora.components.interface.embedded_node_interface import EmbeddedNodeInterface

        interface = EmbeddedNodeInterface(
            name=name,
            constrained_node=constrained_node,
            retained_nodes=retained_nodes,
            rot=rot,
            p=p,
            K=K,
            KP=KP,
            offset=offset,
            use_mesh_part_points=use_mesh_part_points,
            normal_filter=normal_filter,
            filter_tolerance=filter_tolerance,
            contact=contact,
            Kn=Kn,
            Kt=Kt,
            mu=mu,
            int_type=int_type,
            area_scaled=area_scaled,
            meshpart=self._mesh_maker.meshpart,
        )
        self.add(interface)
        return interface

    def get(self, name: str) -> Optional[InterfaceBase]:
        """Return a named interface or None without creating one.

        Args:
            name (str): Exact, case-sensitive registry key.
        """
        return self._interfaces.get(name)

    def get_all(self) -> Dict[str, InterfaceBase]:
        """Return a shallow name-to-interface snapshot with shared objects.

        Queued boundary absorber configurations are not included in this mapping.
        """
        return dict(self._interfaces)

    def require(self, name: str) -> InterfaceBase:
        """Require a registered interface by exact name.

        Args:
            name (str): Registry key.

        Raises:
            ValueError: The interface is missing, rather than returning None.
        """
        interface = self._interfaces.get(name)
        if interface is None:
            raise ValueError(f"Interface '{name}' is not registered in InterfaceManager")
        return interface

    def require_registered(self, interface: InterfaceBase) -> InterfaceBase:
        """Validate ownership and exact registered object identity.

        Args:
            interface (InterfaceBase): Object to check.

        Returns:
            interface (InterfaceBase): The unchanged object on success.

        Raises:
            ValueError: Unmanaged, foreign-owned, or not the object registered
                under its current name. This does not validate assembled geometry.
        """
        if interface._owner is None:
            raise ValueError(
                f"Interface '{interface.name}' is not managed by InterfaceManager; "
                "create it with model.interface.beam_solid_interface(...) "
                "or model.interface.node_interface(...)"
            )
        if interface._owner is not self:
            raise ValueError(
                f"Interface '{interface.name}' belongs to a different model's InterfaceManager"
            )
        registered = self._interfaces.get(interface.name)
        if registered is not interface:
            raise ValueError(
                f"Interface '{interface.name}' is not registered in the current InterfaceManager"
            )
        return interface

    def _release_interface(self, interface: InterfaceBase) -> None:
        interface._unsubscribe_events()
        interface._owner = None
        from femora.components.interface.embedded_beam_solid_interface import (
            EmbeddedBeamSolidInterface,
        )

        if isinstance(interface, EmbeddedBeamSolidInterface):
            interface._instance_embeddedinfo_list.clear()
            self._unregister_beam_solid_interface()

    def _register_beam_solid_interface(self) -> None:
        self._beam_solid_count += 1
        if self._beam_solid_count == 1:
            self._ensure_beam_solid_conflict_subscribed()

    def _unregister_beam_solid_interface(self) -> None:
        if self._beam_solid_count <= 0:
            return
        self._beam_solid_count -= 1
        if self._beam_solid_count == 0:
            self._release_beam_solid_conflict_subscription_if_idle()

    def _ensure_beam_solid_conflict_subscribed(self) -> None:
        if self._beam_solid_conflict_subscribed:
            return
        self._mesh_maker.events.subscribe(
            FemoraEvent.RESOLVE_CORE_CONFLICTS,
            self._resolve_beam_solid_conflicts,
        )
        self._beam_solid_conflict_subscribed = True

    def _release_beam_solid_conflict_subscription_if_idle(self) -> None:
        if self._beam_solid_count != 0:
            return
        if not self._beam_solid_conflict_subscribed:
            return
        self._mesh_maker.events.unsubscribe(
            FemoraEvent.RESOLVE_CORE_CONFLICTS,
            self._resolve_beam_solid_conflicts,
        )
        self._beam_solid_conflict_subscribed = False

    def _resolve_beam_solid_conflicts(self, assembled_mesh, **kwargs):
        """Resolve core conflicts across beam-solid EmbeddedInfo collected during assembly."""
        from femora.components.interface.embedded_beam_solid_interface import (
            EmbeddedBeamSolidInterface,
        )
        from femora.components.interface.embedded_info import EmbeddedInfo

        if not any(
            isinstance(interface, EmbeddedBeamSolidInterface)
            for interface in self._interfaces.values()
        ):
            return

        embeddedinfo_list = self._embeddedinfo_list
        if not embeddedinfo_list:
            return  # nothing to do
        # print("resolving core conflicts")
        # ----------------------------------------------------------
        # 1. Deduplicate identical EmbeddedInfo objects
        # ----------------------------------------------------------
        unique_infos: list[EmbeddedInfo] = []
        for info in embeddedinfo_list:
            if all(info != u for u in unique_infos):
                unique_infos.append(info)

        infos = unique_infos
        n = len(infos)

        # ----------------------------------------------------------
        # 2–3. Build similarity graph & detect conflicts
        # ----------------------------------------------------------
        parent = list(range(n))  # union-find structure

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int):
            pi, pj = find(i), find(j)
            if pi != pj:
                parent[pj] = pi

        for i in range(n):
            for j in range(i + 1, n):
                relation = infos[i].compare(infos[j])
                if relation == "conflict":
                    raise ValueError(
                        f"EmbeddedInfo conflict detected between {infos[i]} and {infos[j]}"
                    )
                elif relation == "similar":
                    union(i, j)
                # "equal" already handled via deduplication

        # ----------------------------------------------------------
        # 4. Apply lowest core number per connected component
        # ----------------------------------------------------------
        groups = defaultdict(list)  # root index → list[info index]
        for idx in range(n):
            groups[find(idx)].append(idx)

        for idx_list in groups.values():
            min_core = min(infos[i].core_number for i in idx_list)
            for i in idx_list:
                info = infos[i]
                # Create a new EmbeddedInfo with updated core_number
                new_info = EmbeddedInfo(
                    beams=info.beams, core_number=min_core, beams_solids=info.beams_solids
                )
                infos[i] = new_info
                for idx, orig in enumerate(embeddedinfo_list):
                    if orig == info:
                        embeddedinfo_list[idx] = new_info
                for interface in self._interfaces.values():
                    if not isinstance(interface, EmbeddedBeamSolidInterface):
                        continue
                    inst_list = interface._instance_embeddedinfo_list
                    for idx2, orig2 in enumerate(inst_list):
                        if orig2 == info:
                            inst_list[idx2] = new_info
                for _beams, solids in new_info.beams_solids:
                    try:
                        assembled_mesh.cell_data["Core"][solids] = min_core
                    except Exception as exc:
                        print(
                            f"[EmbeddedBeamSolidInterface] Failed to set core for solids {solids}: {exc}"
                        )
                try:
                    assembled_mesh.cell_data["Core"][list(new_info.beams)] = min_core
                except Exception as exc:
                    print(
                        f"[EmbeddedBeamSolidInterface] Failed to set core for beams {new_info.beams}: {exc}"
                    )

    def remove(self, name: str) -> None:
        """Remove a named definition and release its lifecycle subscriptions.

        Args:
            name (str): Exact key; missing names are ignored.

        This is not a rollback of generated mesh cells or already exported Tcl.
        Rebuild the affected assembly after changing connection definitions.
        """
        interface = self._interfaces.pop(name, None)
        if interface is None:
            return
        self._release_interface(interface)

    def clear(self) -> None:
        """Release all interfaces, generated bookkeeping, and pending boundaries.

        Associated subscriptions are removed. The current assembled mesh and
        solver output files are not reverted or deleted.
        """
        for interface in list(self._interfaces.values()):
            self._release_interface(interface)
        self._interfaces.clear()
        self._embeddedinfo_list.clear()
        self._boundary_absorbers.clear()
        self._release_boundary_absorber_subscription()
