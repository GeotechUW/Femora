# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class AnalysisComponent(ABC):
    """Extension contract for an OpenSees solution-stack definition.

    Concrete algorithms, handlers, systems, tests, and integrators render their
    commands through to_tcl(). Prefer ``model.analysis`` factory namespaces for
    ordinary construction. Component registry tags are Python bookkeeping, not
    model node/cell IDs or proof of solver-build support.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    def __init__(self) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None

    @abstractmethod
    def to_tcl(self) -> str:
        """Return the concrete solver configuration command without executing it.

        Returns:
            command (str): Tcl supplied by the subclass. This base does not
                configure an active solver or perform an analysis step.
        """
        raise NotImplementedError


__all__ = ["AnalysisComponent"]
