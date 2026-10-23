# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Lazy access to transient OpenSees VTKHDF recorder output."""

from __future__ import annotations

from pathlib import Path
from typing import FrozenSet, Optional, Union

import h5py
import numpy as np
import pyvista as pv

from ..base import (
    CELL_FRAME,
    CELL_HISTORY,
    MESH,
    POINT_FRAME,
    POINT_HISTORY,
    Component,
    ResultReader,
)
from ..exceptions import ResultFormatError


_COMPONENTS = {"x": 0, "y": 1, "z": 2}


class VTKHDFResultReader(ResultReader):
    """Read one OpenSees VTKHDF partition using lazy HDF5 history access.

    Prefer open_results() for ordinary use and for multiple MPI partitions.
    Direct access is useful for extracting a field at one recorded sample.

    Args:
        path: Existing VTKHDF file containing VTKHDF/Points and Steps/Values.

    Raises:
        FileNotFoundError: The file does not exist.
        ResultFormatError: Required VTKHDF layout entries are missing.
        OSError: HDF5 cannot open the file. Wait for the solver to close it;
            do not bypass file locks to read an active recorder.

    Example:
        ```python
        from femora.results.readers import VTKHDFResultReader

        with VTKHDFResultReader("results/response0.vtkhdf") as reader:
            displacement = reader.point_frame("displacement", step=-1)
            geometry = reader.mesh
        ```

    Note:
        Names are the stored field names: displacement, velocity, acceleration,
        force3D, and localForce3D are typical OpenSees outputs. No alias rewriting,
        unit conversion, acceleration conversion, or force interpretation occurs.
        Only fields present in both data and per-step offsets are advertised.
        Unsupported element responses may be stored as zeros by the solver.
    """

    __doc_controls__ = {"members": [
        "capabilities", "times", "number_of_steps", "number_of_points",
        "number_of_cells", "available_point_responses", "available_cell_responses",
        "mesh", "point_history", "cell_history", "point_frame", "cell_frame", "close",
    ]}

    def __init__(self, path: Union[str, Path]) -> None:
        super().__init__(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"VTKHDF result file not found: {self.path}")
        self._file: Optional[h5py.File] = None
        self._mesh: Optional[pv.UnstructuredGrid] = None
        self._validate_layout()

    @property
    def capabilities(self) -> FrozenSet[str]:
        """Available mesh, history, and frame operations based on stored fields."""
        capabilities = {MESH}
        if self.available_point_responses:
            capabilities.update({POINT_HISTORY, POINT_FRAME})
        if self.available_cell_responses:
            capabilities.update({CELL_HISTORY, CELL_FRAME})
        return frozenset(capabilities)

    @property
    def _vtkhdf(self) -> h5py.Group:
        if self._file is None:
            self._file = h5py.File(self.path, "r")
        try:
            return self._file["VTKHDF"]
        except KeyError as exc:
            raise ResultFormatError(f"{self.path} does not contain /VTKHDF") from exc

    def _validate_layout(self) -> None:
        required = ("Points", "Steps")
        with h5py.File(self.path, "r") as result:
            if "VTKHDF" not in result:
                raise ResultFormatError(f"{self.path} does not contain /VTKHDF")
            vtkhdf = result["VTKHDF"]
            missing = [name for name in required if name not in vtkhdf]
            if missing:
                raise ResultFormatError(
                    f"{self.path} is missing VTKHDF entries: {', '.join(missing)}"
                )
            if "Values" not in vtkhdf["Steps"]:
                raise ResultFormatError(f"{self.path} is missing VTKHDF step values")

    @property
    def times(self) -> np.ndarray:
        """Recorded Steps/Values array; static samples may be pseudo-time."""
        return self._vtkhdf["Steps"]["Values"][()]

    @property
    def number_of_steps(self) -> int:
        """Number of stored samples, not necessarily the solver step count."""
        return int(self._vtkhdf["Steps"]["Values"].shape[0])

    @property
    def available_point_responses(self) -> tuple[str, ...]:
        """Names with both point data and per-step offsets in this file."""
        return self._available_responses("PointData")

    @property
    def available_cell_responses(self) -> tuple[str, ...]:
        """Names with both cell data and per-step offsets in this file."""
        return self._available_responses("CellData")

    def _available_responses(self, location: str) -> tuple[str, ...]:
        offsets_name = f"{location}Offsets"
        steps = self._vtkhdf["Steps"]
        if offsets_name not in steps or location not in self._vtkhdf:
            return ()
        offsets = steps[offsets_name]
        fields = self._vtkhdf[location]
        return tuple(sorted(name for name in fields if name in offsets))

    @property
    def mesh(self) -> pv.UnstructuredGrid:
        """Cached PyVista mesh; copy it before modifying coordinates or arrays."""
        if self._mesh is None:
            self._mesh = pv.UnstructuredGrid(pv.read(self.path))
        return self._mesh

    @property
    def number_of_points(self) -> int:
        """Point count for the first mesh, excluding repeated transient counts."""
        if "NumberOfPoints" in self._vtkhdf:
            return self._first_mesh_count("NumberOfPoints")
        return int(self._vtkhdf["Points"].shape[0])

    @property
    def number_of_cells(self) -> int:
        """Cell count for the first mesh, excluding repeated transient counts."""
        if "NumberOfCells" in self._vtkhdf:
            return self._first_mesh_count("NumberOfCells")
        return int(self.mesh.n_cells)

    def _first_mesh_count(self, name):
        counts = np.asarray(self._vtkhdf[name][()]).reshape(-1)
        steps = self._vtkhdf["Steps"]
        if "PartOffsets" in steps and "NumberOfParts" in steps:
            start = int(steps["PartOffsets"][0])
            parts = int(steps["NumberOfParts"][0])
            return int(counts[start:start+parts].sum())
        # OpenSees appends a count for every transient step, not extra cells.
        return int(counts[0]) if self.number_of_steps > 1 else int(counts.sum())

    def point_history(
        self,
        response: str,
        point_index: int,
        component: Component = None,
    ) -> np.ndarray:
        """Read one local point over all samples.

        Args:
            response: Stored point field name.
            point_index: Zero-based mesh-point index, not a node tag.
            component: None for all components, an integer, or x/y/z.

        Returns:
            NumPy array of samples, with a component dimension unless selected
            explicitly or the stored field is scalar.

        Raises:
            KeyError: Field data or its per-step offsets are absent.
            IndexError: Point or component index is outside the stored array.
        """
        return self._history("PointData", response, point_index, component)

    def cell_history(
        self,
        response: str,
        cell_index: int,
        component: Component = None,
    ) -> np.ndarray:
        """Read one local cell's recorded history.

        Args:
            response: Stored cell field name, such as force3D.
            cell_index: Zero-based mesh-cell index, not an element tag.
            component: None for all components, or an integer component index.

        Returns:
            NumPy array of samples and, when applicable, components.

        Raises:
            KeyError: Field data or offsets are absent.
            IndexError: Cell or component index is out of range.
        """
        return self._history("CellData", response, cell_index, component)

    def point_frame(
        self,
        response: str,
        step: int,
        component: Component = None,
    ) -> np.ndarray:
        """Read all points at one recorded sample, without deforming the mesh.

        Args:
            response: Stored point field name.
            step: Zero-based sample index; -1 selects the last sample.
            component: None for every component, an integer, or x/y/z.

        Returns:
            Array shaped (points, components), or (points,) for a scalar/selected
            component. Translational/rotational components are not separated.

        Raises:
            KeyError: Requested field is unavailable.
            IndexError: Sample index is out of range.
        """
        return self._frame("PointData", response, step, component)

    def cell_frame(
        self,
        response: str,
        step: int,
        component: Component = None,
    ) -> np.ndarray:
        """Read all cells at one recorded sample.

        Args:
            response: Stored cell field name, such as force3D.
            step: Zero-based sample index; negative indices count from the end.
            component: None for all components, or an integer component index.

        Returns:
            Array shaped (cells, components), or (cells,) for scalar/selected data.

        Raises:
            KeyError: Requested field is unavailable.
            IndexError: Sample index is out of range.
        """
        return self._frame("CellData", response, step, component)

    def _history(
        self,
        location: str,
        response: str,
        entity_index: int,
        component: Component,
    ) -> np.ndarray:
        entity_count = self._entity_count(location)
        if entity_index < 0 or entity_index >= entity_count:
            raise IndexError(
                f"{location} index {entity_index} is outside [0, {entity_count})"
            )
        values, offsets = self._response_data(location, response)
        indices = offsets[()] + entity_index
        # Regular transient meshes permit a strided read instead of expensive
        # HDF5 fancy indexing over thousands of individual samples.
        stride = int(indices[1] - indices[0]) if len(indices) > 1 else 0
        if stride > 0 and np.all(np.diff(indices) == stride):
            history = values[int(indices[0]):int(indices[-1]) + 1:stride]
        else:
            history = values[indices]
        return self._select_component(history, component)

    def _frame(
        self,
        location: str,
        response: str,
        step: int,
        component: Component,
    ) -> np.ndarray:
        values, offsets = self._response_data(location, response)
        number_of_steps = offsets.shape[0]
        normalized_step = step if step >= 0 else number_of_steps + step
        if normalized_step < 0 or normalized_step >= number_of_steps:
            raise IndexError(f"Step {step} is outside [0, {number_of_steps})")
        start = int(offsets[normalized_step])
        stop = start + self._entity_count(location)
        frame = values[start:stop]
        return self._select_component(frame, component)

    def _response_data(
        self,
        location: str,
        response: str,
    ) -> tuple[h5py.Dataset, h5py.Dataset]:
        offsets_name = f"{location}Offsets"
        try:
            values = self._vtkhdf[location][response]
            offsets = self._vtkhdf["Steps"][offsets_name][response]
        except KeyError as exc:
            available = (
                self.available_point_responses
                if location == "PointData"
                else self.available_cell_responses
            )
            raise KeyError(
                f"Transient {location} response '{response}' is unavailable; "
                f"available responses: {', '.join(available) or 'none'}"
            ) from exc
        return values, offsets

    def _entity_count(self, location: str) -> int:
        return self.number_of_points if location == "PointData" else self.number_of_cells

    @staticmethod
    def _select_component(values: np.ndarray, component: Component) -> np.ndarray:
        if component is None:
            return values
        if values.ndim < 2:
            raise ValueError("A component cannot be selected from a scalar response")
        index = (
            _COMPONENTS.get(component.lower(), None)
            if isinstance(component, str)
            else component
        )
        if index is None or not isinstance(index, int):
            raise ValueError("component must be an integer or one of 'x', 'y', or 'z'")
        if index < 0 or index >= values.shape[1]:
            raise IndexError(
                f"Component {component!r} is unavailable for shape {values.shape}"
            )
        return values[:, index]

    def close(self) -> None:
        """Close the HDF5 handle; context-manager exit calls this automatically."""
        if self._file is not None:
            self._file.close()
            self._file = None
