# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate the interactive partition view for the 3D site-response example."""

from __future__ import annotations

import os
from pathlib import Path
import runpy

import numpy as np
import pyvista as pv


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples" / "site_response" / "partitioned_layered_soil_domain.py"
DESTINATION = (
    ROOT
    / "website"
    / "docs"
    / "assets"
    / "examples"
    / "partitioned-layered-soil-domain"
    / "index.html"
)
CORE_COLORS = [
    "#315c6d",
    "#ca7049",
    "#c9a34d",
    "#59866f",
    "#7e6d9c",
    "#4f7fa8",
    "#a85c68",
    "#72854a",
]


def main() -> None:
    previous_executable = os.environ.pop("FEMORA_OPENSEES", None)
    try:
        namespace = runpy.run_path(str(SOURCE))
    finally:
        if previous_executable is not None:
            os.environ["FEMORA_OPENSEES"] = previous_executable

    mesh = namespace["model"].assembled_mesh
    core_ids = np.asarray(mesh.cell_data["Core"])
    plotter = pv.Plotter(off_screen=True, window_size=(1050, 650))
    for core_id in np.unique(core_ids):
        plotter.add_mesh(
            mesh.extract_cells(np.flatnonzero(core_ids == core_id)),
            color=CORE_COLORS[int(core_id) % len(CORE_COLORS)],
            show_edges=True,
            edge_color="#26363b",
            line_width=0.45,
        )

    plotter.add_axes(line_width=2, labels_off=False)
    plotter.view_isometric()
    plotter.enable_parallel_projection()
    plotter.camera.zoom(1.12)
    plotter.set_background("#f6f4ef")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    plotter.export_html(DESTINATION)
    plotter.close()
    print(f"Generated {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
