# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class Load(ABC):
    """Base class for OpenSees load commands emitted inside a ``pattern Plain`` block.

    Load instances do not self-register. A :class:`LoadManager` owns tag assignment
    and lifecycle for a single model context.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    def __init__(self) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None
        self.pattern_tag: Optional[int] = None

    @abstractmethod
    def to_tcl(self) -> str:
        """Render a command intended for the containing Plain pattern block.

        Returns:
            command (str): Concrete load syntax. This abstract contract neither
                supplies a time series nor opens a pattern or runs the solver.
        """
        raise NotImplementedError


__all__ = ["Load"]
