# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from femora.core.material_manager import MaterialManager

from femora.components.material.nd import (
    DruckerPragerMaterial,
    ElasticIsotropicMaterial,
    J2CyclicBoundingSurfaceMaterial,
    LinearElasticGGmaxMaterial,
    PressureDependMultiYieldMaterial,
    PressureIndependMultiYieldMaterial,
)


class NDMaterialManager:
    """Create multidimensional materials through ``model.material.nd``.

    Factories construct a concrete material and register it with the parent
    MaterialManager, assigning its tag and enforcing a unique user name.
    Use a consistent stress/density unit system; no unit conversion is applied.
    Component pages describe constitutive parameters and assumptions.

    Example:
        ```python
        from femora import Model

        model = Model()
        soil = model.material.nd.elastic_isotropic(
            user_name="soil", E=108000.0, nu=1.0 / 3.0, rho=1.8,
        )
        assert model.material.get_by_name("soil") is soil
        ```

    Note:
        ``name`` is an explicit compatibility alias for ``user_name``. A supplied
        non-None ``name`` takes precedence; prefer one spelling per call.
        Distinct materials should have distinct names, including when using
        defaults. Registration and constructor validation can raise errors.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "elastic_isotropic",
            "j2_cyclic_bounding_surface",
            "drucker_prager",
            "pressure_depend_multi_yield",
            "linear_elastic_ggmax",
            "pressure_independ_multi_yield",
        ],
    }

    def __init__(self, manager: "MaterialManager") -> None:
        self._manager = manager

    @staticmethod
    def _normalize_user_name(kwargs):
        if "name" in kwargs:
            if "user_name" in kwargs:
                raise TypeError("Use only one of 'name' or 'user_name'")
            kwargs["user_name"] = kwargs.pop("name")
        return kwargs

    def elastic_isotropic(
        self,
        user_name: str = "Unnamed",
        E: float = 1.0,
        nu: float = 0.3,
        rho: float = 0.0,
        *,
        name: str | None = None,
    ) -> ElasticIsotropicMaterial:
        """Create an elastic isotropic material with validated parameters.

        Args:
            user_name: Label included in the emitted Tcl comment and stored by
                the owning material manager.
            E: Young's modulus. Must be a positive numeric value.
            nu: Poisson's ratio. Must be numeric and in the range ``[0, 0.5)``.
            rho: Mass density. Must be a non-negative numeric value.

        Raises:
            ValueError: If ``E`` or ``nu`` is missing, if any numeric parameter
                cannot be converted to ``float``, if ``E`` is not positive, if
                ``nu`` is outside ``[0, 0.5)``, or if ``rho`` is negative.

        Returns:
            material (ElasticIsotropicMaterial): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = ElasticIsotropicMaterial(
            user_name=user_name if name is None else name, E=E, nu=nu, rho=rho
        )
        self._manager.add(material)
        return material

    def j2_cyclic_bounding_surface(
        self,
        user_name: str = "Unnamed",
        *,
        G: float | None = None,
        K: float | None = None,
        Su: float | None = None,
        Den: float | None = None,
        h: float | None = None,
        m: float | None = None,
        h0: float | None = None,
        chi: float | None = None,
        beta: float = 0.5,
        name: str | None = None,
    ) -> J2CyclicBoundingSurfaceMaterial:
        """Create a J2 cyclic bounding surface material with validated parameters.

        Args:
            user_name: Instance label appended to Tcl and stored by the owning manager.
            G: Shear modulus, strictly positive.
            K: Bulk modulus, strictly positive.
            Su: Undrained shear strength, strictly positive.
            Den: Mass density for inertia or body-force coupling, ``>= 0``.
            h: Hardening parameter controlling plastic modulus evolution.
            m: Hardening exponent shaping the nonlinear hardening curve.
            h0: Initial or reference hardening level.
            chi: Viscous damping coefficient used by the OpenSees model.
            beta: Implicit-explicit blending weight on ``[0, 1]``.

        Raises:
            ValueError: If any mandatory parameter is missing.
            ValueError: If a numeric parameter cannot be converted to ``float``.
            ValueError: If ``G``, ``K``, or ``Su`` is not positive, if ``Den``
                is negative, or if ``beta`` falls outside ``[0, 1]``.

        Returns:
            material (J2CyclicBoundingSurfaceMaterial): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = J2CyclicBoundingSurfaceMaterial(
            user_name=user_name if name is None else name,
            G=G,
            K=K,
            Su=Su,
            Den=Den,
            h=h,
            m=m,
            h0=h0,
            chi=chi,
            beta=beta,
        )
        self._manager.add(material)
        return material

    def drucker_prager(
        self,
        user_name: str = "Unnamed",
        *,
        k: float | None = None,
        G: float | None = None,
        sigmaY: float | None = None,
        rho: float | None = None,
        rhoBar: float | None = None,
        Kinf: float | None = None,
        Ko: float | None = None,
        delta1: float | None = None,
        delta2: float | None = None,
        H: float | None = None,
        theta: float | None = None,
        density: float | None = None,
        atmPressure: float | None = None,
        name: str | None = None,
    ) -> DruckerPragerMaterial:
        """Create a Drucker-Prager material object with validated inputs.

        Args:
            user_name: Stored in Tcl suffix comments and enforced unique among
                managed materials.
            k: Bulk modulus analogue in the Tcl command, strictly greater than
                zero.
            G: Shear modulus analogue in the Tcl command, strictly greater than
                zero.
            sigmaY: Initial yield intercept, strictly positive.
            rho: Cohesion-like Drucker-Prager strength parameter, strictly
                positive.
            rhoBar: Optional cap on dilatancy evolution. Defaults to ``rho`` and
                must satisfy ``0 <= rhoBar <= rho``.
            Kinf: Optional long-run isotropic strengthening magnitude, ``>= 0``.
            Ko: Additional isotropic evolution parameter, ``>= 0``.
            delta1: Isotropic modulus expansion coefficient, ``>= 0``.
            delta2: Softening or decay coefficient, ``>= 0``.
            H: Combined hardening modulus, ``>= 0``.
            theta: Blend in ``[0, 1]`` between isotropic and kinematic mechanisms.
            density: Optional mass density, ``>= 0``.
            atmPressure: Reference pressure for modulus updates, ``>= 0``.

        Raises:
            ValueError: If a required parameter is missing.
            ValueError: If a numeric value cannot be converted to ``float``.
            ValueError: If any validated value falls outside the supported interval.

        Returns:
            material (DruckerPragerMaterial): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = DruckerPragerMaterial(
            user_name=user_name if name is None else name,
            k=k,
            G=G,
            sigmaY=sigmaY,
            rho=rho,
            rhoBar=rhoBar,
            Kinf=Kinf,
            Ko=Ko,
            delta1=delta1,
            delta2=delta2,
            H=H,
            theta=theta,
            density=density,
            atmPressure=atmPressure,
        )
        self._manager.add(material)
        return material

    def pressure_depend_multi_yield(
        self,
        user_name: str = "Unnamed",
        *,
        nd: int,
        rho: float,
        refShearModul: float,
        refBulkModul: float,
        frictionAng: float,
        peakShearStra: float,
        refPress: float,
        pressDependCoe: float,
        PTAng: float,
        contrac: float,
        dilat1: float,
        dilat2: float,
        liquefac1: float,
        liquefac2: float,
        liquefac3: float,
        e: float = 0.6,
        cs1: float = 0.9,
        cs2: float = 0.02,
        cs3: float = 0.7,
        pa: float = 101.0,
        c: float = 0.3,
        noYieldSurf: int = 20,
        pairs: list[float] | list[tuple[float, float]] | None = None,
        name: str | None = None,
    ) -> PressureDependMultiYieldMaterial:
        """Construct the material from keyword arguments matching OpenSees naming.

        Args:
            user_name: Label placed in the trailing Tcl comment once managed.
            nd: Spatial dimension flag, either ``2`` or ``3``.
            rho: Saturated mass density, strictly positive in model units.
            refShearModul: Reference low-strain shear modulus at ``refPress``.
            refBulkModul: Reference bulk modulus at ``refPress``.
            frictionAng: Peak friction angle in degrees.
            peakShearStra: Octahedral shear strain at peak strength, strictly positive.
            refPress: Reference mean effective stress, strictly positive.
            pressDependCoe: Non-negative confinement dependence coefficient.
            PTAng: Phase-transformation angle in degrees.
            contrac: Contractive plasticity parameter.
            dilat1: First dilatancy parameter.
            dilat2: Second dilatancy parameter.
            liquefac1: Liquefaction parameter 1.
            liquefac2: Liquefaction parameter 2.
            liquefac3: Liquefaction parameter 3.
            noYieldSurf: Surface count or negative custom-backbone selector.
            pairs: Custom backbone data required when ``noYieldSurf < 0``.
            e: Optional void ratio, default ``0.6``.
            cs1: Optional critical-state coefficient, default ``0.9``.
            cs2: Optional critical-state coefficient, default ``0.02``.
            cs3: Optional critical-state coefficient, default ``0.7``.
            pa: Optional atmospheric or reference pressure, default ``101.0``.
            c: Optional cohesion-like intercept, default ``0.3``.

        Raises:
            ValueError: If a supplied parameter fails component validation.
            ValueError: If a numeric Tcl argument cannot be converted correctly.
            ValueError: If any validated value falls outside the supported range.

        Returns:
            material (PressureDependMultiYieldMaterial): Registered material with a model-local tag.

        Note:
            name overrides user_name when non-None. Missing required keywords and
            unknown keywords raise TypeError at this factory boundary.
        """
        material = PressureDependMultiYieldMaterial(
            user_name=user_name if name is None else name,
            nd=nd,
            rho=rho,
            refShearModul=refShearModul,
            refBulkModul=refBulkModul,
            frictionAng=frictionAng,
            peakShearStra=peakShearStra,
            refPress=refPress,
            pressDependCoe=pressDependCoe,
            PTAng=PTAng,
            contrac=contrac,
            dilat1=dilat1,
            dilat2=dilat2,
            liquefac1=liquefac1,
            liquefac2=liquefac2,
            liquefac3=liquefac3,
            e=e,
            cs1=cs1,
            cs2=cs2,
            cs3=cs3,
            pa=pa,
            c=c,
            noYieldSurf=noYieldSurf,
            pairs=pairs,
        )
        self._manager.add(material)
        return material

    def linear_elastic_ggmax(
        self,
        user_name: str = "Unnamed",
        *,
        G: float | None = None,
        K_or_nu: float | None = None,
        rho: float = 0.0,
        curveType: int = 1,
        pairs: Sequence[tuple[float, float]] | Sequence[float] | None = None,
        param1: float | None = None,
        param2: float | None = None,
        param3: float | None = None,
        name: str | None = None,
    ) -> LinearElasticGGmaxMaterial:
        """Create a LinearElasticGGmax material with backbone validation rules.

        Args:
            user_name: Unique label referenced in Tcl export comments under
                the owning material manager.
            G: Small-strain shear modulus ``G_max``, strictly greater than zero.
            K_or_nu: Interpreted by OpenSees as Poisson's ratio in the special
                range, otherwise as bulk modulus.
            rho: Saturated density for mass coupling, required to be non-negative.
            curveType: Integer backbone selector ``{0, 1, 2, 3}``.
            pairs: User-defined backbone data for ``curveType == 0``, either as
                a sequence of ``(gamma, G/Gmax)`` tuples or a flattened
                sequence ``[gamma1, GG1, gamma2, GG2, ...]``.
            param1: Curve-specific scalar used by built-in backbone types.
            param2: Darendeli-specific parameter used when ``curveType == 3``.
            param3: Darendeli-specific parameter used when ``curveType == 3``.

        Raises:
            ValueError: If ``G`` or ``K_or_nu`` is missing.
            ValueError: If ``rho`` is negative or ``curveType`` is unsupported.
            ValueError: If user-defined backbone data are malformed.

        Returns:
            material (LinearElasticGGmaxMaterial): Registered material with a model-local tag.

        Note:
            The keyword-only name alias overrides user_name when non-None.
            Unknown keywords are rejected; component validation remains authoritative.
        """
        material = LinearElasticGGmaxMaterial(
            user_name=user_name if name is None else name,
            G=G,
            K_or_nu=K_or_nu,
            rho=rho,
            curveType=curveType,
            pairs=pairs,
            param1=param1,
            param2=param2,
            param3=param3,
        )
        self._manager.add(material)
        return material

    def pressure_independ_multi_yield(
        self,
        user_name: str = "Unnamed",
        *,
        nd: int,
        rho: float,
        refShearModul: float,
        refBulkModul: float,
        cohesi: float,
        peakShearStra: float,
        frictionAng: float = 0.0,
        refPress: float = 100.0,
        pressDependCoe: float = 0.0,
        noYieldSurf: int = 20,
        pairs: list[float] | list[tuple[float, float]] | None = None,
        name: str | None = None,
    ) -> PressureIndependMultiYieldMaterial:
        """Validate soil keyword arguments before storing them for Tcl export.

        Args:
            user_name: Comment annotation and manager registry key.
            nd: ``2`` or ``3`` dimensional analysis flag.
            rho: Saturated density, strictly positive.
            refShearModul: Reference small-strain shear modulus, strictly positive.
            refBulkModul: Reference bulk modulus, strictly positive.
            cohesi: Apparent cohesion intercept, non-negative.
            peakShearStra: Octahedral shear strain marker for peak strength.
            frictionAng: Friction angle in degrees. Defaults to ``0`` when omitted.
            refPress: Positive reference mean stress. Defaults to ``100``.
            pressDependCoe: Non-negative confinement scaling coefficient.
            noYieldSurf: Surface count or negative backbone selector.
            pairs: Mandatory custom backbone list when ``noYieldSurf < 0``.

        Raises:
            ValueError: If a supplied parameter fails component validation.
            ValueError: If a numeric value cannot be converted correctly.
            ValueError: If any validated value falls outside the supported range.
            ValueError: If ``pairs`` is malformed or invalid when required.

        Returns:
            material (PressureIndependMultiYieldMaterial): Registered material with a model-local tag.

        Note:
            name overrides user_name when non-None. Missing required keywords and
            unknown keywords raise TypeError at this factory boundary.
        """
        material = PressureIndependMultiYieldMaterial(
            user_name=user_name if name is None else name,
            nd=nd,
            rho=rho,
            refShearModul=refShearModul,
            refBulkModul=refBulkModul,
            cohesi=cohesi,
            peakShearStra=peakShearStra,
            frictionAng=frictionAng,
            refPress=refPress,
            pressDependCoe=pressDependCoe,
            noYieldSurf=noYieldSurf,
            pairs=pairs,
        )
        self._manager.add(material)
        return material


__all__ = ["NDMaterialManager"]
