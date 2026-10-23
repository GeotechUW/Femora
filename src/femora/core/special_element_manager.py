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
    from femora.components.element.asd_embedded_node import ASDEmbeddedNodeElement3D
    from femora.components.element.embedded_node_contact import EmbeddedNodeContact3D
    from femora.components.element.ghost_node import GhostNodeElement
    from femora.components.element.zero_length_contact import ZeroLengthContactASDimplex


class SpecialElementManager:
    """Create auxiliary/contact definitions through ``model.element.special``.

    Each factory registers a reusable definition in the parent ElementManager.
    It does not find contact surfaces, construct connectivity, or install a
    node/beam-solid interface. Use component-specific documentation to select
    compatible DOFs, geometry, penalty parameters, and solver capabilities.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "ghost_node",
            "asd_embedded_node",
            "embedded_node_contact",
            "zero_length_contact",
        ],
    }

    def __init__(self, manager: "ElementManager") -> None:
        self._manager = manager

    def ghost_node(self, ndof: int) -> GhostNodeElement:
        """Create a GhostNodeElement with merge-protected sentinel DOF metadata.

        Args:
            ndof: Real number of DOFs per node written during Tcl export. Must
                be 3 or 6.

        Raises:
            ValueError: If ``ndof`` is not 3 or 6.

        Returns:
            component (GhostNodeElement): Registered definition; no solver is launched.
        """
        from femora.components.element.ghost_node import GhostNodeElement

        component = GhostNodeElement(ndof)
        self._manager.add(component)
        return component

    def asd_embedded_node(
        self,
        ndof: int,
        *,
        rot: bool = False,
        p: bool = False,
        K: float | None = None,
        KP: float | None = None,
    ) -> ASDEmbeddedNodeElement3D:
        """Create an ASDEmbeddedNodeElement3D with validated constraint options.

        Args:
            ndof: Number of DOFs per node. Must be 3, 4, or 6.
            rot: Whether to constrain rotational DOFs at the embedded node.
            p: Whether to constrain pressure DOFs.
            K: Optional user-defined penalty stiffness for displacement
                constraints.
            KP: Optional user-defined penalty stiffness for pressure
                constraints.

        Raises:
            ValueError: If ``ndof`` is unsupported.

        Returns:
            component (ASDEmbeddedNodeElement3D): Registered definition; no solver is launched.
        """
        from femora.components.element.asd_embedded_node import ASDEmbeddedNodeElement3D

        component = ASDEmbeddedNodeElement3D(ndof, rot=rot, p=p, K=K, KP=KP)
        self._manager.add(component)
        return component

    def embedded_node_contact(
        self,
        ndof: int,
        Kn: float,
        Kt: float,
        mu: float,
        *,
        orient: list[float] | tuple[float, float, float] | None = None,
        orient_map: dict[int, list[float]] | None = None,
        int_type: int = 0,
    ) -> EmbeddedNodeContact3D:
        """Register an embedded-node contact definition.

        Args:
            ndof (int): Nodal degrees of freedom.
            Kn (float): Normal penalty parameter in consistent component units.
            Kt (float): Tangential penalty parameter.
            mu (float): Friction coefficient.
            orient (list[float] | tuple[float, float, float] | None): Contact normal.
            orient_map (dict[int, list[float]] | None): Per-element normal overrides.
            int_type (int): Contact integration selector.

        Returns:
            element (EmbeddedNodeContact3D): Registered definition. Penalty
                calibration, connectivity, and time-step stability remain the
                modeler's responsibility; constructor errors propagate.

        """
        from femora.components.element.embedded_node_contact import EmbeddedNodeContact3D

        component = EmbeddedNodeContact3D(
            ndof=ndof,
            Kn=Kn,
            Kt=Kt,
            mu=mu,
            orient=orient,
            orient_map=orient_map,
            int_type=int_type,
        )
        self._manager.add(component)
        return component

    def zero_length_contact(
        self,
        ndof: int,
        Kn: float,
        Kt: float,
        mu: float,
        *,
        material: Material | None = None,
        orient: list[float] | None = None,
        intType: int = 0,
    ) -> ZeroLengthContactASDimplex:
        """Create a ZeroLengthContactASDimplex element with validated contact inputs.

        Args:
            ndof: Number of DOFs per node in the surrounding model (2, 3, 4,
                or 6).
            Kn: Normal contact penalty stiffness. Must be positive.
            Kt: Tangential contact penalty stiffness. Must be positive.
            mu: Mohr-Coulomb friction coefficient. Must be non-negative.
            material: Unused placeholder accepted for base-class compatibility.
            orient: Optional contact orientation vector ``[nx, ny, nz]``.
            intType: Contact integration type (``0`` implicit, ``1`` IMPL-EX).

        Raises:
            ValueError: If ``ndof`` is unsupported or if contact parameters are
                invalid.

        Returns:
            component (ZeroLengthContactASDimplex): Registered definition; no solver is launched.
        """
        from femora.components.element.zero_length_contact import ZeroLengthContactASDimplex

        component = ZeroLengthContactASDimplex(
            ndof=ndof, Kn=Kn, Kt=Kt, mu=mu, material=material, orient=orient, intType=intType
        )
        self._manager.add(component)
        return component


__all__ = ["SpecialElementManager"]
