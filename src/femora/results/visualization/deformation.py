# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Reusable deformation movie rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pyvista as pv
from tqdm import tqdm

from ..base import MESH, POINT_FRAME
from ..exceptions import UnsupportedResultOperation


class DeformationRenderer:
    """Configure and write deformation movies from a result set."""

    def __init__(self, results) -> None:
        if not results.supports(MESH) or not results.supports(POINT_FRAME):
            raise UnsupportedResultOperation(
                "Deformation rendering requires mesh and point-frame capabilities"
            )
        self.results = results
        self.response = "displacement"
        self.scale = 1.0
        self._field_name: Optional[str] = None
        self._field_location = "point"
        self._field_reduction: Optional[Union[str, int]] = None
        self._field_options: dict[str, Any] = {}
        self._mesh_options: dict[str, Any] = {"show_edges": True}
        self._camera_position: Any = None
        self._parallel_projection = False
        self._zoom: Optional[float] = None
        self._background: Any = None

    def deform_by(
        self,
        response: str = "displacement",
        *,
        scale: float = 1.0,
    ) -> "DeformationRenderer":
        """Choose the vector response and visual deformation scale."""
        if scale <= 0.0:
            raise ValueError("scale must be positive")
        self.response = response
        self.scale = float(scale)
        return self

    def color_by(
        self,
        field: str,
        *,
        location: str = "point",
        reduction: Optional[Union[str, int]] = None,
        **options: Any,
    ) -> "DeformationRenderer":
        """Color by a transient response or an existing static mesh array."""
        normalized = location.lower()
        if normalized not in {"point", "cell"}:
            raise ValueError("location must be 'point' or 'cell'")
        if reduction not in {None, "magnitude", 0, 1, 2}:
            raise ValueError("reduction must be None, 'magnitude', 0, 1, or 2")
        self._field_name = field
        self._field_location = normalized
        self._field_reduction = reduction
        self._field_options = dict(options)
        return self

    def style_mesh(self, **options: Any) -> "DeformationRenderer":
        """Set options forwarded to ``pyvista.Plotter.add_mesh``."""
        self._mesh_options.update(options)
        return self

    def set_view(
        self,
        camera_position: Any = None,
        *,
        parallel_projection: bool = False,
        zoom: Optional[float] = None,
        background: Any = None,
    ) -> "DeformationRenderer":
        """Configure the shared camera and background."""
        self._camera_position = camera_position
        self._parallel_projection = parallel_projection
        self._zoom = zoom
        self._background = background
        return self

    def write(
        self,
        filename: Union[str, Path],
        *,
        stride: int = 1,
        frame_rate: int = 30,
        quality: int = 5,
        progress: bool = True,
        window_size: tuple[int, int] = (960, 544),
    ) -> Path:
        """Render the configured result sequence to an MP4 file."""
        if stride <= 0:
            raise ValueError("stride must be positive")
        if frame_rate <= 0:
            raise ValueError("frame_rate must be positive")
        if self.response not in self.results.available_point_responses:
            raise KeyError(f"Point response '{self.response}' is unavailable")

        output = Path(filename)
        output.parent.mkdir(parents=True, exist_ok=True)
        meshes = [self.results.mesh(index, copy=True) for index in range(
            self.results.number_of_partitions
        )]
        self._validate_static_field(meshes)
        original_points = [mesh.points.copy() for mesh in meshes]
        plotter = pv.Plotter(off_screen=True, window_size=window_size)

        transient_field = self._transient_field_location()
        for partition, mesh in enumerate(meshes):
            if transient_field is not None:
                self._assign_field(mesh, partition, 0, transient_field)
            options = dict(self._mesh_options)
            if self._field_name is not None:
                options.update(scalars=self._field_name)
                options.update(self._field_options)
            plotter.add_mesh(mesh, **options)

        if self._camera_position is not None:
            plotter.camera_position = self._camera_position
        if self._parallel_projection:
            plotter.enable_parallel_projection()
        if self._zoom is not None:
            plotter.camera.zoom(self._zoom)
        if self._background is not None:
            plotter.set_background(self._background)

        plotter.open_movie(str(output), framerate=frame_rate, quality=quality)
        steps = range(0, self.results.number_of_steps, stride)
        iterator = tqdm(
            steps,
            desc="Rendering response",
            unit="frame",
            disable=not progress,
        )
        try:
            for step in iterator:
                for partition, (reader, mesh, points) in enumerate(
                    zip(self.results.readers, meshes, original_points)
                ):
                    displacement = reader.point_frame(self.response, step)
                    mesh.points = points + self.scale * self._as_xyz(displacement)
                    if transient_field is not None:
                        self._assign_field(mesh, partition, step, transient_field)
                plotter.write_frame()
        finally:
            plotter.close()
        return output

    def _validate_static_field(self, meshes) -> None:
        if self._field_name is None or self._transient_field_location() is not None:
            return
        for partition, mesh in enumerate(meshes):
            arrays = (
                mesh.point_data
                if self._field_location == "point"
                else mesh.cell_data
            )
            if self._field_name not in arrays:
                raise KeyError(
                    f"Static {self._field_location} field '{self._field_name}' "
                    f"is unavailable in partition {partition}"
                )

    def _transient_field_location(self) -> Optional[str]:
        if self._field_name is None:
            return None
        if self._field_location == "point":
            available = self.results.available_point_responses
        else:
            available = self.results.available_cell_responses
        return self._field_location if self._field_name in available else None

    def _assign_field(
        self,
        mesh: pv.UnstructuredGrid,
        partition: int,
        step: int,
        location: str,
    ) -> None:
        reader = self.results.readers[partition]
        if location == "point":
            values = reader.point_frame(self._field_name, step)
            target = mesh.point_data
        else:
            values = reader.cell_frame(self._field_name, step)
            target = mesh.cell_data
        target[self._field_name] = self._reduce(values)

    def _reduce(self, values: np.ndarray) -> np.ndarray:
        if self._field_reduction is None:
            return values
        if self._field_reduction == "magnitude":
            if values.ndim < 2:
                return np.abs(values)
            return np.linalg.norm(values, axis=1)
        if values.ndim < 2:
            raise ValueError("A component cannot be selected from a scalar field")
        return values[:, self._field_reduction]

    @staticmethod
    def _as_xyz(values: np.ndarray) -> np.ndarray:
        if values.ndim != 2:
            raise ValueError("The deformation response must be a vector field")
        if values.shape[1] == 3:
            return values
        if values.shape[1] > 3:
            return values[:, :3]
        padded = np.zeros((values.shape[0], 3), dtype=values.dtype)
        padded[:, : values.shape[1]] = values
        return padded
