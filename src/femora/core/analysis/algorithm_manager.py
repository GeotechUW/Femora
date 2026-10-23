# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from femora.core.analysis_manager import AnalysisManager

from femora.components.analysis.algorithms import (
    BFGSAlgorithm,
    BroydenAlgorithm,
    ExpressNewtonAlgorithm,
    KrylovNewtonAlgorithm,
    LinearAlgorithm,
    ModifiedNewtonAlgorithm,
    NewtonAlgorithm,
    NewtonLineSearchAlgorithm,
    SecantNewtonAlgorithm,
)
from femora.core.analysis.algorithm import Algorithm
from femora.core.tagged_component_manager import TaggedComponentManager


class AlgorithmManager(TaggedComponentManager[Algorithm]):
    """Create solution algorithms through ``model.analysis.algorithm``.

    Factories register command definitions, not active solver algorithms. Pass
    the returned object to an analysis factory. Keyword parameters are forwarded
    unchanged to the matching Components/analysis algorithm constructor; its
    validation errors propagate. Inherited registry methods manage only this
    family, and clearing it does not repair analyses referencing its objects.

    Example:
        ```python
        from femora import Model

        model = Model()
        algorithm = model.analysis.algorithm.modifiednewton(factor_once=True)
        assert "ModifiedNewton" in algorithm.to_tcl()
        ```

    No algorithm selection or iteration limit guarantees physical equilibrium,
    nonlinear convergence, or explicit time-step stability for an arbitrary model.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "linear",
            "newton",
            "modifiednewton",
            "newtonlinesearch",
            "krylovnewton",
            "secantnewton",
            "bfgs",
            "broyden",
            "expressnewton",
        ],
    }

    def __init__(self, analysis_manager: "AnalysisManager") -> None:
        super().__init__(analysis_manager, Algorithm, "_algorithms")

    def linear(self, *, initial: bool = False, factor_once: bool = False) -> LinearAlgorithm:
        """Create a Linear solution algorithm.

        Args:
            initial: If True, uses the initial structural stiffness matrix.
            factor_once: If True, sets up and factors the matrix only once.

        Returns:
            component (LinearAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = LinearAlgorithm(initial=initial, factor_once=factor_once)
        self.add(component)
        return component

    def newton(
        self, *, initial: bool = False, initial_then_current: bool = False
    ) -> NewtonAlgorithm:
        """Create a Newton-Raphson solution algorithm.

        Args:
            initial: If True, uses the initial stiffness matrix throughout the iterations.
            initial_then_current: If True, uses initial stiffness for the first iteration,
                and then reforms the tangent stiffness for subsequent iterations.

        Raises:
            ValueError: If both initial and initial_then_current are set to True.

        Returns:
            component (NewtonAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = NewtonAlgorithm(initial=initial, initial_then_current=initial_then_current)
        self.add(component)
        return component

    def modifiednewton(
        self, *, initial: bool = False, factor_once: bool = False
    ) -> ModifiedNewtonAlgorithm:
        """Create a Modified Newton solution algorithm.

        Args:
            initial: If True, uses initial stiffness iterations.
            factor_once: If True, factorizes the stiffness matrix only once.

        Returns:
            component (ModifiedNewtonAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = ModifiedNewtonAlgorithm(initial=initial, factor_once=factor_once)
        self.add(component)
        return component

    def newtonlinesearch(
        self,
        *,
        type_search: str = "InitialInterpolated",
        tol: float = 0.8,
        max_iter: int = 10,
        min_eta: float = 0.1,
        max_eta: float = 10.0,
    ) -> NewtonLineSearchAlgorithm:
        """Create a Newton Line Search solution algorithm.

        Args:
            type_search: Line search algorithm type. Must be one of
                `'Bisection'`, `'Secant'`, `'RegulaFalsi'`, or `'InitialInterpolated'`.
            tol: Tolerance for the line search convergence.
            max_iter: Maximum number of line search iterations per step.
            min_eta: Minimum scaling factor limit.
            max_eta: Maximum scaling factor limit.

        Raises:
            ValueError: If type_search is not a valid line search type.

        Returns:
            component (NewtonLineSearchAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = NewtonLineSearchAlgorithm(
            type_search=type_search, tol=tol, max_iter=max_iter, min_eta=min_eta, max_eta=max_eta
        )
        self.add(component)
        return component

    def krylovnewton(
        self, *, tang_iter: str = "current", tang_incr: str = "current", max_dim: int = 3
    ) -> KrylovNewtonAlgorithm:
        """Create a Krylov-Newton solution algorithm.

        Args:
            tang_iter: Tangent to iterate on. Must be `'current'`, `'initial'`, or `'noTangent'`.
            tang_incr: Tangent to increment on. Must be `'current'`, `'initial'`, or `'noTangent'`.
            max_dim: Max number of subspace iterations before reforming the tangent.

        Raises:
            ValueError: If tang_iter or tang_incr is not a valid option.

        Returns:
            component (KrylovNewtonAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = KrylovNewtonAlgorithm(tang_iter=tang_iter, tang_incr=tang_incr, max_dim=max_dim)
        self.add(component)
        return component

    def secantnewton(
        self, *, tang_iter: str = "current", tang_incr: str = "current", max_dim: int = 3
    ) -> SecantNewtonAlgorithm:
        """Create a Secant-Newton solution algorithm.

        Args:
            tang_iter: Tangent to iterate on. Must be `'current'`, `'initial'`, or `'noTangent'`.
            tang_incr: Tangent to increment on. Must be `'current'`, `'initial'`, or `'noTangent'`.
            max_dim: Max number of iterations before reforming the tangent.

        Raises:
            ValueError: If tang_iter or tang_incr is not a valid option.

        Returns:
            component (SecantNewtonAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = SecantNewtonAlgorithm(tang_iter=tang_iter, tang_incr=tang_incr, max_dim=max_dim)
        self.add(component)
        return component

    def bfgs(self, *, count: int) -> BFGSAlgorithm:
        """Create a BFGS solution algorithm.

        Args:
            count: Number of iterations before reforming the tangent stiffness matrix.

        Raises:
            ValueError: If count is not a positive integer.

        Returns:
            component (BFGSAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = BFGSAlgorithm(count=count)
        self.add(component)
        return component

    def broyden(self, *, count: int) -> BroydenAlgorithm:
        """Create a Broyden solution algorithm.

        Args:
            count: Number of iterations before reforming the tangent stiffness matrix.

        Raises:
            ValueError: If count is not a positive integer.

        Returns:
            component (BroydenAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = BroydenAlgorithm(count=count)
        self.add(component)
        return component

    def expressnewton(
        self,
        *,
        iter_count: int = 2,
        k_multiplier: float = 1.0,
        initial_tangent: bool = False,
        current_tangent: bool = True,
        factor_once: bool = False,
    ) -> ExpressNewtonAlgorithm:
        """Create an Express Newton solution algorithm.

        Args:
            iter_count: Constant number of iterations to perform.
            k_multiplier: Multiplier factor for system stiffness.
            initial_tangent: If True, uses initial stiffness matrix.
            current_tangent: If True, uses current tangent stiffness matrix.
            factor_once: If True, factors system stiffness only once.

        Raises:
            ValueError: If iter_count is not positive, or if both initial_tangent
                and current_tangent are set to True.

        Returns:
            component (ExpressNewtonAlgorithm): Registered definition. Creating it does not run OpenSees.
        """
        component = ExpressNewtonAlgorithm(
            iter_count=iter_count,
            k_multiplier=k_multiplier,
            initial_tangent=initial_tangent,
            current_tangent=current_tangent,
            factor_once=factor_once,
        )
        self.add(component)
        return component


__all__ = ["AlgorithmManager"]
