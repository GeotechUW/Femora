# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from femora.core.analysis_manager import AnalysisManager

from femora.components.analysis.integrators import (
    ArcLengthIntegrator,
    CentralDifferenceIntegrator,
    DisplacementControlIntegrator,
    ExplicitDifferenceIntegrator,
    GeneralizedAlphaIntegrator,
    HHTIntegrator,
    LoadControlIntegrator,
    MinUnbalDispNormIntegrator,
    NewmarkIntegrator,
    ParallelDisplacementControlIntegrator,
    PFEMIntegrator,
    TRBDF2Integrator,
)
from femora.core.analysis.integrator import Integrator, StaticIntegrator, TransientIntegrator
from femora.core.tagged_component_manager import TaggedComponentManager


class IntegratorManager(TaggedComponentManager[Integrator]):
    """Create integration definitions through ``model.analysis.integrator``.

    Static families control load/displacement increments in equilibrium steps;
    transient families advance response in model time. Factories register objects
    and forward keyword arguments to the corresponding Components/analysis
    integrator constructor. No solver step is taken during construction.

    Match the family to the Analysis type. Explicit schemes require a suitable
    mass matrix and a verified stable time step; successful registration cannot
    determine either. Numerical damping and unconditional stability claims must
    be interpreted under each scheme's assumptions, not as a guarantee of accuracy.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "loadcontrol",
            "displacementcontrol",
            "paralleldisplacementcontrol",
            "minunbaldispnorm",
            "arclength",
            "centraldifference",
            "newmark",
            "hht",
            "generalizedalpha",
            "trbdf2",
            "explicitdifference",
            "pfem",
            "get_static_types",
            "get_transient_types",
        ],
    }

    def __init__(self, analysis_manager: "AnalysisManager") -> None:
        """Initialize the IntegratorManager.

        Args:
            analysis_manager (AnalysisManager): The parent AnalysisManager instance.
        """
        super().__init__(analysis_manager, Integrator, "_integrators")

    def loadcontrol(
        self,
        *,
        incr: float,
        num_iter: int = 1,
        min_incr: float | None = None,
        max_incr: float | None = None,
    ) -> LoadControlIntegrator:
        """Create a LoadControl static integrator.

        Args:
            incr: Load factor increment size.
            num_iter: Desired number of iterations in the solution algorithm.
            min_incr: Minimum allowable load factor increment size. Defaults to `incr`.
            max_incr: Maximum allowable load factor increment size. Defaults to `incr`.

        Returns:
            component (LoadControlIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = LoadControlIntegrator(
            incr=incr, num_iter=num_iter, min_incr=min_incr, max_incr=max_incr
        )
        self.add(component)
        return component

    def displacementcontrol(
        self,
        *,
        node_tag: int,
        dof: int,
        incr: float,
        num_iter: int = 1,
        min_incr: float | None = None,
        max_incr: float | None = None,
    ) -> DisplacementControlIntegrator:
        """Create a DisplacementControl static integrator.

        Args:
            node_tag: ID tag of the controlling node.
            dof: Degree of freedom (1-indexed) at the node that controls response.
            incr: Initial displacement increment.
            num_iter: Desired number of iterations in the solution algorithm.
            min_incr: Minimum allowable displacement increment. Defaults to `incr`.
            max_incr: Maximum allowable displacement increment. Defaults to `incr`.

        Returns:
            component (DisplacementControlIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = DisplacementControlIntegrator(
            node_tag=node_tag,
            dof=dof,
            incr=incr,
            num_iter=num_iter,
            min_incr=min_incr,
            max_incr=max_incr,
        )
        self.add(component)
        return component

    def paralleldisplacementcontrol(
        self,
        *,
        node_tag: int,
        dof: int,
        incr: float,
        num_iter: int = 1,
        min_incr: float | None = None,
        max_incr: float | None = None,
    ) -> ParallelDisplacementControlIntegrator:
        """Create a ParallelDisplacementControl static integrator.

        Args:
            node_tag: ID tag of the controlling node.
            dof: Degree of freedom (1-indexed) at the node that controls response.
            incr: Initial displacement increment.
            num_iter: Desired number of iterations in the solution algorithm.
            min_incr: Minimum allowable displacement increment. Defaults to `incr`.
            max_incr: Maximum allowable displacement increment. Defaults to `incr`.

        Returns:
            component (ParallelDisplacementControlIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = ParallelDisplacementControlIntegrator(
            node_tag=node_tag,
            dof=dof,
            incr=incr,
            num_iter=num_iter,
            min_incr=min_incr,
            max_incr=max_incr,
        )
        self.add(component)
        return component

    def minunbaldispnorm(
        self,
        *,
        dlambda1: float,
        jd: int = 1,
        min_lambda: float | None = None,
        max_lambda: float | None = None,
        det: bool = False,
    ) -> MinUnbalDispNormIntegrator:
        """Create a MinUnbalDispNorm static integrator.

        Args:
            dlambda1: First load increment size.
            jd: Desired number of iterations per step.
            min_lambda: Minimum allowable load increment size. Defaults to `dlambda1`.
            max_lambda: Maximum allowable load increment size. Defaults to `dlambda1`.
            det: If True, uses the determinant of the tangent matrix for step sizing.

        Returns:
            component (MinUnbalDispNormIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = MinUnbalDispNormIntegrator(
            dlambda1=dlambda1, jd=jd, min_lambda=min_lambda, max_lambda=max_lambda, det=det
        )
        self.add(component)
        return component

    def arclength(self, *, s: float, alpha: float) -> ArcLengthIntegrator:
        """Create an ArcLength static integrator.

        Args:
            s: The arc-length parameter constraint.
            alpha: Scaling parameter on the reference load vector.

        Returns:
            component (ArcLengthIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = ArcLengthIntegrator(s=s, alpha=alpha)
        self.add(component)
        return component

    def centraldifference(self) -> CentralDifferenceIntegrator:
        """Create a CentralDifference transient integrator.

        Returns:
            component (CentralDifferenceIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = CentralDifferenceIntegrator()
        self.add(component)
        return component

    def newmark(self, *, gamma: float, beta: float, form: str = "D") -> NewmarkIntegrator:
        """Create a Newmark transient integrator.

        Args:
            gamma: Gamma dynamic integration parameter.
            beta: Beta dynamic integration parameter.
            form: Primary formulation variable. 'D' for displacement (default),
                'V' for velocity, or 'A' for acceleration.

        Raises:
            ValueError: If form is not 'D', 'V', or 'A'.

        Returns:
            component (NewmarkIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = NewmarkIntegrator(gamma=gamma, beta=beta, form=form)
        self.add(component)
        return component

    def hht(
        self, *, alpha: float, gamma: float | None = None, beta: float | None = None
    ) -> HHTIntegrator:
        """Create an HHT transient integrator.

        Args:
            alpha: Alpha integration parameter.
            gamma: Gamma integration parameter. Defaults to `1.5 - alpha`.
            beta: Beta integration parameter. Defaults to `(2 - alpha)**2 / 4`.

        Returns:
            component (HHTIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = HHTIntegrator(alpha=alpha, gamma=gamma, beta=beta)
        self.add(component)
        return component

    def generalizedalpha(
        self,
        *,
        alpha_m: float,
        alpha_f: float,
        gamma: float | None = None,
        beta: float | None = None,
    ) -> GeneralizedAlphaIntegrator:
        """Create a GeneralizedAlpha transient integrator.

        Args:
            alpha_m: Alpha_M parameter.
            alpha_f: Alpha_F parameter.
            gamma: Gamma parameter. Defaults to `0.5 + alpha_m - alpha_f`.
            beta: Beta parameter. Defaults to `(1.0 + alpha_m - alpha_f)**2 / 4.0`.

        Returns:
            component (GeneralizedAlphaIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = GeneralizedAlphaIntegrator(
            alpha_m=alpha_m, alpha_f=alpha_f, gamma=gamma, beta=beta
        )
        self.add(component)
        return component

    def trbdf2(self) -> TRBDF2Integrator:
        """Create a TRBDF2 transient integrator.

        Returns:
            component (TRBDF2Integrator): Registered definition. Creating it does not run OpenSees.
        """
        component = TRBDF2Integrator()
        self.add(component)
        return component

    def explicitdifference(self) -> ExplicitDifferenceIntegrator:
        """Create an ExplicitDifference transient integrator.

        Returns:
            component (ExplicitDifferenceIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = ExplicitDifferenceIntegrator()
        self.add(component)
        return component

    def pfem(self, *, gamma: float = 0.5, beta: float = 0.25) -> PFEMIntegrator:
        """Create a PFEM fluid-structure transient integrator.

        Args:
            gamma: Gamma integration parameter. Defaults to 0.5.
            beta: Beta integration parameter. Defaults to 0.25.

        Returns:
            component (PFEMIntegrator): Registered definition. Creating it does not run OpenSees.
        """
        component = PFEMIntegrator(gamma=gamma, beta=beta)
        self.add(component)
        return component

    def get_static_types(self) -> List[str]:
        """Get available static integrator types.

        Returns:
            A list of static integrator type names.
        """
        return StaticIntegrator.get_static_types()

    def get_transient_types(self) -> List[str]:
        """Get available transient integrator types.

        Returns:
            A list of transient integrator type names.
        """
        return TransientIntegrator.get_transient_types()


__all__ = ["IntegratorManager"]
