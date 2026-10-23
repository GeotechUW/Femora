# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from femora.core.model import Model

from femora.core.mp_constraint_manager import MPConstraintManager
from femora.core.sp_constraint_manager import SpConstraintManager


class ConstraintManager:
    """Organize boundary and coupling constraints through ``model.constraint``.

    Attributes:
        sp (SpConstraintManager): Single-point support/fixity definitions.
        mp (MPConstraintManager): Multipoint kinematic coupling definitions.

    Constraint definitions are exported with the model; creating one does not
    immediately constrain a running solver. Use solver node tags, not zero-based
    PyVista point indices, for explicit node references. Geometry-derived MP
    helpers require an assembled mesh. Analysis constraint handlers are a
    separate namespace under ``model.analysis.constraint``.

    Example:
        ```python
        from femora import Model

        model = Model()
        support = model.constraint.sp.fix(node_tag=1, dofs=[1, 1, 1])
        assert model.constraint.sp.get(support.tag) is support
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["clear", "set_tag_start"]}

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "constraint", None)
        if isinstance(existing_manager, ConstraintManager):
            raise ValueError("mesh_maker already owns a constraint manager")
        self._mesh_maker = mesh_maker
        mesh_maker.constraint = self
        self.mp = MPConstraintManager(self)
        self.sp = SpConstraintManager(self)

    def clear(self) -> None:
        """Detach and clear both SP and MP constraint collections.

        Meshes and solver files are retained. Existing process references to
        removed constraints are not automatically edited.
        """
        self.mp.clear()
        self.sp.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set and apply the tag origin independently to SP and MP registries.

        Args:
            start_tag (int): Positive origin validated by each registry.

        Raises:
            ValueError: Invalid origin. Constraint tags are registry identities,
                not the solver node tags referenced by the constraints.
        """
        self.mp.set_tag_start(start_tag)
        self.sp.set_tag_start(start_tag)


__all__ = ["ConstraintManager"]
