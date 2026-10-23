# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import numpy as np

from femora.components.mask.mask_base import ElementMask, MeshIndex, NodeMask
from femora.core.event_bus import FemoraEvent

if TYPE_CHECKING:
    from femora.core.model import Model


class MaskManager:
    """Query an assembled-mesh snapshot through ``model.mask``.

    ``nodes`` and ``elements`` start fluent selections provided by the mask
    components. Access requires assembly. The manager builds a cached index
    from copied mesh data after assembly, or lazily on the first query.

    The index stores mesh identifiers and export tag origins separately; use
    the concrete mask's explicit conversion methods rather than assuming a
    zero-based point/cell identifier is a solver tag.

    Note:
        Direct edits to the live assembled mesh or export tag origins do not
        automatically refresh an existing snapshot. Call ``clear()`` and start
        new queries to rebuild it; previously returned masks keep their snapshot.
        Mask queries do not alter mesh connectivity or apply boundary conditions.
    """

    __doc_controls__ = {"summary": True, "members": ["nodes", "elements", "clear"]}

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._mesh_index: MeshIndex | None = None
        self._events_subscribed = False

    def register_events(self) -> None:
        """Install the internal post-assembly index-refresh subscription.

        Model manages this hook; it is not part of the ordinary query workflow.
        """
        if self._events_subscribed:
            return
        self._mesh_maker.events.subscribe(FemoraEvent.POST_ASSEMBLE, self._handle_post_assemble)
        self._events_subscribed = True

    def unregister_events(self) -> None:
        """Release the internal index-refresh hook during model lifecycle cleanup."""
        if not self._events_subscribed:
            return
        self._mesh_maker.events.unsubscribe(FemoraEvent.POST_ASSEMBLE, self._handle_post_assemble)
        self._events_subscribed = False

    def clear(self) -> None:
        """Drop the cached assembled-mesh index snapshot."""
        self._mesh_index = None

    def _handle_post_assemble(self, **kwargs) -> None:
        grid = kwargs.get("assembled_mesh", self._mesh_maker.assembled_mesh)
        if grid is not None:
            self._mesh_index = self._build_index_from_grid(
                grid.copy(),
                node_tag_start=int(self._mesh_maker._start_nodetag),
                element_tag_start=int(self._mesh_maker._start_ele_tag),
            )
        else:
            self._mesh_index = None

    def _require_index(self) -> MeshIndex:
        # POST_ASSEMBLE normally builds the cache; this path covers direct access
        # after assembly when the index has not been populated yet.
        if self._mesh_index is None:
            grid = self._mesh_maker.assembled_mesh
            if grid is None:
                raise RuntimeError(
                    "Mask requires an assembled mesh; call assembler.assemble() first"
                )
            self._mesh_index = self._build_index_from_grid(
                grid.copy(),
                node_tag_start=int(self._mesh_maker._start_nodetag),
                element_tag_start=int(self._mesh_maker._start_ele_tag),
            )
        return self._mesh_index

    @property
    def nodes(self) -> NodeMask:
        """Start a NodeMask containing all nodes of the cached mesh snapshot.

        Raises:
            RuntimeError: No assembled mesh is available to build an index.

        A new selection object is returned for each access, sharing the cached
        index. Query methods are documented on the concrete NodeMask component.
        """
        mesh = self._require_index()
        return NodeMask(mesh, mesh.node_ids)

    @property
    def elements(self) -> ElementMask:
        """Start an ElementMask containing all elements of the cached snapshot.

        Raises:
            RuntimeError: No assembled mesh is available to build an index.

        The returned selection shares the index, not the live mutable mesh.
        Inspect ElementMask's identifier/tag conventions before exporting selections.
        """
        mesh = self._require_index()
        return ElementMask(mesh, mesh.element_ids)

    @staticmethod
    def _build_index_from_grid(
        grid,
        *,
        node_tag_start: int = 1,
        element_tag_start: int = 1,
    ) -> MeshIndex:
        node_coords = np.asarray(grid.points)
        node_ids = np.arange(node_coords.shape[0], dtype=int)
        node_ndf = np.asarray(
            grid.point_data.get("ndf", np.zeros((node_coords.shape[0],), dtype=int))
        )

        ncells = int(grid.n_cells)
        elem_tags = grid.cell_data.get("ElementTag")
        element_ids = (
            np.asarray(elem_tags, dtype=int)
            if elem_tags is not None
            else np.arange(ncells, dtype=int)
        )

        offsets = np.asarray(grid.offset)
        connectivity = np.asarray(grid.cell_connectivity)
        conn_list: List[np.ndarray] = []
        for i, start in enumerate(offsets):
            end = int(offsets[i + 1]) if i + 1 < len(offsets) else int(connectivity.size)
            conn_list.append(connectivity[start:end].astype(int, copy=False))

        element_centroids = np.asarray(grid.cell_centers().points)
        element_types = np.asarray(getattr(grid, "celltypes", np.zeros((ncells,), dtype=int)))
        material_tags = np.asarray(grid.cell_data.get("MaterialTag", np.zeros(ncells, dtype=int)))
        section_tags = np.asarray(grid.cell_data.get("SectionTag", np.zeros(ncells, dtype=int)))
        region_tags = np.asarray(grid.cell_data.get("Region", np.zeros(ncells, dtype=int)))
        core_ids = np.asarray(grid.cell_data.get("Core", np.zeros(ncells, dtype=int)))

        node_core_map: List[List[int]] = [list() for _ in range(node_ids.size)]
        elem_id_to_index: Dict[int, int] = {}
        for idx, eid in enumerate(element_ids.tolist()):
            elem_id_to_index[int(eid)] = idx
            pid = int(core_ids[idx])
            for nidx in conn_list[idx].tolist():
                if pid not in node_core_map[int(nidx)]:
                    node_core_map[int(nidx)].append(pid)

        return MeshIndex(
            node_ids=node_ids,
            node_coords=node_coords,
            element_ids=element_ids,
            element_connectivity=conn_list,
            element_centroids=element_centroids,
            element_types=element_types,
            material_tags=material_tags,
            section_tags=section_tags,
            region_tags=region_tags,
            core_ids=core_ids,
            node_ndf=node_ndf,
            node_core_map=node_core_map,
            element_id_to_index=elem_id_to_index,
            node_tag_start=node_tag_start,
            element_tag_start=element_tag_start,
        )
