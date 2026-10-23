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
    from femora.core.section_base import Section
    from femora.core.transformation_base import GeometricTransformation
    from femora.components.element.disp_beam_column import DispBeamColumnElement
    from femora.components.element.elastic_beam_column import ElasticBeamColumnElement
    from femora.components.element.force_beam_column import ForceBeamColumnElement
    from femora.components.element.truss import TrussElement


class BeamElementManager:
    """Create beam-column and truss definitions through ``model.element.beam``.

    Pass a section object or section tag, and for beam-columns a managed
    transformation object or integer tag. Transformation names are unsupported.
    All returned definitions enter the parent ElementManager's registry. Creating
    a definition does not create a line mesh, connectivity, or boundary conditions.

    Example:
        ```python
        from femora import Model

        model = Model()
        section = model.section.beam.elastic(
            user_name="beam", E=200e6, G=77e6, A=0.01,
            Iy=1e-4, Iz=1e-4, J=2e-4,
        )
        transform = model.transformation.transformation3d("Linear", 0, 0, 1)
        beam = model.element.beam.disp(
            ndof=6, section=section, transformation=transform, numIntgrPts=5,
        )
        assert beam.get_section() is section
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["elastic", "disp", "force", "truss"]}

    def __init__(self, manager: "ElementManager") -> None:
        self._manager = manager

    def elastic(
        self,
        ndof: int,
        section: Section | int | str,
        transformation: GeometricTransformation | int,
        *,
        massDens: float = 0.0,
        cMass: bool = False,
    ) -> ElasticBeamColumnElement:
        """Create an ElasticBeamColumnElement with validated dependencies.

        Args:
            ndof: Number of DOFs per node. Must be 3 for 2D or 6 for 3D.
            section: Managed section object defining axial and bending stiffness.
            transformation: Managed geometric transformation defining the local
                element axis.
            massDens: Optional mass per unit length for dynamic analyses.
            cMass: When ``True``, use a consistent mass matrix.

        Raises:
            ValueError: If ``ndof`` is unsupported, if the section or
                transformation is missing, if mass density is negative, or if
                dependencies cannot be resolved.

        Returns:
            component (ElasticBeamColumnElement): Registered definition; no solver is launched.
        """
        from femora.components.element.elastic_beam_column import ElasticBeamColumnElement

        sec = self._manager._resolve_section(section)
        transf = self._manager._resolve_transformation(transformation)
        component = ElasticBeamColumnElement(ndof, sec, transf, massDens=massDens, cMass=cMass)
        self._manager.add(component)
        return component

    def disp(
        self,
        ndof: int,
        section: Section | int | str,
        transformation: GeometricTransformation | int,
        *,
        numIntgrPts: int = 5,
        massDens: float = 0.0,
    ) -> DispBeamColumnElement:
        """Create a DispBeamColumnElement with validated dependencies.

        Args:
            ndof: Number of DOFs per node. Must be 3 for 2D or 6 for 3D.
            section: Managed section object integrated along the member.
            transformation: Managed geometric transformation defining the local
                element axis.
            numIntgrPts: Number of Gauss integration points along the element.
            massDens: Optional mass per unit length for dynamic analyses.

        Raises:
            ValueError: If ``ndof`` is unsupported, if the section or
                transformation is missing, if integration-point or mass inputs
                are invalid, or if dependencies cannot be resolved.

        Returns:
            component (DispBeamColumnElement): Registered definition; no solver is launched.
        """
        from femora.components.element.disp_beam_column import DispBeamColumnElement

        sec = self._manager._resolve_section(section)
        transf = self._manager._resolve_transformation(transformation)
        component = DispBeamColumnElement(
            ndof, sec, transf, numIntgrPts=numIntgrPts, massDens=massDens
        )
        self._manager.add(component)
        return component

    def force(
        self,
        ndof: int,
        section: Section | int | str,
        transformation: GeometricTransformation | int,
        *,
        numIntgrPts: int = 5,
        massDens: float = 0.0,
        maxIters: int = 10,
        tol: float = 1e-12,
    ) -> ForceBeamColumnElement:
        """Create a ForceBeamColumnElement with validated dependencies.

        Args:
            ndof: Number of DOFs per node. Must be 3 for 2D or 6 for 3D.
            section: Managed section object integrated along the member.
            transformation: Managed geometric transformation defining the local
                element axis.
            numIntgrPts: Number of Gauss integration points along the element.
            massDens: Optional mass per unit length for dynamic analyses.
            maxIters: Maximum number of internal compatibility iterations.
            tol: Convergence tolerance for compatibility iteration.

        Raises:
            ValueError: If ``ndof`` is unsupported, if the section or
                transformation is missing, if integration, mass, or iteration
                inputs are invalid, or if dependencies cannot be resolved.

        Returns:
            component (ForceBeamColumnElement): Registered definition; no solver is launched.
        """
        from femora.components.element.force_beam_column import ForceBeamColumnElement

        sec = self._manager._resolve_section(section)
        transf = self._manager._resolve_transformation(transformation)
        component = ForceBeamColumnElement(
            ndof,
            sec,
            transf,
            numIntgrPts=numIntgrPts,
            massDens=massDens,
            maxIters=maxIters,
            tol=tol,
        )
        self._manager.add(component)
        return component

    def truss(
        self,
        ndof: int,
        section: Section | int | str,
        rho: float = 0.0,
        cMass: int = 0,
        doRayleigh: int = 0,
    ) -> TrussElement:
        """Create a TrussElement with validated section and mass options.

        Args:
            ndof: Number of nodal DOFs in the surrounding model (2, 3, or 6).
            section: Managed section object defining axial stiffness and area.
            rho: Optional mass per unit length.
            cMass: Consistent mass flag, ``0`` or ``1``.
            doRayleigh: Rayleigh damping flag, ``0`` or ``1``.

        Raises:
            ValueError: If inputs are invalid or the section cannot be resolved.

        Returns:
            component (TrussElement): Registered definition; no solver is launched.
        """
        from femora.components.element.truss import TrussElement

        sec = self._manager._resolve_section(section)
        component = TrussElement(ndof, section=sec, rho=rho, cMass=cMass, doRayleigh=doRayleigh)
        self._manager.add(component)
        return component


__all__ = ["BeamElementManager"]
