# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Logical result collections spanning one or more recorder files."""

from __future__ import annotations

from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

import numpy as np

from .base import Component, ResultReader
from .exceptions import ResultFormatError, UnsupportedResultOperation
from .registry import ResultReaderRegistry, reader_registry


PathInput = Union[str, Path]


@dataclass(frozen=True)
class PointSelection:
    """A point selected from one file in a logical result set."""

    partition: int
    index: int
    coordinate: tuple[float, float, float]
    distance: float


class ResultSet:
    """Present serial or partitioned recorder files through one interface."""

    def __init__(self, readers: Sequence[ResultReader]) -> None:
        if not readers:
            raise ValueError("ResultSet requires at least one reader")
        self.readers = tuple(readers)
        self._times: Optional[np.ndarray] = None
        self._times_loaded = False

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(reader.path for reader in self.readers)

    @property
    def number_of_partitions(self) -> int:
        return len(self.readers)

    @property
    def times(self) -> Optional[np.ndarray]:
        if not self._times_loaded:
            reference = self.readers[0].times
            for reader in self.readers[1:]:
                candidate = reader.times
                if reference is None or candidate is None:
                    if reference is not None or candidate is not None:
                        raise ResultFormatError(
                            "Some partitioned files contain time values and others do not"
                        )
                    continue
                if reference.shape != candidate.shape or not np.allclose(
                    reference,
                    candidate,
                    rtol=1.0e-9,
                    atol=1.0e-12,
                ):
                    raise ResultFormatError(
                        "Partitioned result files do not share the same recorded times"
                    )
            self._times = reference
            self._times_loaded = True
        return self._times

    @property
    def number_of_steps(self) -> int:
        reference = self.readers[0].number_of_steps
        if any(reader.number_of_steps != reference for reader in self.readers[1:]):
            raise ResultFormatError(
                "Partitioned result files do not contain the same number of steps"
            )
        return reference

    @property
    def available_point_responses(self) -> tuple[str, ...]:
        return self._common_responses("available_point_responses")

    @property
    def available_cell_responses(self) -> tuple[str, ...]:
        return self._common_responses("available_cell_responses")

    def _common_responses(self, attribute: str) -> tuple[str, ...]:
        common = set(getattr(self.readers[0], attribute))
        for reader in self.readers[1:]:
            common.intersection_update(getattr(reader, attribute))
        return tuple(sorted(common))

    def supports(self, capability: str) -> bool:
        return all(reader.supports(capability) for reader in self.readers)

    def mesh(self, partition: int = 0, *, copy: bool = False):
        """Return one partition mesh."""
        mesh = self.readers[partition].mesh
        return mesh.copy(deep=True) if copy else mesh

    def nearest_point(
        self,
        coordinate: Iterable[float],
        *,
        tolerance: Optional[float] = None,
    ) -> PointSelection:
        """Find the nearest point across all result partitions."""
        target = np.asarray(tuple(coordinate), dtype=float)
        if target.shape != (3,):
            raise ValueError("coordinate must contain exactly three values")

        best: Optional[PointSelection] = None
        for partition, reader in enumerate(self.readers):
            if not reader.supports("mesh"):
                raise UnsupportedResultOperation(
                    f"{type(reader).__name__} cannot select points without geometry"
                )
            points = reader.mesh.points
            if points.size == 0:
                continue
            distances = np.linalg.norm(points - target, axis=1)
            index = int(np.argmin(distances))
            selection = PointSelection(
                partition=partition,
                index=index,
                coordinate=tuple(float(value) for value in points[index]),
                distance=float(distances[index]),
            )
            if best is None or selection.distance < best.distance:
                best = selection

        if best is None:
            raise ResultFormatError("The result set contains no selectable points")
        if tolerance is not None and best.distance > tolerance:
            raise ValueError(
                f"Nearest result point is {best.distance:g} away, exceeding "
                f"tolerance {tolerance:g}"
            )
        return best

    def point_history(
        self,
        response: str,
        point: PointSelection,
        component: Component = None,
    ) -> np.ndarray:
        """Return a selected point's history."""
        return self.readers[point.partition].point_history(
            response,
            point.index,
            component,
        )

    def cell_history(
        self,
        response: str,
        cell_index: int,
        *,
        partition: int = 0,
        component: Component = None,
    ) -> np.ndarray:
        """Return a cell history from one partition."""
        return self.readers[partition].cell_history(
            response,
            cell_index,
            component,
        )

    def deformation_renderer(self):
        """Create a reusable deformation renderer for mesh-capable results."""
        from .visualization import DeformationRenderer

        return DeformationRenderer(self)

    def close(self) -> None:
        for reader in self.readers:
            reader.close()

    def __enter__(self) -> "ResultSet":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def _resolve_paths(source: Union[PathInput, Iterable[PathInput]]) -> list[Path]:
    if isinstance(source, (str, Path)):
        text = str(source)
        if any(character in text for character in "*?["):
            paths = [Path(match) for match in sorted(glob(text))]
        else:
            paths = [Path(source)]
    else:
        paths = [Path(path) for path in source]

    if not paths:
        raise FileNotFoundError(f"No result files matched {source!r}")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Result file not found: {missing[0]}")
    return paths


def open_results(
    source: Union[PathInput, Iterable[PathInput]],
    *,
    format: Optional[str] = None,
    registry: ResultReaderRegistry = reader_registry,
    **reader_options: Any,
) -> ResultSet:
    """Open one result file or a partitioned set selected by a glob pattern."""
    return ResultSet(
        [
            registry.create(path, format=format, **reader_options)
            for path in _resolve_paths(source)
        ]
    )
