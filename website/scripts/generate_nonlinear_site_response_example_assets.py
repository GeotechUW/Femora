# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate the interactive mesh preview for the nonlinear soil example."""

from __future__ import annotations

import os
from pathlib import Path
import runpy

import numpy as np
import pyvista as pv


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples" / "site_response" / "nonlinear_layered_soil_column.py"
DESTINATION = (
    ROOT
    / "website"
    / "docs"
    / "assets"
    / "examples"
    / "nonlinear-layered-soil-column"
    / "index.html"
)
PHYSICAL_LAYERS = [
    (-18.0, -8.0, "#315c6d"),
    (-8.0, -2.0, "#c59652"),
    (-2.0, 0.0, "#b65f3a"),
]


def main() -> None:
    """Assemble the model without a solver run and export its PyVista scene."""
    previous_executable = os.environ.pop("FEMORA_OPENSEES", None)
    try:
        namespace = runpy.run_path(str(SOURCE))
    finally:
        if previous_executable is not None:
            os.environ["FEMORA_OPENSEES"] = previous_executable

    mesh = namespace["model"].assembled_mesh
    cell_elevations = mesh.cell_centers().points[:, 2]
    plotter = pv.Plotter(off_screen=True, window_size=(1050, 620))
    for z_min, z_max, color in PHYSICAL_LAYERS:
        cells = (cell_elevations >= z_min) & (cell_elevations < z_max + 1.0e-9)
        plotter.add_mesh(
            mesh.extract_cells(np.flatnonzero(cells)),
            color=color,
            show_edges=True,
            edge_color="#17252b",
            line_width=1.6,
        )
    plotter.add_axes(line_width=2, labels_off=False)
    plotter.view_xz()
    plotter.enable_parallel_projection()
    plotter.camera.zoom(1.12)
    plotter.set_background("#f6f4ef")

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    plotter.export_html(DESTINATION)
    plotter.close()
    print(f"Generated {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
