# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from femora.core.material_manager import MaterialManager

from femora.components.material.uniaxial import (
    ElasticUniaxialMaterial,
    Steel01Material,
)


class UniaxialMaterialManager:
    """Create one-dimensional materials through ``model.material.uniaxial``.

    Returned objects belong to the parent MaterialManager and share its name
    and tag space with nD materials. A material definition does not create a
    section, element, mesh, or solver analysis.

    Example:
        ```python
        from femora import Model

        model = Model()
        steel = model.material.uniaxial.elastic(user_name="steel", E=200e6)
        assert steel.tag is not None
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["elastic", "steel01"]}

    def __init__(self, manager: "MaterialManager") -> None:
        self._manager = manager

    @staticmethod
    def _normalize_user_name(kwargs):
        if "name" in kwargs:
            if "user_name" in kwargs:
                raise TypeError("Use only one of 'name' or 'user_name'")
            kwargs["user_name"] = kwargs.pop("name")
        return kwargs

    def elastic(
        self,
        user_name: str = "Unnamed",
        E: float = 1.0,
        eta: float = 0.0,
        Eneg: float | None = None,
        *,
        name: str | None = None,
    ) -> ElasticUniaxialMaterial:
        """Normalize moduli and damping tangent for OpenSees insertion.

        Args:
            user_name: Comment key for Tcl plus manager uniqueness constraint.
            E: Primary tensile or loading stiffness, strictly positive.
            eta: Supplemental damping tangent, non-negative after coercion.
            Eneg: Compression-side stiffness. Falls back to ``E`` when omitted.

        Raises:
            ValueError: If ``E`` is missing.
            ValueError: If ``E``, ``eta``, or ``Eneg`` cannot be converted to numeric values.
            ValueError: If ``E`` or ``Eneg`` is not positive, or if ``eta`` is negative.

        Returns:
            material (ElasticUniaxialMaterial): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = ElasticUniaxialMaterial(
            user_name=user_name if name is None else name, E=E, eta=eta, Eneg=Eneg
        )
        self._manager.add(material)
        return material

    def steel01(
        self,
        user_name: str = "Unnamed",
        *,
        Fy: float | None = None,
        E0: float | None = None,
        b: float | None = None,
        a1: float | None = None,
        a2: float | None = None,
        a3: float | None = None,
        a4: float | None = None,
        name: str | None = None,
    ) -> Steel01Material:
        """Validate yield, stiffness, and optional isotropic hardening inputs.

        Args:
            user_name: Unique Femora and OpenSees material label surfaced in Tcl.
            Fy: Yield strength, strictly positive after coercion.
            E0: Initial elastic modulus, strictly positive.
            b: Post-yield stiffness ratio ``E_ep / E0``, non-negative.
            a1: Isotropic coefficient for compression envelope widening.
            a2: Isotropic exponent paired with ``a1``.
            a3: Isotropic coefficient for tension envelope widening.
            a4: Isotropic exponent paired with ``a3``.

        Raises:
            ValueError: If ``Fy``, ``E0``, or ``b`` is missing.
            ValueError: If a numeric parameter cannot be converted correctly.
            ValueError: If a validated value falls outside the supported range.
            ValueError: If only part of the isotropic hardening set is provided.

        Returns:
            material (Steel01Material): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = Steel01Material(
            user_name=user_name if name is None else name,
            Fy=Fy,
            E0=E0,
            b=b,
            a1=a1,
            a2=a2,
            a3=a3,
            a4=a4,
        )
        self._manager.add(material)
        return material


__all__ = ["UniaxialMaterialManager"]
