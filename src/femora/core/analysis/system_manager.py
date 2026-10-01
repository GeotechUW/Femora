# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

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
    """Manager for system solvers on the Analysis model."""

    def __init__(self, analysis_manager) -> None:
        """Initialize the SystemManager.

        Args:
            analysis_manager: The parent AnalysisManager instance.
        """
        super().__init__(analysis_manager, System, "_systems")

    def fullgeneral(self, **kwargs) -> System:
        """Add a FullGeneralSystem solver.

        Args:
            **kwargs: Keyword arguments passed to FullGeneralSystem.

        Returns:
            The solver system instance.
        """
        return self.add(FullGeneralSystem(**kwargs))

    def bandgeneral(self, **kwargs) -> System:
        """Add a BandGeneralSystem solver.

        Args:
            **kwargs: Keyword arguments passed to BandGeneralSystem.

        Returns:
            The solver system instance.
        """
        return self.add(BandGeneralSystem(**kwargs))

    def bandspd(self, **kwargs) -> System:
        """Add a BandSPDSystem solver.

        Args:
            **kwargs: Keyword arguments passed to BandSPDSystem.

        Returns:
            The solver system instance.
        """
        return self.add(BandSPDSystem(**kwargs))

    def profilespd(self, **kwargs) -> System:
        """Add a ProfileSPDSystem solver.

        Args:
            **kwargs: Keyword arguments passed to ProfileSPDSystem.

        Returns:
            The solver system instance.
        """
        return self.add(ProfileSPDSystem(**kwargs))

    def superlu(self, **kwargs) -> System:
        """Add a SuperLUSystem solver.

        Args:
            **kwargs: Keyword arguments passed to SuperLUSystem.

        Returns:
            The solver system instance.
        """
        return self.add(SuperLUSystem(**kwargs))

    def umfpack(self, **kwargs) -> System:
        """Add a UmfpackSystem solver.

        Args:
            **kwargs: Keyword arguments passed to UmfpackSystem.

        Returns:
            The solver system instance.
        """
        return self.add(UmfpackSystem(**kwargs))

    def mumps(self, **kwargs) -> System:
        """Add a MumpsSystem solver.

        Args:
            **kwargs: Keyword arguments passed to MumpsSystem.

        Returns:
            The solver system instance.
        """
        return self.add(MumpsSystem(**kwargs))

    def mpidiagonal(self) -> System:
        """Add the parallel diagonal solver used by explicit analyses."""
        return self.add(MPIDiagonalSystem())


__all__ = ["SystemManager"]
