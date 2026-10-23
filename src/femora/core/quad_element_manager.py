# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from femora.core.element_manager import ElementManager
    from femora.core.material_base import Material
    from femora.components.element.ssp_quad import SSPQuadElement


class QuadElementManager:
    """Create quadrilateral definitions through ``model.element.quad``.

    The factory registers a reusable element definition, not a surface mesh.
    Supply a compatible nD material and create geometry separately through
    ``model.meshpart``. Prefer objects from the same model over stored tags.
    """

    __doc_controls__ = {"summary": True, "members": ["ssp"]}

    def __init__(self, manager: "ElementManager") -> None:
        self._manager = manager

    def ssp(
        self,
        ndof: int,
        material: Material | int | str,
        *,
        Type: str,
        Thickness: float,
        b1: float = 0.0,
        b2: float = 0.0,
    ) -> SSPQuadElement:
        """Create an SSPQuadElement with validated material and geometry inputs.

        Args:
            ndof: Number of DOFs per node. Must be 2 for this element.
            material: Managed 2D ``nDMaterial`` assigned to the quadrilateral.
            Type: ``PlaneStrain`` or ``PlaneStress`` formulation flag.
            Thickness: Element thickness in the out-of-plane direction.
            b1: Constant body force in the global x-direction.
            b2: Constant body force in the global y-direction.

        Raises:
            ValueError: If the material is incompatible, if ``ndof`` is not 2,
                or if any parameter is missing or invalid.

        Returns:
            component (SSPQuadElement): Registered definition; no solver is launched.
        """
        from femora.components.element.ssp_quad import SSPQuadElement

        mat = self._manager._resolve_materials(material)
        component = SSPQuadElement(ndof, mat, Type=Type, Thickness=Thickness, b1=b1, b2=b2)
        self._manager.add(component)
        return component


__all__ = ["QuadElementManager"]
