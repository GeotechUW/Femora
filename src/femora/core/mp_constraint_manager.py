# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from femora.components.constraint.mp_constraints import EqualDOF
    from femora.components.constraint.mp_constraints import RigidDiaphragm
    from femora.components.constraint.mp_constraints import RigidLink
    from femora.core.constraint_manager import ConstraintManager

from femora.core.constraint_base import MPConstraint
from femora.core.tagging import CompactRetagPolicy
from pykdtree.kdtree import KDTree
import numpy as np


class MPConstraintManager:
    """Create kinematic couplings through ``model.constraint.mp``.

    Unlike SP fixity flags, ``dofs`` here lists one-based DOF numbers to couple.
    Explicit factories accept solver node tags. Geometry-derived helpers require
    final assembly and register constraints using its current node numbering.
    Rebuild those constraints if assembly or exported node origins change.

    Example:
        ```python
        from femora import Model

        model = Model()
        coupling = model.constraint.mp.equal_dof(1, [2], [1, 2, 3])
        assert model.constraint.mp.get(coupling.tag) is coupling
        assert "equalDOF" in coupling.to_tcl()
        ```

    Note:
        Registration does not verify node existence or prevent conflicting
        coupling chains. Select an appropriate analysis constraint handler.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "equal_dof",
            "rigid_link",
            "rigid_diaphragm",
            "laminar_boundary",
            "equal_dof_between_meshparts",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
            "to_tcl",
        ],
    }

    def __init__(self, owner: "ConstraintManager") -> None:
        from femora.core.constraint_manager import ConstraintManager as ConstraintManagerClass

        if not isinstance(owner, ConstraintManagerClass):
            raise TypeError("owner must be a ConstraintManager instance")
        if getattr(owner, "mp", None) is not None:
            raise ValueError("constraint manager already owns MP constraints")

        self._owner = owner
        self._mesh_maker = owner._mesh_maker
        self._constraints: Dict[int, MPConstraint] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[MPConstraint]()

    @staticmethod
    def _extract_surface_compat(mesh):
        """Return a surface mesh across PyVista versions."""
        try:
            return mesh.extract_surface(algorithm="dataset_surface")
        except TypeError:
            return mesh.extract_surface()

    def __len__(self) -> int:
        return len(self._constraints)

    def __iter__(self):
        return iter(self._constraints.values())

    def add(self, constraint: MPConstraint) -> MPConstraint:
        """Register an MP object and return it with a manager-assigned tag.

        Args:
            constraint (MPConstraint): Unmanaged object or one already owned here.

        Raises:
            TypeError: Input is not an MPConstraint.
            ValueError: Ownership or registry-tag conflict.
        """
        if not isinstance(constraint, MPConstraint):
            raise TypeError("constraint must be an MPConstraint instance")
        if constraint._owner is None:
            constraint._owner = self
        elif constraint._owner is not self:
            raise ValueError("constraint already belongs to another manager")
        try:
            constraint.tag = self._tagging.assign_tag(
                self._constraints, constraint, self._start_tag
            )
        except ValueError as exc:
            raise ValueError(f"Constraint tag {constraint.tag} already exists") from exc
        self._constraints[constraint.tag] = constraint
        return constraint

    def equal_dof(self, master_node: int, slave_nodes: List[int], dofs: List[int]) -> EqualDOF:
        """Register equal-DOF coupling between explicit solver nodes.

        Args:
            master_node (int): Retained solver node tag.
            slave_nodes (list[int]): Constrained solver node tags.
            dofs (list[int]): One-based DOF numbers, not fixity flags.

        Returns:
            constraint (EqualDOF): Registered coupling definition.
        """
        from femora.components.constraint.mp_constraints import EqualDOF

        component = EqualDOF(master_node, slave_nodes, dofs)
        self.add(component)
        return component

    def rigid_link(self, type_str: str, master_node: int, slave_nodes: List[int]) -> RigidLink:
        """Register rigid-link coupling between explicit solver nodes.

        Args:
            type_str (str): Link type accepted by RigidLink, such as bar or beam.
            master_node (int): Retained solver node tag.
            slave_nodes (list[int]): Constrained solver node tags.

        Returns:
            constraint (RigidLink): Registered definition. Constructor validation
                errors propagate; geometric and solver compatibility remain required.
        """
        from femora.components.constraint.mp_constraints import RigidLink

        component = RigidLink(type_str, master_node, slave_nodes)
        self.add(component)
        return component

    def rigid_diaphragm(
        self, direction: int, master_node: int, slave_nodes: List[int]
    ) -> RigidDiaphragm:
        """Register a rigid diaphragm using explicit retained/constrained nodes.

        Args:
            direction (int): Direction perpendicular to the diaphragm plane.
            master_node (int): Retained solver node tag.
            slave_nodes (list[int]): Constrained solver node tags.

        Returns:
            constraint (RigidDiaphragm): Registered definition. The factory does
                not select floors or add a retained node/mass automatically.
        """
        from femora.components.constraint.mp_constraints import RigidDiaphragm

        component = RigidDiaphragm(direction, master_node, slave_nodes)
        self.add(component)
        return component

    def laminar_boundary(
        self, dofs: List[int], bounds: Tuple[float, float], direction: int = 3, tol: float = 1e-2
    ) -> None:
        """Register equal-DOF couplings on boundary coordinate layers.

        Args:
            dofs (list[int]): One-based DOF numbers to couple.
            bounds (tuple[float, float]): Included coordinate interval along direction.
            direction (int): Layer-coordinate axis: 1=x, 2=y, or 3=z.
            tol (float): Surface selection and layer-rounding tolerance in length units.

        Returns:
            result (None): Couplings are added to this registry, not returned.

        Raises:
            ValueError: No assembled mesh exists or direction is invalid.

        Note:
            This helper groups selected surface points by rounded coordinates.
            It is not a general soil-boundary generator; inspect the resulting
            constraints and use a positive tolerance.
        """
        if self._mesh_maker.assembled_mesh is None:
            raise ValueError("Assembled mesh is not created yet")

        mesh = self._mesh_maker.assembled_mesh.copy()
        surface = self._extract_surface_compat(mesh)
        xmin, xmax, ymin, ymax, zmin, zmax = surface.bounds
        eps = tol
        if direction == 3:
            xmin += eps
            xmax -= eps
            ymin += eps
            ymax -= eps
            zmin -= eps
            zmax += eps
        elif direction == 2:
            xmin += eps
            xmax -= eps
            ymin -= eps
            ymax += eps
            zmin += eps
            zmax -= eps
        elif direction == 1:
            xmin -= eps
            xmax += eps
            ymin += eps
            ymax -= eps
            zmin += eps
            zmax -= eps
        else:
            raise ValueError("Direction must be 1, 2, or 3")

        ind = surface.find_cells_within_bounds((xmin, xmax, ymin, ymax, zmin, zmax))
        surface = surface.extract_cells(ind, invert=True)
        points = surface.points
        tolerance = tol

        kdtree = KDTree(mesh.points)
        distances, indices = kdtree.query(points, k=1)
        nodeTags = indices + self._mesh_maker.get_start_node_tag()

        z = points[:, direction - 1]

        boundmin = bounds[0]
        boundmax = bounds[1]
        mask = (z >= boundmin - tolerance) & (z <= boundmax + tolerance)
        z = z[mask]
        nodeTags = nodeTags[mask]
        points = points[mask]

        z_rounded = np.round(z / tolerance) * tolerance
        unique_z, group_ids = np.unique(z_rounded, return_inverse=True)

        Taggroups = [nodeTags[group_ids == i] for i in range(len(unique_z))]

        for group in Taggroups:
            if len(group) > 1:
                for slave in group[1:]:
                    self.equal_dof(master_node=group[0], slave_nodes=[slave], dofs=dofs)

    def equal_dof_between_meshparts(
        self, meshpart_master: str, meshpart_slave: str, dofs: List[int], tol: float = 1e-5
    ) -> None:
        """Couple near-coincident assembled nodes from two registered parts.

        Args:
            meshpart_master (str): Retained mesh-part name.
            meshpart_slave (str): Constrained mesh-part name.
            dofs (list[int]): One-based DOF numbers valid for both definitions.
            tol (float): Maximum nearest-neighbor distance in model length units.

        Returns:
            result (None): Matching pairs are registered as EqualDOF objects.

        Raises:
            ValueError: Assembly/parts/points are missing or requested DOFs are invalid.

        Note:
            Each retained point searches its nearest constrained point. This is
            not a one-to-one matching guarantee or interpolated nonconforming
            interface. Unmatched points are skipped. Keep component nodes
            distinct when they are intended to be connected by these constraints.
        """
        if self._mesh_maker.assembled_mesh is None:
            raise ValueError("Assembled mesh is not created yet")

        master_part = self._mesh_maker.meshpart.get(meshpart_master)
        slave_part = self._mesh_maker.meshpart.get(meshpart_slave)
        if master_part is None:
            raise ValueError(f"MeshPart '{meshpart_master}' not found")
        if slave_part is None:
            raise ValueError(f"MeshPart '{meshpart_slave}' not found")

        ndf_master = master_part.element._ndof
        ndf_slave = slave_part.element._ndof
        max_common = min(ndf_master, ndf_slave)
        if any((d < 1 or d > max_common) for d in dofs):
            raise ValueError(
                f"Requested DOFs {dofs} invalid for master ndf={ndf_master} and slave ndf={ndf_slave}"
            )

        assembled = self._mesh_maker.assembled_mesh.copy()
        points = assembled.points
        master_idx = assembled.extract_values(
            values=master_part.tag, scalars="MeshPartTag_celldata", preference="cell"
        )
        slave_idx = assembled.extract_values(
            values=slave_part.tag, scalars="MeshPartTag_celldata", preference="cell"
        )
        master_idx = master_idx.point_data["vtkOriginalPointIds"]
        slave_idx = slave_idx.point_data["vtkOriginalPointIds"]

        if len(master_idx) != master_part.mesh.n_points:
            print(
                f"Warning: Number of points in master mesh part '{meshpart_master}' "
                f"({master_part.number_of_points}) does not match points found in assembled mesh ({len(master_idx)})."
            )
        if len(slave_idx) != slave_part.mesh.n_points:
            print(
                f"Warning: Number of points in slave mesh part '{meshpart_slave}' "
                f"({slave_part.number_of_points}) does not match points found in assembled mesh ({len(slave_idx)})."
            )

        if master_idx.size == 0:
            raise ValueError(
                f"No points found for master mesh part '{meshpart_master}' in assembled mesh"
            )
        if slave_idx.size == 0:
            raise ValueError(
                f"No points found for slave mesh part '{meshpart_slave}' in assembled mesh"
            )

        master_pts = points[master_idx]
        slave_pts = points[slave_idx]

        tree = KDTree(slave_pts)
        distances, nearest = tree.query(master_pts, k=1)

        start_node_tag = self._mesh_maker.get_start_node_tag()

        for i, (dist, j) in enumerate(zip(distances, nearest)):
            if dist <= tol:
                master_point_idx = int(master_idx[i])
                slave_point_idx = int(slave_idx[j])
                master_node_tag = master_point_idx + start_node_tag
                slave_node_tag = slave_point_idx + start_node_tag
                self.equal_dof(master_node=master_node_tag, slave_nodes=[slave_node_tag], dofs=dofs)

    def get(self, tag: int) -> Optional[MPConstraint]:
        """Return an MP definition by integer-convertible registry tag, or None.

        Args:
            tag (int): Constraint registry key, not a retained/constrained node tag.
        """
        return self._constraints.get(int(tag))

    def get_all(self) -> Dict[int, MPConstraint]:
        """Return a shallow tag-to-constraint snapshot with shared object values."""
        return dict(self._constraints)

    def remove(self, tag: int) -> None:
        """Detach one MP definition and compact surviving registry tags.

        Args:
            tag (int): Current constraint key; absent entries are ignored.

        Node tags inside definitions are unchanged; process references are not repaired.
        """
        constraint = self._constraints.pop(int(tag), None)
        if constraint is not None:
            constraint.tag = None
            constraint._owner = None
            self._reassign_tags()

    def to_tcl(self) -> str:
        """Concatenate registered coupling commands in registry insertion order.

        Returns:
            commands (str): Tcl text, or an empty string for an empty registry.
                Rendering does not enforce constraints or run the solver.
        """
        tcl_str = ""
        for constraint in self._constraints.values():
            tcl_str += constraint.to_tcl()
        return tcl_str

    def clear(self) -> None:
        """Detach all MP definitions and clear their registry tags.

        SP supports, mesh connectivity, and files remain unchanged. No command
        is sent to an existing solver domain.
        """
        for constraint in list(self._constraints.values()):
            constraint.tag = None
            constraint._owner = None
        self._constraints.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive MP registry origin and retag existing definitions.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. Solver node references are not renumbered.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._constraints, self._start_tag)


__all__ = ["MPConstraintManager"]
