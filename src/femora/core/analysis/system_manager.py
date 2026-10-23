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

from femora.components.analysis.systems import (
    BandGeneralSystem,
    BandSPDSystem,
    FullGeneralSystem,
    MPIDiagonalSystem,
    MumpsSystem,
    ProfileSPDSystem,
    SuperLUSystem,
    UmfpackSystem,
)
from femora.core.analysis.system import System
from femora.core.tagged_component_manager import TaggedComponentManager


class SystemManager(TaggedComponentManager[System]):
    """Create linear equation solvers through ``model.analysis.system``.

    Factories return registered System definitions for an Analysis. They do not
    factor a matrix or verify installed solver libraries. Keyword options pass
    to the matching Components/analysis system constructor, whose validation
    errors propagate. Choose matrix symmetry/definiteness, MPI support, and
    memory settings appropriate for the model and constraint handler.

    MPIDiagonal is intended for compatible diagonal explicit formulations, not
    as a drop-in replacement for a general coupled stiffness solver. Registry
    operations affect definitions only, not previously exported analyses.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "fullgeneral",
            "bandgeneral",
            "bandspd",
            "profilespd",
            "superlu",
            "umfpack",
            "mumps",
            "mpidiagonal",
        ],
    }

    def __init__(self, analysis_manager: "AnalysisManager") -> None:
        """Initialize the SystemManager.

        Args:
            analysis_manager (AnalysisManager): The parent AnalysisManager instance.
        """
        super().__init__(analysis_manager, System, "_systems")

    def fullgeneral(self) -> FullGeneralSystem:
        """Create a FullGeneral solver system.

        Returns:
            component (FullGeneralSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = FullGeneralSystem()
        self.add(component)
        return component

    def bandgeneral(self) -> BandGeneralSystem:
        """Create a BandGeneral solver system.

        Returns:
            component (BandGeneralSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = BandGeneralSystem()
        self.add(component)
        return component

    def bandspd(self) -> BandSPDSystem:
        """Create a BandSPD solver system.

        Returns:
            component (BandSPDSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = BandSPDSystem()
        self.add(component)
        return component

    def profilespd(self) -> ProfileSPDSystem:
        """Create a ProfileSPD solver system.

        Returns:
            component (ProfileSPDSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = ProfileSPDSystem()
        self.add(component)
        return component

    def superlu(self) -> SuperLUSystem:
        """Create a SuperLU solver system.

        Returns:
            component (SuperLUSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = SuperLUSystem()
        self.add(component)
        return component

    def umfpack(self, *, lvalue_fact: float | None = None) -> UmfpackSystem:
        """Create a Umfpack sparse solver system.

        Args:
            lvalue_fact: Factor controlling matrix storage reallocation sizing.
                Defaults to None.

        Returns:
            component (UmfpackSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = UmfpackSystem(lvalue_fact=lvalue_fact)
        self.add(component)
        return component

    def mumps(self, *, icntl14: float | None = None, icntl7: int | None = None) -> MumpsSystem:
        """Create a MUMPS direct solver system.

        Args:
            icntl14: Percentage increase in estimated workspace during solver setup.
            icntl7: Ordering symmetric permutation algorithm flag.
                0 for AMD, 1 set by user, 2 AMF, 3 SCOTCH, 4 PORD, 5 Metis,
                6 AMD with QADM, 7 automatic.

        Returns:
            component (MumpsSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = MumpsSystem(icntl14=icntl14, icntl7=icntl7)
        self.add(component)
        return component

    def mpidiagonal(self) -> MPIDiagonalSystem:
        """Add the parallel diagonal solver used by explicit analyses.

        Returns:
            component (MPIDiagonalSystem): Registered definition. Creating it does not run OpenSees.
        """
        component = MPIDiagonalSystem()
        self.add(component)
        return component


__all__ = ["SystemManager"]
