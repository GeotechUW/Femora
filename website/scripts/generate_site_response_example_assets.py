# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate interactive assets for documented site-response examples."""

from __future__ import annotations

import os
from pathlib import Path
import runpy

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples" / "site_response" / "layered_elastic_soil_column.py"
DESTINATION = (
    ROOT
    / "website"
    / "docs"
    / "assets"
    / "examples"
    / "layered-elastic-soil-column"
    / "index.html"
)
FREQUENCY_SWEEP_PLOT = DESTINATION.with_name("frequency-sweep.png")

PHYSICAL_LAYERS = [
    (-18.0, -8.0, "#315c6d"),
    (-8.0, -2.0, "#c59652"),
    (-2.0, 0.0, "#b65f3a"),
]


def main() -> None:
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
            mesh.extract_cells(cells),
            color=color,
            show_edges=True,
            edge_color="#17252b",
            line_width=1.6,
        )

    plotter.add_axes(
        line_width=2,
        labels_off=False,
    )
    plotter.view_xz()
    plotter.enable_parallel_projection()
    plotter.camera.zoom(1.12)
    plotter.set_background("#f6f4ef")

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    plotter.export_html(DESTINATION)
    plotter.close()

    motion_time = np.loadtxt(
        ROOT / "examples" / "inputs" / "motions" / "FrequencySweep.time"
    )
    motion_acceleration = np.loadtxt(
        ROOT / "examples" / "inputs" / "motions" / "FrequencySweep.acc"
    )
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(10.5, 5.2),
        constrained_layout=True,
        gridspec_kw={"height_ratios": [1.0, 1.25]},
    )
    for axis in axes:
        axis.plot(
            motion_time,
            motion_acceleration,
            color="#b65f3a",
            linewidth=0.9,
        )
        axis.set_ylabel("Acceleration (g)")
        axis.grid(color="#8a969b", alpha=0.22, linewidth=0.7)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_xlim(motion_time[0], motion_time[-1])
    axes[0].set_title("Complete frequency-sweep record", loc="left")
    axes[1].set_xlim(3.0, 12.0)
    axes[1].set_title("Early-time detail", loc="left")
    axes[1].set_xlabel("Time (s)")
    figure.patch.set_facecolor("#f6f4ef")
    for axis in axes:
        axis.set_facecolor("#f6f4ef")
    figure.savefig(FREQUENCY_SWEEP_PLOT, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(f"Generated {DESTINATION.relative_to(ROOT)}")
    print(f"Generated {FREQUENCY_SWEEP_PLOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
