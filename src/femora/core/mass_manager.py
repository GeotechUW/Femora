# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional, Tuple, Union

import numpy as np
from numpy.typing import ArrayLike
from pykdtree.kdtree import KDTree

from femora.constants import FEMORA_MAX_NDF
from femora.core.event_bus import FemoraEvent
from femora.core.meshpart_base import MeshPart

if TYPE_CHECKING:
    from femora.core.model import Model


class MassManager:
    """Model-owned service for assigning nodal mass arrays.

    Mass data lives on mesh parts before assembly and on the assembled mesh
    after assembly. This manager provides convenience helpers that modify those
    arrays without introducing separate mass objects or registries.

    Attributes:
        meshpart: Source-part helpers used before section creation/assembly.
        region: Assembled-node helpers selecting nodes of cells in a region.
        global_: Helpers acting on the current assembled mesh; trailing underscore
            avoids the Python keyword ``global``.

    Mass vectors use nodal DOF order. Entries include translational mass and,
    where relevant, rotary inertia in consistent units. Vectors are flattened,
    zero-padded, or truncated to FEMORA_MAX_NDF and stored as float32; these
    helpers do not reject entries merely because a node has fewer active DOFs.
    They assign the supplied amount per selected node, not a total distributed
    across all nodes. No gravity force is created by assigning mass.

    Example:
        ```python
        from femora import Model

        model = Model()
        soil = model.material.nd.elastic_isotropic(user_name="soil", E=1e5, nu=0.3, rho=1.8)
        brick = model.element.brick.std(ndof=3, material=soil)
        model.meshpart.volume.uniform_rectangular_grid(
            user_name="block", element=brick,
            x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1,
            nx=1, ny=1, nz=1,
        )
        model.mass.meshpart.add_all("block", [1.0, 1.0, 1.0])
        masses = model.mass.get_meshpart_mass_array("block")
        assert masses[0, 0] == 1.0
        ```

    Warning:
        Avoid double-counting element/material and explicit nodal mass. Source
        edits do not update existing section copies, and assembled edits are
        lost when the final mesh is rebuilt. Rebuild affected sections as well
        as the final mesh when source-part masses change after section creation.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "get_meshpart_mass_array",
            "get_assembled_mass_array",
            "clear",
        ],
    }

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._events_subscribed = False
        self._region_point_cache: dict[int, np.ndarray] = {}

        self.meshpart = _MeshPartMassHelper(self)
        self.region = _RegionMassHelper(self)
        self.global_ = _GlobalMassHelper(self)

    def register_events(self) -> None:
        """Install the internal pre-assembly cache invalidation subscription.

        Model manages this lifecycle hook; ordinary scripts should not call it.
        """
        if self._events_subscribed:
            return
        self._mesh_maker.events.subscribe(FemoraEvent.PRE_ASSEMBLE, self._handle_pre_assemble)
        self._events_subscribed = True

    def unregister_events(self) -> None:
        """Release the internal pre-assembly cache hook during model clearing."""
        if not self._events_subscribed:
            return
        self._mesh_maker.events.unsubscribe(FemoraEvent.PRE_ASSEMBLE, self._handle_pre_assemble)
        self._events_subscribed = False

    @staticmethod
    def _pad_mass(vec: ArrayLike, ndf: int) -> np.ndarray:
        """Return a vector of length FEMORA_MAX_NDF with zeros padded / truncated."""
        v = np.asarray(vec, dtype=np.float32).flatten()

        if v.size > FEMORA_MAX_NDF:
            v = v[:FEMORA_MAX_NDF]

        res = np.zeros(FEMORA_MAX_NDF, dtype=np.float32)
        res[: v.size] = v
        return res

    @staticmethod
    def _combine(old: np.ndarray, new: np.ndarray, rule: str) -> np.ndarray:
        if rule == "sum":
            return old + new
        if rule == "override":
            return new
        raise ValueError("combine must be 'sum' or 'override'")

    def _handle_pre_assemble(self, *_, **__):
        """Clear transient region caches before a fresh assembly."""
        self._region_point_cache.clear()

    def clear(self) -> None:
        """Clear manager caches and remove Mass arrays from the current model."""
        self._region_point_cache.clear()

        mesh_maker = self._mesh_maker
        if mesh_maker is None:
            return

        for mp in mesh_maker.meshpart.get_all().values():
            if "Mass" in mp.mesh.point_data:
                del mp.mesh.point_data["Mass"]

        asm = mesh_maker.assembled_mesh
        if asm is not None and "Mass" in asm.point_data:
            del asm.point_data["Mass"]

    def get_meshpart_mass_array(self, meshpart_name: str) -> np.ndarray:
        """Return the live Mass array on a source mesh part, creating zeros if absent.

        Args:
            meshpart_name (str): Exact registered part name.

        Returns:
            masses (np.ndarray): Live float32 array shaped
                ``(part.mesh.n_points, FEMORA_MAX_NDF)``. Mutating it edits source data.

        Raises:
            KeyError: The part is missing. Generated part geometry is required.
        """
        mp = self._mesh_maker.meshpart.get(meshpart_name)
        if mp is None:
            raise KeyError(f"MeshPart '{meshpart_name}' not found")
        _ensure_mass_array(mp)
        return mp.mesh.point_data["Mass"]

    def get_assembled_mass_array(self) -> Optional[np.ndarray]:
        """Return the live final-mesh Mass array, creating zeros when needed.

        Returns:
            masses (np.ndarray | None): Array shaped
                ``(assembled.n_points, FEMORA_MAX_NDF)``, or None without assembly.
                In-place changes affect the current assembled model, not source parts.
        """
        asm = self._mesh_maker.assembled_mesh
        if asm is None:
            return None
        if "Mass" not in asm.point_data:
            asm.point_data["Mass"] = np.zeros((asm.n_points, FEMORA_MAX_NDF), dtype=np.float32)
        return asm.point_data["Mass"]


def _ensure_mass_array(meshpart: MeshPart) -> None:
    if "Mass" not in meshpart.mesh.point_data:
        n = meshpart.mesh.n_points
        meshpart.mesh.point_data["Mass"] = np.zeros((n, FEMORA_MAX_NDF), dtype=np.float32)


class _MeshPartMassHelper:
    """Modify meshpart mass arrays before assembly.

    Meshpart ``Mass`` is authoritative pre-assembly. After assembly, edits
    here are not synced automatically; the user must reassemble manually.
    """

    def __init__(self, manager: MassManager) -> None:
        self._mgr = manager

    def add_all(
        self,
        meshpart_name: str,
        mass_vec: ArrayLike,
        *,
        combine: str = "sum",
        filter_fn: Callable[[int], bool] | None = None,
    ) -> None:
        """Assign a mass vector independently to every selected source-part node.

        Args:
            meshpart_name (str): Exact part name.
            mass_vec (ArrayLike): Per-node mass/inertia vector in nodal DOF order.
            combine (str): ``sum`` adds to stored entries; ``override`` replaces them.
            filter_fn (Callable | None): Optional predicate receiving a local
                zero-based point index; False excludes that point.

        Raises:
            KeyError: Part not found.
            ValueError: Invalid combination rule or vector conversion failure.

        Section copies and final assembled arrays are not updated by this operation.
        """
        mp = self._get_mp(meshpart_name)
        arr = mp.mesh.point_data["Mass"]
        if "ndf" not in mp.mesh.point_data:
            ndf_array = np.full(
                shape=(mp.mesh.n_points,),
                fill_value=mp.element._ndof,
                dtype=np.int8,
            )
        else:
            ndf_array = mp.mesh.point_data["ndf"]
        padded = None
        for idx in range(arr.shape[0]):
            if filter_fn is not None and not filter_fn(idx):
                continue
            ndf = int(ndf_array[idx])
            if padded is None:
                padded = self._mgr._pad_mass(mass_vec, ndf)
            arr[idx] = self._mgr._combine(arr[idx], padded, combine)

    def closest_point(
        self,
        meshpart_name: str,
        xyz: Tuple[float, float, float],
        mass_vec: ArrayLike,
        *,
        combine: str = "sum",
    ) -> int:
        """Assign mass to the nearest point in a source part, without distance cutoff.

        Args:
            meshpart_name (str): Exact part name.
            xyz (tuple[float, float, float]): Query point in model coordinates.
            mass_vec (ArrayLike): Per-node vector in DOF order.
            combine (str): ``sum`` or ``override``.

        Returns:
            index (int): Local zero-based source point index, not a solver node tag.

        Missing/empty mesh and KD-tree or vector errors propagate. Inspect the
        selected location when the query is far from the part.
        """
        mp = self._get_mp(meshpart_name)
        pts = mp.mesh.points
        tree = KDTree(pts)
        _, idx = tree.query(np.asarray(xyz).reshape(1, -1), k=1)
        idx = int(idx[0])
        self.add_nodes(meshpart_name, [idx], [mass_vec], combine=combine)
        return idx

    def add_nodes(
        self,
        meshpart_name: str,
        point_indices: List[int],
        mass_matrix: List[ArrayLike],
        *,
        combine: str = "sum",
    ) -> None:
        """Assign one mass vector per explicitly selected local source point.

        Args:
            meshpart_name (str): Exact part name.
            point_indices (list[int]): Local zero-based point indices, not solver tags.
            mass_matrix (list[ArrayLike]): One vector per index, in matching order.
            combine (str): ``sum`` or ``override``.

        Raises:
            ValueError: Index/vector list lengths differ or combination is invalid.
            KeyError: Part is missing.
            IndexError: An index cannot access the source arrays.

        Uses NumPy indexing semantics; negative indices are not explicitly rejected.
        Duplicate indices apply their operations repeatedly. Updates are not atomic.
        """
        if len(point_indices) != len(mass_matrix):
            raise ValueError("point_indices and mass_matrix must be same length")
        mp = self._get_mp(meshpart_name)
        arr = mp.mesh.point_data["Mass"]
        if "ndf" not in mp.mesh.point_data:
            ndf_array = np.full(
                shape=(mp.mesh.n_points,),
                fill_value=mp.element._ndof,
                dtype=np.int8,
            )
        else:
            ndf_array = mp.mesh.point_data["ndf"]
        for idx, vec in zip(point_indices, mass_matrix):
            ndf = int(ndf_array[idx])
            padded = self._mgr._pad_mass(vec, ndf)
            arr[idx] = self._mgr._combine(arr[idx], padded, combine)

    def _get_mp(self, name: str) -> MeshPart:
        mp = self._mgr._mesh_maker.meshpart.get(name)
        if mp is None:
            raise KeyError(f"MeshPart '{name}' not found")
        _ensure_mass_array(mp)
        return mp


class _RegionMassHelper:
    """Modify final-mesh nodes attached to cells carrying a region tag.

    Access through ``model.mass.region`` after assembly. Selection is based on
    the assembled cell-data Region array, not a separate node-region registry.
    Shared nodes can belong to multiple selections and receive repeated additions.
    """

    def __init__(self, manager: MassManager) -> None:
        self._mgr = manager

    def add_all(
        self,
        region_tag: int,
        mass_vec: ArrayLike,
        *,
        combine: str = "sum",
    ) -> None:
        """Assign a vector to every assembled node incident to region cells.

        Args:
            region_tag (int): Region value present in final cell data.
            mass_vec (ArrayLike): Per-node mass/inertia vector, not a regional total.
            combine (str): ``sum`` or ``override``.

        Raises:
            RuntimeError: No assembled mesh exists.
            KeyError: No cells carry the requested region tag.
            ValueError: Invalid combination rule or vector conversion.
        """
        asm = self._require_assembled()
        point_ids = self._get_region_point_ids(region_tag, asm)
        self._add_to_points(point_ids, mass_vec, asm, combine)

    def closest_point(
        self,
        region_tag: int,
        xyz: Tuple[float, float, float],
        mass_vec: ArrayLike,
        *,
        combine: str = "sum",
    ) -> int:
        """Assign mass at the nearest assembled point incident to region cells.

        Args:
            region_tag (int): Region value in assembled cell data.
            xyz (tuple[float, float, float]): Query location in model coordinates.
            mass_vec (ArrayLike): Nodal mass/inertia vector.
            combine (str): ``sum`` or ``override``.

        Returns:
            index (int): Global assembled point index, not a solver node tag.

        Raises:
            RuntimeError: Model is not assembled.
            KeyError: Region has no assembled cells.

        No maximum search distance is imposed; source-part arrays are unchanged.
        """
        asm = self._require_assembled()
        point_ids = self._get_region_point_ids(region_tag, asm)
        pts = asm.points[point_ids]
        tree = KDTree(pts)
        _, local_idx = tree.query(np.asarray(xyz).reshape(1, -1), k=1)
        global_idx = int(point_ids[int(local_idx[0])])
        self._add_to_points([global_idx], mass_vec, asm, combine)
        return global_idx

    def _require_assembled(self):
        asm = self._mgr._mesh_maker.assembled_mesh
        if asm is None:
            raise RuntimeError("Model must be assembled before using region mass helpers")
        if "Mass" not in asm.point_data:
            asm.point_data["Mass"] = np.zeros((asm.n_points, FEMORA_MAX_NDF), dtype=np.float32)
        return asm

    def _get_region_point_ids(self, region_tag: int, asm):
        if region_tag in self._mgr._region_point_cache:
            return self._mgr._region_point_cache[region_tag]
        cell_ids = np.where(asm.cell_data["Region"] == region_tag)[0]
        if cell_ids.size == 0:
            raise KeyError(f"Region tag {region_tag} not present in assembled mesh")
        offsets = asm.offset
        connectivity = asm.cell_connectivity
        point_set: set[int] = set()
        for cid in cell_ids:
            start = offsets[cid]
            end = offsets[cid + 1]
            point_set.update(connectivity[start:end])
        ids = np.fromiter(point_set, dtype=int)
        self._mgr._region_point_cache[region_tag] = ids
        return ids

    def _add_to_points(
        self,
        point_ids: np.ndarray | List[int],
        mass_vec: ArrayLike,
        asm,
        combine: str,
    ) -> None:
        arr = asm.point_data["Mass"]
        ndf_arr = asm.point_data["ndf"]
        for idx in point_ids:
            ndf = int(ndf_arr[idx])
            vec = self._mgr._pad_mass(mass_vec, ndf)
            arr[idx] = self._mgr._combine(arr[idx], vec, combine)


class _GlobalMassHelper:
    """Modify the current final-mesh Mass array through ``model.mass.global_``.

    Assembly is required. These edits are not propagated to source mesh parts
    and must be reapplied after rebuilding the final mesh.
    """

    def __init__(self, manager: MassManager) -> None:
        self._mgr = manager

    def closest_point(
        self,
        xyz: Tuple[float, float, float],
        mass_vec: ArrayLike,
        *,
        combine: str = "sum",
    ) -> int:
        """Assign a vector at the nearest assembled point without a distance cutoff.

        Args:
            xyz (tuple[float, float, float]): Query location in model coordinates.
            mass_vec (ArrayLike): Nodal mass/inertia vector.
            combine (str): ``sum`` or ``override``.

        Returns:
            index (int): Zero-based assembled point index, not a solver node tag.

        Raises:
            RuntimeError: The model has no assembled mesh.

        KD-tree, vector conversion, and invalid combination errors propagate.
        """
        asm = self._require_assembled()
        pts = asm.points
        tree = KDTree(pts)
        _, idx = tree.query(np.asarray(xyz).reshape(1, -1), k=1)
        idx = int(idx[0])
        self._add_to_points([idx], mass_vec, asm, combine)
        return idx

    def add_all(self, mass_vec: ArrayLike, *, combine: str = "sum") -> None:
        """Assign the same vector independently to every assembled point.

        Args:
            mass_vec (ArrayLike): Per-node mass/inertia vector, not a model total.
            combine (str): ``sum`` adds; ``override`` replaces stored vectors.

        Raises:
            RuntimeError: The model has no assembled mesh.
            ValueError: Invalid combination rule or vector conversion failure.
        """
        asm = self._require_assembled()
        self._add_to_points(np.arange(asm.n_points), mass_vec, asm, combine)

    def _require_assembled(self):
        asm = self._mgr._mesh_maker.assembled_mesh
        if asm is None:
            raise RuntimeError("Model must be assembled before using global mass helpers")
        if "Mass" not in asm.point_data:
            asm.point_data["Mass"] = np.zeros((asm.n_points, FEMORA_MAX_NDF), dtype=np.float32)
        return asm

    def _add_to_points(self, ids, mass_vec, asm, combine) -> None:
        arr = asm.point_data["Mass"]
        ndf_arr = asm.point_data["ndf"]
        for idx in ids:
            ndf = int(ndf_arr[idx])
            vec = self._mgr._pad_mass(mass_vec, ndf)
            arr[idx] = self._mgr._combine(arr[idx], vec, combine)
