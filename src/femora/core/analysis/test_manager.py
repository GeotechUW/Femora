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

from femora.components.analysis.convergence_tests import (
    EnergyIncrTest,
    FixedNumIterTest,
    NormDispAndUnbalanceTest,
    NormDispIncrTest,
    NormDispOrUnbalanceTest,
    NormUnbalanceTest,
    RelativeEnergyIncrTest,
    RelativeNormDispIncrTest,
    RelativeNormUnbalanceTest,
    RelativeTotalNormDispIncrTest,
)
from femora.core.analysis.test import Test
from femora.core.tagged_component_manager import TaggedComponentManager


class TestManager(TaggedComponentManager[Test]):
    """Create iteration tests through ``model.analysis.test``.

    Factories return registered Test definitions; they do not evaluate a solution
    in Python. Keyword options pass to the matching Components/analysis convergence
    test constructor. Tolerances depend on units, equation scaling, and the chosen
    norm; one tolerance value is not interchangeable across test families.

    max_iter bounds solver iterations, not the number of analysis steps. Print
    flags can change diagnostics and, for some tests, failure handling; consult
    the concrete test before selecting them. A passed test alone does not prove
    physical accuracy, and an explicit linear update may not use iteration tests.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "normunbalance",
            "normdispincr",
            "energyincr",
            "relativenormunbalance",
            "relativenormdispincr",
            "relativetotalnormdispincr",
            "relativeenergyincr",
            "fixednumiter",
            "normdispandunbalance",
            "normdisporunbalance",
        ],
    }

    def __init__(self, analysis_manager: "AnalysisManager") -> None:
        """Initialize the TestManager.

        Args:
            analysis_manager (AnalysisManager): The parent AnalysisManager instance.
        """
        super().__init__(analysis_manager, Test, "_tests")

    def normunbalance(
        self, *, tol: float, max_iter: int, print_flag: int = 0, norm_type: int = 2
    ) -> NormUnbalanceTest:
        """Create a NormUnbalance convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).

        Returns:
            component (NormUnbalanceTest): Registered definition. Creating it does not run OpenSees.
        """
        component = NormUnbalanceTest(
            tol=tol, max_iter=max_iter, print_flag=print_flag, norm_type=norm_type
        )
        self.add(component)
        return component

    def normdispincr(
        self, *, tol: float, max_iter: int, print_flag: int = 0, norm_type: int = 2
    ) -> NormDispIncrTest:
        """Create a NormDispIncr convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).

        Returns:
            component (NormDispIncrTest): Registered definition. Creating it does not run OpenSees.
        """
        component = NormDispIncrTest(
            tol=tol, max_iter=max_iter, print_flag=print_flag, norm_type=norm_type
        )
        self.add(component)
        return component

    def energyincr(self, *, tol: float, max_iter: int, print_flag: int = 0) -> EnergyIncrTest:
        """Create an EnergyIncr convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.

        Returns:
            component (EnergyIncrTest): Registered definition. Creating it does not run OpenSees.
        """
        component = EnergyIncrTest(tol=tol, max_iter=max_iter, print_flag=print_flag)
        self.add(component)
        return component

    def relativenormunbalance(
        self, *, tol: float, max_iter: int, print_flag: int = 0, norm_type: int = 2
    ) -> RelativeNormUnbalanceTest:
        """Create a RelativeNormUnbalance convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).

        Returns:
            component (RelativeNormUnbalanceTest): Registered definition. Creating it does not run OpenSees.
        """
        component = RelativeNormUnbalanceTest(
            tol=tol, max_iter=max_iter, print_flag=print_flag, norm_type=norm_type
        )
        self.add(component)
        return component

    def relativenormdispincr(
        self, *, tol: float, max_iter: int, print_flag: int = 0, norm_type: int = 2
    ) -> RelativeNormDispIncrTest:
        """Create a RelativeNormDispIncr convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).

        Returns:
            component (RelativeNormDispIncrTest): Registered definition. Creating it does not run OpenSees.
        """
        component = RelativeNormDispIncrTest(
            tol=tol, max_iter=max_iter, print_flag=print_flag, norm_type=norm_type
        )
        self.add(component)
        return component

    def relativetotalnormdispincr(
        self, *, tol: float, max_iter: int, print_flag: int = 0, norm_type: int = 2
    ) -> RelativeTotalNormDispIncrTest:
        """Create a RelativeTotalNormDispIncr convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).

        Returns:
            component (RelativeTotalNormDispIncrTest): Registered definition. Creating it does not run OpenSees.
        """
        component = RelativeTotalNormDispIncrTest(
            tol=tol, max_iter=max_iter, print_flag=print_flag, norm_type=norm_type
        )
        self.add(component)
        return component

    def relativeenergyincr(
        self, *, tol: float, max_iter: int, print_flag: int = 0
    ) -> RelativeEnergyIncrTest:
        """Create a RelativeEnergyIncr convergence test.

        Args:
            tol: Tolerance criteria for convergence.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.

        Returns:
            component (RelativeEnergyIncrTest): Registered definition. Creating it does not run OpenSees.
        """
        component = RelativeEnergyIncrTest(tol=tol, max_iter=max_iter, print_flag=print_flag)
        self.add(component)
        return component

    def fixednumiter(self, *, num_iter: int) -> FixedNumIterTest:
        """Create a FixedNumIter convergence test.

        Args:
            num_iter: Exact number of iterations to perform at each step.

        Returns:
            component (FixedNumIterTest): Registered definition. Creating it does not run OpenSees.
        """
        component = FixedNumIterTest(num_iter=num_iter)
        self.add(component)
        return component

    def normdispandunbalance(
        self,
        *,
        tol_incr: float,
        tol_r: float,
        max_iter: int,
        print_flag: int = 0,
        norm_type: int = 2,
        max_incr: int = -1,
    ) -> NormDispAndUnbalanceTest:
        """Create a NormDispAndUnbalance convergence test.

        Args:
            tol_incr: Tolerance for displacement increment norm.
            tol_r: Tolerance for unbalanced force residual norm.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).
            max_incr: Maximum times the error can increase before giving up.
                Use -1 for default.

        Returns:
            component (NormDispAndUnbalanceTest): Registered definition. Creating it does not run OpenSees.
        """
        component = NormDispAndUnbalanceTest(
            tol_incr=tol_incr,
            tol_r=tol_r,
            max_iter=max_iter,
            print_flag=print_flag,
            norm_type=norm_type,
            max_incr=max_incr,
        )
        self.add(component)
        return component

    def normdisporunbalance(
        self,
        *,
        tol_incr: float,
        tol_r: float,
        max_iter: int,
        print_flag: int = 0,
        norm_type: int = 2,
        max_incr: int = -1,
    ) -> NormDispOrUnbalanceTest:
        """Create a NormDispOrUnbalance convergence test.

        Args:
            tol_incr: Tolerance for displacement increment norm.
            tol_r: Tolerance for unbalanced force residual norm.
            max_iter: Maximum number of iterations to perform before returning failure.
            print_flag: Print control flag. 0 prints nothing, 1 prints norm info
                each iteration, 2 prints norms and iterations at success, 4 prints
                norms, displacement, and residual vectors, 5 prints warnings only.
            norm_type: Mathematical norm type to use. 0 for Max-norm, 1 for 1-norm,
                2 for 2-norm (default).
            max_incr: Maximum times the error can increase before giving up.
                Use -1 for default.

        Returns:
            component (NormDispOrUnbalanceTest): Registered definition. Creating it does not run OpenSees.
        """
        component = NormDispOrUnbalanceTest(
            tol_incr=tol_incr,
            tol_r=tol_r,
            max_iter=max_iter,
            print_flag=print_flag,
            norm_type=norm_type,
            max_incr=max_incr,
        )
        self.add(component)
        return component


__all__ = ["TestManager"]
