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
    from femora.components.element.pml_3d import PML3DElement
    from femora.components.element.ssp_brick import SSPbrickElement
    from femora.components.element.std_brick import stdBrickElement


class BrickElementManager:
    """Create continuum brick definitions through ``model.element.brick``.

    Pass a managed nD material object, preferably from the same Model. Integer
    material tags are resolved through that model's material registry. A string
    is interpreted as an integer tag, not a material name. Component constructors
    validate compatible nodal DOFs and options. Mesh geometry is supplied later
    through ``model.meshpart``.

    Example:
        ```python
        from femora import Model

        model = Model()
        soil = model.material.nd.elastic_isotropic(user_name="soil", E=1e5, nu=0.3, rho=1.8)
        brick = model.element.brick.std(ndof=3, material=soil, b3=-9.81 * 1.8)
        assert brick.get_material() is soil
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["std", "pml3d", "ssp"]}

    def __init__(self, manager: "ElementManager") -> None:
        self._manager = manager

    def std(
        self,
        ndof: int,
        material: Material | int | str,
        *,
        b1: float = 0.0,
        b2: float = 0.0,
        b3: float = 0.0,
        lumped: bool = False,
    ) -> stdBrickElement:
        """Create a stdBrickElement with validated material and body-force inputs.

        Args:
            ndof: Number of DOFs per node. Must be 3 for this element.
            material: Managed 3D ``nDMaterial`` assigned to the brick.
            b1: Constant body force in the global x-direction.
            b2: Constant body force in the global y-direction.
            b3: Constant body force in the global z-direction.
            lumped: When ``True``, export the ``-lumped`` mass-matrix flag.

        Raises:
            ValueError: If the material is incompatible, if ``ndof`` is not 3,
                or if any provided parameter is invalid.

        Returns:
            component (stdBrickElement): Registered definition; no solver is launched.
        """
        from femora.components.element.std_brick import stdBrickElement

        mat = self._manager._resolve_materials(material)
        component = stdBrickElement(ndof, mat, b1=b1, b2=b2, b3=b3, lumped=lumped)
        self._manager.add(component)
        return component

    def pml3d(
        self,
        ndof: int,
        material: Material | int | str,
        *,
        PML_Thickness: float,
        meshType: str,
        meshTypeParameters: list[float] | str,
        gamma: float = 0.5,
        beta: float = 0.25,
        eta: float = 1.0 / 12.0,
        ksi: float = 1.0 / 48.0,
        m: float = 2.0,
        R: float = 1e-08,
        Cp: float | None = None,
        alpha0: float | None = None,
        beta0: float | None = None,
    ) -> PML3DElement:
        """Create a PML3DElement with validated PML and Newmark parameters.

        Args:
            ndof: Number of DOFs per node. Must be 9 for this element.
            material: Managed isotropic elastic 3D ``nDMaterial``.
            PML_Thickness: Thickness of the PML layer.
            meshType: ``box`` or ``general`` mesh type passed to OpenSees.
            meshTypeParameters: Six numeric values or a comma-separated string
                describing the PML mesh orientation.
            gamma: Newmark gamma parameter.
            beta: Newmark beta parameter.
            eta: Newmark eta parameter.
            ksi: Newmark ksi parameter.
            m: PML attenuation parameter when ``alpha0``/``beta0`` are omitted.
            R: PML reflection parameter when ``alpha0``/``beta0`` are omitted.
            Cp: Optional P-wave speed override.
            alpha0: Optional PML alpha parameter; must be paired with ``beta0``.
            beta0: Optional PML beta parameter; must be paired with ``alpha0``.

        Raises:
            ValueError: If the material is incompatible, if ``ndof`` is not 9,
                or if any PML or Newmark parameter is invalid.

        Returns:
            component (PML3DElement): Registered definition; no solver is launched.
        """
        from femora.components.element.pml_3d import PML3DElement

        mat = self._manager._resolve_materials(material)
        component = PML3DElement(
            ndof,
            mat,
            PML_Thickness=PML_Thickness,
            meshType=meshType,
            meshTypeParameters=meshTypeParameters,
            gamma=gamma,
            beta=beta,
            eta=eta,
            ksi=ksi,
            m=m,
            R=R,
            Cp=Cp,
            alpha0=alpha0,
            beta0=beta0,
        )
        self._manager.add(component)
        return component

    def ssp(
        self,
        ndof: int,
        material: Material | int | str,
        *,
        b1: float = 0.0,
        b2: float = 0.0,
        b3: float = 0.0,
    ) -> SSPbrickElement:
        """Create an SSPbrickElement with validated material and body-force inputs.

        Args:
            ndof: Number of DOFs per node. Must be 3 for this element.
            material: Managed 3D ``nDMaterial`` assigned to the brick.
            b1: Constant body force in the global x-direction.
            b2: Constant body force in the global y-direction.
            b3: Constant body force in the global z-direction.

        Raises:
            ValueError: If the material is incompatible, if ``ndof`` is not 3,
                or if any provided parameter is invalid.

        Returns:
            component (SSPbrickElement): Registered definition; no solver is launched.
        """
        from femora.components.element.ssp_brick import SSPbrickElement

        mat = self._manager._resolve_materials(material)
        component = SSPbrickElement(ndof, mat, b1=b1, b2=b2, b3=b3)
        self._manager.add(component)
        return component


__all__ = ["BrickElementManager"]
