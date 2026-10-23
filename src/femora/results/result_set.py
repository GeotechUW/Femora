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
    """Location returned by ResultSet.nearest_point(), not an OpenSees node tag.

    Attributes:
        partition: Zero-based reader position in the result set, not an MPI rank.
        index: Zero-based local point index within that reader's mesh.
        coordinate: Selected XYZ location in model length units.
        distance: Distance from the requested coordinate, in model length units.

    Note:
        Keep this selection with the result set that created it. Partition order
        follows the supplied file order; a glob is sorted lexicographically.
    """

    __doc_controls__ = {"members": []}

    partition: int
    index: int
    coordinate: tuple[float, float, float]
    distance: float


class ResultSet:
    """Query one recorder's serial or MPI-partitioned output.

    Usually obtained from [open_results()][femora.results.result_set.open_results],
    not constructed directly. Each file keeps its own mesh and entity indices;
    this object does not merge meshes or identify physical members.

    Start with the example below. The Methods and Attributes summary tables
    link directly to each member's detailed reference further down this page.

    Args:
        readers (Sequence[ResultReader]): Nonempty reader sequence. The result set owns them
            and closes them on context-manager exit or close().

    Raises:
        ValueError: No readers were supplied.

    Example:
        ```python
        from femora.results import open_results

        with open_results("results/response*.vtkhdf") as results:
            print(results.paths)
            point = results.nearest_point((0, 0, 0), tolerance=0.01)
            ux = results.point_history("displacement", point, component="x")
        ```

    Note:
        Queries return NumPy arrays without unit conversion or automatic
        acceleration-basis conversion. Use BuildingResults for building-aware
        tables, identity checks, and structural response interpretation.
    """

    __doc_controls__ = {"summary": True, "members": [
        "paths", "number_of_partitions", "times", "number_of_steps",
        "available_point_responses", "available_cell_responses", "supports",
        "mesh", "nearest_point", "point_history", "cell_history",
        "deformation_renderer", "close",
    ]}

    def __init__(self, readers: Sequence[ResultReader]) -> None:
        if not readers:
            raise ValueError("ResultSet requires at least one reader")
        self.readers = tuple(readers)
        self._times: Optional[np.ndarray] = None
        self._times_loaded = False

    @property
    def paths(self) -> tuple[Path, ...]:
        """Input file paths in reader/partition order."""
        return tuple(reader.path for reader in self.readers)

    @property
    def number_of_partitions(self) -> int:
        """Number of input readers, not the solver's total MPI rank count."""
        return len(self.readers)

    @property
    def times(self) -> Optional[np.ndarray]:
        """Common recorded sample coordinates, or None if none were recorded.

        Returns:
            numpy.ndarray | None: One-dimensional samples, usually in model time
                units; a static recorder may store load-factor/pseudo-time.

        Raises:
            ResultFormatError: Partitions disagree on timestamps or on whether
                timestamps exist. Validation is performed when first accessed.
        """
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
        """Recorded sample count, which may differ from solver step count.

        Raises:
            ResultFormatError: Partition sample counts differ.
        """
        reference = self.readers[0].number_of_steps
        if any(reader.number_of_steps != reference for reader in self.readers[1:]):
            raise ResultFormatError(
                "Partitioned result files do not contain the same number of steps"
            )
        return reference

    @property
    def available_point_responses(self) -> tuple[str, ...]:
        """Sorted point-field names available in every partition.

        Typical normalized names are displacement, velocity, and acceleration.
        Inspect this property rather than assuming a field was recorded.
        """
        return self._common_responses("available_point_responses")

    @property
    def available_cell_responses(self) -> tuple[str, ...]:
        """Sorted cell-field names common to every partition, such as force3D."""
        return self._common_responses("available_cell_responses")

    def _common_responses(self, attribute: str) -> tuple[str, ...]:
        common = set(getattr(self.readers[0], attribute))
        for reader in self.readers[1:]:
            common.intersection_update(getattr(reader, attribute))
        return tuple(sorted(common))

    def supports(self, capability: str) -> bool:
        """Check that every reader implements an operation.

        Args:
            capability: Capability name such as ``"mesh"``, ``"point_history"``,
                ``"cell_history"``, ``"point_frame"``, or ``"cell_frame"``.

        Returns:
            bool: True only if all readers support that operation. This does not
                guarantee that a particular response field exists in the files.
        """
        return all(reader.supports(capability) for reader in self.readers)

    def mesh(self, partition: int = 0, *, copy: bool = False):
        """Return one partition's undeformed mesh.

        Args:
            partition: Zero-based reader position, not the MPI rank or filename suffix.
            copy: Return a deep copy if True; otherwise return the reader's cached
                mesh. Use a copy before changing coordinates or arrays.

        Returns:
            grid (pyvista.UnstructuredGrid): Mesh supplied by the selected reader.

        Raises:
            UnsupportedResultOperation: The reader has no mesh capability.
            IndexError: The partition index is outside the reader sequence.
        """
        mesh = self.readers[partition].mesh
        return mesh.copy(deep=True) if copy else mesh

    def nearest_point(
        self,
        coordinate: Iterable[float],
        *,
        tolerance: Optional[float] = None,
    ) -> PointSelection:
        """Find the closest recorded mesh point across all partitions.

        Args:
            coordinate: Three global XYZ coordinates in model length units.
            tolerance: Maximum permitted distance in those units. None accepts
                the closest point regardless of its distance.

        Returns:
            PointSelection: Reader position, local index, and distance.
                Equal-distance ties use the first partition/point encountered.

        Raises:
            ValueError: Coordinate does not contain three values, or the nearest
                point exceeds tolerance.
            ResultFormatError: All partition meshes are empty.
            UnsupportedResultOperation: A reader does not provide geometry.

        Note:
            This is nearest-node selection, not interpolation. Coincident points
            cannot be distinguished by coordinate alone; use structural metadata
            and BuildingResults when node identity is important.
        """
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
        """Read one selected point over all recorded samples.

        Args:
            response: Recorded field name, normally ``"displacement"``,
                ``"velocity"``, or ``"acceleration"`` for VTKHDF.
            point: Selection returned by this result set's nearest_point().
            component: None for every component, or ``"x"``, ``"y"``, ``"z"``
                or an integer component index, as supported by the reader.

        Returns:
            numpy.ndarray: Shape (samples, components), or (samples,) when a
                component is selected. Recorded units and basis are retained.

        Raises:
            KeyError: The reader does not contain the requested field.
            UnsupportedResultOperation: Point histories are unsupported.
        """
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
        """Read one local element/cell history from one partition.

        Args:
            response: Cell field name, for example ``"force3D"``.
            cell_index: Zero-based local mesh-cell index, not an OpenSees element tag.
            partition: Zero-based reader position in this collection.
            component: None for all components, or a reader-supported component index.

        Returns:
            numpy.ndarray: Shape (samples, components), or (samples,) for one
                component. Force3D contains 12 end actions for supported beams.

        Raises:
            KeyError: The requested cell field was not recorded.
            UnsupportedResultOperation: Cell histories are unsupported.

        Example:
            ```python
            with open_results("results/building_response*.vtkhdf") as results:
                forces = results.cell_history("force3D", cell_index=0, partition=0)
            ```
        """
        return self.readers[partition].cell_history(
            response,
            cell_index,
            component,
        )

    def deformation_renderer(self):
        """Create a DeformationRenderer; no movie is written yet.

        Returns:
            renderer (DeformationRenderer): Renderer referencing these readers. Call its
                write() method before closing the result set.

        Raises:
            UnsupportedResultOperation: Mesh or point-frame access is unsupported.
        """
        from .visualization import DeformationRenderer

        return DeformationRenderer(self)

    def close(self) -> None:
        """Release all owned readers; prefer a with block for automatic cleanup."""
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
    """Open one recorder's output without loading every response history.

    Args:
        source: File path, glob string, or iterable of paths. Globs are sorted
            lexicographically. Select only partitions from the same recorder/run.
        format: Explicit registered format name, for example ``"vtkhdf"``.
            None selects a reader by file suffix; VTKHDF is registered by default.
        registry: Reader registry. Usually leave the shared default unchanged.
        **reader_options: Additional options forwarded to each reader factory.
            The built-in VTKHDF reader currently accepts only a path.

    Returns:
        ResultSet: Collection owning the readers. Close it or use a with block.

    Raises:
        FileNotFoundError: No files match, or a supplied path does not exist.
        ResultFormatError: The file format is unregistered or a reader rejects
            the file. Timestamp consistency is checked when results.times is read.

    Examples:
        Open a serial file:

        ```python
        from femora.results import open_results

        with open_results("results/response0.vtkhdf") as results:
            print(results.available_point_responses)
        ```

        Read one point from partitioned output:

        ```python
        with open_results("results/response*.vtkhdf") as results:
            point = results.nearest_point((0, 0, 0), tolerance=0.01)
            ax = results.point_history("acceleration", point, component="x")
            time = results.times
        ```

    Note:
        This reads existing output, not a live analysis. It does not create
        recorders, run OpenSees, merge partition meshes, convert units, or add
        ground acceleration. A finite history alone does not prove stability.
    """
    return ResultSet(
        [
            registry.create(path, format=format, **reader_options)
            for path in _resolve_paths(source)
        ]
    )
