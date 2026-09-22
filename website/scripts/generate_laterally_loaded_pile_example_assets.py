# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate the interactive laterally loaded pile documentation asset."""

from __future__ import annotations

import os
from pathlib import Path
import runpy

import pyvista as pv


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples" / "soil_structure_interaction" / "laterally_loaded_pile.py"
DESTINATION = (
    ROOT
    / "website"
    / "docs"
    / "assets"
    / "examples"
    / "laterally-loaded-pile"
    / "index.html"
)


def main() -> None:
    previous_executable = os.environ.pop("FEMORA_OPENSEES", None)
    try:
        namespace = runpy.run_path(str(SOURCE))
    finally:
        if previous_executable is not None:
            os.environ["FEMORA_OPENSEES"] = previous_executable

    interface = namespace["pile_soil_interface"]
    mesh = namespace["model"].assembled_mesh
    soil_mesh = mesh.extract_cells(mesh.celltypes != int(pv.CellType.LINE))

    soil_color = "#c7b99f"
    pile_color = "#17252b"
    selected_color = "#d97732"
    envelope_color = "#3f7185"
    plotter = interface.plot(
        show_mesh=False,
        show_envelope=True,
        selected_opacity=0.52,
        envelope_opacity=0.24,
        selected_color=selected_color,
        envelope_color=envelope_color,
        beam_color=pile_color,
        off_screen=True,
        window_size=(1100, 680),
        return_plotter=True,
    )
    plotter.add_mesh(
        soil_mesh,
        color=soil_color,
        opacity=0.13,
        show_edges=True,
        edge_color="#697a7e",
        line_width=0.7,
    )
    plotter.add_legend(
        labels=[
            ["Soil mesh", soil_color],
            ["Pile beam", pile_color],
            ["Interface envelope", envelope_color],
            ["Selected solid cells", selected_color],
        ],
        bcolor="#f6f4ef",
        border=True,
        face="rectangle",
        size=(0.24, 0.22),
        loc="upper right",
    )
    plotter.view_isometric()
    plotter.enable_parallel_projection()
    plotter.camera.zoom(1.16)
    plotter.set_background("#f6f4ef")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    plotter.export_html(DESTINATION)
    plotter.close()
    print(f"Generated {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
