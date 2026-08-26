# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Format-neutral interfaces for recorded analysis results."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import FrozenSet, Optional, Union

import numpy as np


Component = Optional[Union[int, str]]

MESH = "mesh"
POINT_HISTORY = "point_history"
CELL_HISTORY = "cell_history"
POINT_FRAME = "point_frame"
CELL_FRAME = "cell_frame"


class ResultReader(ABC):
    """Interface implemented by each supported recorder format."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    @property
    @abstractmethod
    def capabilities(self) -> FrozenSet[str]:
        """Operations supported by this reader."""

    def supports(self, capability: str) -> bool:
        """Return whether the reader supports an operation."""
        return capability in self.capabilities

    @property
    @abstractmethod
    def times(self) -> Optional[np.ndarray]:
        """Return recorded times, or ``None`` when time was not recorded."""

    @property
    @abstractmethod
    def number_of_steps(self) -> int:
        """Return the number of recorded samples independently of time data."""

    @property
    @abstractmethod
    def available_point_responses(self) -> tuple[str, ...]:
        """Return available transient point-response names."""

    @property
    @abstractmethod
    def available_cell_responses(self) -> tuple[str, ...]:
        """Return available transient cell-response names."""

    @property
    def mesh(self):
        """Return this reader's mesh when geometry is supported."""
        from .exceptions import UnsupportedResultOperation

        raise UnsupportedResultOperation(
            f"{type(self).__name__} does not provide mesh geometry"
        )

    def point_history(
        self,
        response: str,
        point_index: int,
        component: Component = None,
    ) -> np.ndarray:
        """Return one point's response over all recorded times."""
        from .exceptions import UnsupportedResultOperation

        raise UnsupportedResultOperation(
            f"{type(self).__name__} does not provide point histories"
        )

    def cell_history(
        self,
        response: str,
        cell_index: int,
        component: Component = None,
    ) -> np.ndarray:
        """Return one cell's response over all recorded times."""
        from .exceptions import UnsupportedResultOperation

        raise UnsupportedResultOperation(
            f"{type(self).__name__} does not provide cell histories"
        )

    def point_frame(
        self,
        response: str,
        step: int,
        component: Component = None,
    ) -> np.ndarray:
        """Return a point-response field at one recorded step."""
        from .exceptions import UnsupportedResultOperation

        raise UnsupportedResultOperation(
            f"{type(self).__name__} does not provide point fields"
        )

    def cell_frame(
        self,
        response: str,
        step: int,
        component: Component = None,
    ) -> np.ndarray:
        """Return a cell-response field at one recorded step."""
        from .exceptions import UnsupportedResultOperation

        raise UnsupportedResultOperation(
            f"{type(self).__name__} does not provide cell fields"
        )

    def close(self) -> None:
        """Release resources held by the reader."""

    def __enter__(self) -> "ResultReader":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
