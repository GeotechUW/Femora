# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from femora.components.constraint.sp_constraints import FixConstraint
    from femora.components.constraint.sp_constraints import FixMacroX_max
    from femora.components.constraint.sp_constraints import FixMacroX_min
    from femora.components.constraint.sp_constraints import FixMacroY_max
    from femora.components.constraint.sp_constraints import FixMacroY_min
    from femora.components.constraint.sp_constraints import FixMacroZ_max
    from femora.components.constraint.sp_constraints import FixMacroZ_min
    from femora.components.constraint.sp_constraints import FixXConstraint
    from femora.components.constraint.sp_constraints import FixYConstraint
    from femora.components.constraint.sp_constraints import FixZConstraint
    from femora.core.constraint_manager import ConstraintManager

from femora.core.constraint_base import SPConstraint
from femora.core.tagging import CompactRetagPolicy


class SpConstraintManager:
    """Create supports through ``model.constraint.sp``.

    ``dofs`` in these factories is a fixity flag vector: one entry per nodal
    DOF, with 1 fixed and 0 free. It is not a list of DOF numbers. Coordinate
    factories emit solver selection commands; macro factories use model-boundary
    variables generated during export. Creation alone does not test whether
    the selected nodes exist or whether the supports stabilize the model.

    Example:
        ```python
        from femora import Model

        model = Model()
        support = model.constraint.sp.fix(1, [1, 1, 1])
        assert "fix 1" in support.to_tcl()
        ```
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "fix",
            "fix_x",
            "fix_y",
            "fix_z",
            "fix_macro_x_min",
            "fix_macro_x_max",
            "fix_macro_y_min",
            "fix_macro_y_max",
            "fix_macro_z_min",
            "fix_macro_z_max",
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
        if getattr(owner, "sp", None) is not None:
            raise ValueError("constraint manager already owns SP constraints")

        self._owner = owner
        self._constraints: Dict[int, SPConstraint] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[SPConstraint]()

    def __len__(self) -> int:
        return len(self._constraints)

    def __iter__(self):
        return iter(self._constraints.values())

    def add(self, constraint: SPConstraint) -> SPConstraint:
        """Register an SP object, returning it with an assigned constraint tag.

        Args:
            constraint (SPConstraint): Unmanaged object or one already owned here.

        Raises:
            TypeError: The object is not an SPConstraint.
            ValueError: Ownership or registry-tag conflict.
        """
        if not isinstance(constraint, SPConstraint):
            raise TypeError("constraint must be a SPConstraint instance")
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

    def fix(self, node_tag: int, dofs: List[int]) -> FixConstraint:
        """Register explicit nodal fixity.

        Args:
            node_tag (int): Solver node tag.
            dofs (list[int]): Per-DOF 0/1 fixity flags.

        Returns:
            constraint (FixConstraint): Registered definition; no solver is run.
        """
        from femora.components.constraint.sp_constraints import FixConstraint

        component = FixConstraint(node_tag, dofs)
        self.add(component)
        return component

    def fix_x(self, xCoordinate: float, dofs: List[int], tol: float = 1e-10) -> FixXConstraint:
        """Register fixity on a constant-global-x plane.

        Args:
            xCoordinate (float): Plane coordinate in model length units.
            dofs (list[int]): Per-DOF 0/1 fixity flags.
            tol (float): Coordinate selection tolerance in length units.

        Returns:
            constraint (FixXConstraint): Deferred coordinate-based constraint.
        """
        from femora.components.constraint.sp_constraints import FixXConstraint

        component = FixXConstraint(xCoordinate, dofs, tol)
        self.add(component)
        return component

    def fix_y(self, yCoordinate: float, dofs: List[int], tol: float = 1e-10) -> FixYConstraint:
        """Register fixity on a constant-global-y plane.

        Args:
            yCoordinate (float): Plane coordinate in model length units.
            dofs (list[int]): Per-DOF 0/1 fixity flags.
            tol (float): Coordinate selection tolerance in length units.

        Returns:
            constraint (FixYConstraint): Deferred coordinate-based constraint.
        """
        from femora.components.constraint.sp_constraints import FixYConstraint

        component = FixYConstraint(yCoordinate, dofs, tol)
        self.add(component)
        return component

    def fix_z(self, zCoordinate: float, dofs: List[int], tol: float = 1e-10) -> FixZConstraint:
        """Register fixity on a constant-global-z plane.

        Args:
            zCoordinate (float): Plane coordinate in model length units.
            dofs (list[int]): Per-DOF 0/1 fixity flags.
            tol (float): Coordinate selection tolerance in length units.

        Returns:
            constraint (FixZConstraint): Deferred coordinate-based constraint.
        """
        from femora.components.constraint.sp_constraints import FixZConstraint

        component = FixZConstraint(zCoordinate, dofs, tol)
        self.add(component)
        return component

    def fix_macro_x_min(self, dofs: List[int], tol: float = 1e-10) -> FixMacroX_min:
        """Register fixity at the exported minimum-x macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroX_min

        component = FixMacroX_min(dofs, tol)
        self.add(component)
        return component

    def fix_macro_x_max(self, dofs: List[int], tol: float = 1e-10) -> FixMacroX_max:
        """Register fixity at the exported maximum-x macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroX_max

        component = FixMacroX_max(dofs, tol)
        self.add(component)
        return component

    def fix_macro_y_min(self, dofs: List[int], tol: float = 1e-10) -> FixMacroY_min:
        """Register fixity at the exported minimum-y macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroY_min

        component = FixMacroY_min(dofs, tol)
        self.add(component)
        return component

    def fix_macro_y_max(self, dofs: List[int], tol: float = 1e-10) -> FixMacroY_max:
        """Register fixity at the exported maximum-y macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroY_max

        component = FixMacroY_max(dofs, tol)
        self.add(component)
        return component

    def fix_macro_z_min(self, dofs: List[int], tol: float = 1e-10) -> FixMacroZ_min:
        """Register fixity at the exported minimum-z macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroZ_min

        component = FixMacroZ_min(dofs, tol)
        self.add(component)
        return component

    def fix_macro_z_max(self, dofs: List[int], tol: float = 1e-10) -> FixMacroZ_max:
        """Register fixity at the exported maximum-z macro boundary.

        Args:
            dofs (list[int]): Per-DOF fixity flags.
            tol (float): Boundary coordinate tolerance in model length units.

        Returns:
            constraint (SPConstraint): Macro definition requiring export context.
        """
        from femora.components.constraint.sp_constraints import FixMacroZ_max

        component = FixMacroZ_max(dofs, tol)
        self.add(component)
        return component

    def get(self, tag: int) -> Optional[SPConstraint]:
        """Return an SP definition by integer-convertible registry tag, or None.

        Args:
            tag (int): Constraint registry tag, not the constrained solver node tag.
        """
        return self._constraints.get(int(tag))

    def get_all(self) -> Dict[int, SPConstraint]:
        """Return a shallow tag-to-definition snapshot with shared object values."""
        return dict(self._constraints)

    def remove(self, tag: int) -> None:
        """Detach a definition and compact surviving constraint registry tags.

        Args:
            tag (int): Current tag; absent tags are ignored. Solver node tags
                stored inside constraints do not change during compaction.
        """
        constraint = self._constraints.pop(int(tag), None)
        if constraint is not None:
            constraint.tag = None
            constraint._owner = None
            self._reassign_tags()

    def to_tcl(self) -> str:
        """Render explicit-node and coordinate-plane fixities grouped by kind.

        This convenience renderer includes Fix/FixX/FixY/FixZ definitions only;
        macro-boundary definitions require the full model export path. It does
        not launch OpenSees or verify selected nodes.
        """
        from femora.components.constraint.sp_constraints import (
            FixConstraint,
            FixXConstraint,
            FixYConstraint,
            FixZConstraint,
        )

        tcl_commands = []
        fix_constraints = []
        fix_x_constraints = []
        fix_y_constraints = []
        fix_z_constraints = []

        for constraint in self._constraints.values():
            if isinstance(constraint, FixConstraint):
                fix_constraints.append(constraint)
            elif isinstance(constraint, FixXConstraint):
                fix_x_constraints.append(constraint)
            elif isinstance(constraint, FixYConstraint):
                fix_y_constraints.append(constraint)
            elif isinstance(constraint, FixZConstraint):
                fix_z_constraints.append(constraint)

        if fix_constraints:
            tcl_commands.append("# Node-specific constraints")
            for constraint in fix_constraints:
                tcl_commands.append(constraint.to_tcl())

        if fix_x_constraints:
            tcl_commands.append("\n# X-coordinate constraints")
            for constraint in fix_x_constraints:
                tcl_commands.append(constraint.to_tcl())

        if fix_y_constraints:
            tcl_commands.append("\n# Y-coordinate constraints")
            for constraint in fix_y_constraints:
                tcl_commands.append(constraint.to_tcl())

        if fix_z_constraints:
            tcl_commands.append("\n# Z-coordinate constraints")
            for constraint in fix_z_constraints:
                tcl_commands.append(constraint.to_tcl())

        return "\n".join(tcl_commands)

    def clear(self) -> None:
        """Detach every SP definition and clear its registry tag.

        MP constraints and model meshes remain unchanged. Exported files and a
        running solver are not affected.
        """
        for constraint in list(self._constraints.values()):
            constraint.tag = None
            constraint._owner = None
        self._constraints.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive SP registry origin and retag existing definitions.

        Args:
            start_tag (int): Positive origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. This does not change solver node numbering.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._constraints, self._start_tag)


__all__ = ["SpConstraintManager"]
