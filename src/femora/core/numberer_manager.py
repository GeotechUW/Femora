# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, TYPE_CHECKING, cast

from femora.core.analysis.numberer import Numberer
import femora.components.analysis.numberers

if TYPE_CHECKING:
    from femora.core.analysis_manager import AnalysisManager
    from femora.components.analysis.numberers import (
        PlainNumberer,
        RCMNumberer,
        AMDNumberer,
        ParallelRCMNumberer,
        ParallelPlainNumberer,
    )


class NumbererManager:
    """Select equation ordering through ``model.analysis.numberer``.

    Each factory caches one object per type in this manager. Repeated calls
    return the same object until clear(). Numberers are not tag-managed here;
    they order equations, not solver node tags or mesh partition ownership.
    Parallel variants require compatible OpenSees/MPI support and do not launch ranks.
    """

    __doc_controls__ = {
        "summary": True,
        "members": ["plain", "rcm", "amd", "parallelrcm", "parallelplain", "clear"],
    }

    def __init__(self, analysis_manager: AnalysisManager) -> None:
        self._analysis_manager = analysis_manager
        self._instances: Dict[str, Numberer] = {}

    def _cached(self, key: str) -> Numberer:
        key = key.lower()
        if key not in self._instances:
            if key not in Numberer._numberers:
                raise ValueError(f"Unknown numberer type: {key}")
            self._instances[key] = Numberer._numberers[key]()
        return self._instances[key]

    def plain(self) -> PlainNumberer:
        """Return the cached Plain equation-numbering definition."""
        return cast("PlainNumberer", self._cached("plain"))

    def rcm(self) -> RCMNumberer:
        """Return the cached reverse Cuthill-McKee equation-ordering definition."""
        return cast("RCMNumberer", self._cached("rcm"))

    def amd(self) -> AMDNumberer:
        """Return the cached approximate minimum-degree ordering definition."""
        return cast("AMDNumberer", self._cached("amd"))

    def parallelrcm(self) -> ParallelRCMNumberer:
        """Return the cached ParallelRCM definition; no MPI processes are allocated."""
        return cast("ParallelRCMNumberer", self._cached("parallelrcm"))

    def parallelplain(self) -> ParallelPlainNumberer:
        """Return the cached ParallelPlain definition; compatible solver support is required."""
        return cast("ParallelPlainNumberer", self._cached("parallelplain"))

    def clear(self) -> None:
        """Empty the cache without mutating numberer objects held by analyses.

        Subsequent factory calls create new instances. This is not a solver
        wipeAnalysis command or a renumbering of an already running domain.
        """
        self._instances.clear()


__all__ = ["NumbererManager"]
