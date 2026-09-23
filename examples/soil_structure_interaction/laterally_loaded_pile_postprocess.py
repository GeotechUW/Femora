# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Plot and animate the laterally loaded pile response."""

from __future__ import annotations

from pathlib import Path
import re
from xml.etree import ElementTree

import femora as fm
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from tqdm import tqdm


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "example_outputs" / "laterally_loaded_pile" / "results"
FORCE_FILE = RESULTS_DIR / "pile_force_pile_Core0_globalForce.xml"
POSTPROCESS_DIR = RESULTS_DIR.parent / "post_processing"
OUTPUT_FILE = POSTPROCESS_DIR / "pile_forces_moments.png"
MOVIE_FILE = POSTPROCESS_DIR / "lateral-deformation.mp4"
PILE_BOTTOM_Z = -10.0
PILE_HEAD_Z = 1.0
# These are intentionally separate from the physical pile elevations. They
# reproduce the depth range used by the legacy comparison plot.
LEGACY_PLOT_BOTTOM = -5.0
LEGACY_PLOT_TOP = 2.0
DEFORMATION_SCALE = 100.0
MOVIE_FRAME_RATE = 24


def read_beam_force_xml(path: Path) -> tuple[int, np.ndarray]:
    """Return the element count and numeric recorder rows from OpenSees XML."""
    root = ElementTree.parse(path).getroot()
    element_count = len(root.findall(".//ElementOutput"))
    data_node = root.find(".//Data")
    if element_count == 0 or data_node is None or not data_node.text:
        raise ValueError(f"Incomplete beam-force recorder: {path}")

    number_pattern = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
    rows = [
        [float(value) for value in number_pattern.findall(line)]
        for line in data_node.text.splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"No force data found in {path}")
    return element_count, np.asarray(rows, dtype=float)


def end_distributions(element_count: int, row: np.ndarray) -> dict[str, np.ndarray]:
    """Collect i-end values and the final j-end value along the pile."""
    values = row[1:].reshape(element_count, 12)
    names = ("Px", "Py", "Pz", "Mx", "My", "Mz")
    return {
        name: np.concatenate((values[:, index], [-values[-1, index + 6]]))
        for index, name in enumerate(names)
    }


# --8<-- [start:post-processing-workflow]
def generate_force_plot() -> Path:
    """Plot the final pile force and moment distributions."""
    element_count, history = read_beam_force_xml(FORCE_FILE)
    response = end_distributions(element_count, history[-1])
    depths = np.linspace(LEGACY_PLOT_BOTTOM, LEGACY_PLOT_TOP, element_count + 1)

    # Keep the legacy arrangement and Matplotlib defaults for direct comparison
    # with examples/SoilStructureInteraction/Example0/plot_moment.py.
    figure, axes = plt.subplots(3, 2, figsize=(6, 8), constrained_layout=True)
    components = (
        ("Px", axes[0, 0], "Shear Forces Px"),
        ("Py", axes[0, 1], "Shear Forces Py"),
        ("Pz", axes[1, 0], "Axial Forces Pz"),
        ("Mx", axes[1, 1], "Moments Mx"),
        ("My", axes[2, 0], "Moments My"),
        ("Mz", axes[2, 1], "Torsional Moments Mz"),
    )
    for component, axis, title in components:
        axis.plot(response[component], depths, "-", alpha=1.0)
        axis.set_title(title)
        axis.grid(True, which="both", linestyle="--", alpha=0.5)
        axis.set_xlabel("Force / Moment")
        axis.set_ylabel("Depth")
        axis.axvline(0, color="black", linewidth=0.8, linestyle="-", alpha=0.7)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_FILE, dpi=300, bbox_inches="tight")
    plt.close(figure)
    return OUTPUT_FILE


def generate_deformation_movie() -> Path:
    """Animate the complete model through the static load progression."""
    result_pattern = str(RESULTS_DIR / "pile_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        if results.number_of_partitions != 1:
            raise ValueError("This serial example expects one VTKHDF result file")

        reader = results.readers[0]
        mesh = results.mesh(copy=True)
        original_points = mesh.points.copy()
        line_cells = mesh.celltypes == int(pv.CellType.LINE)
        pile_mesh = mesh.extract_cells(line_cells)
        pile_point_ids = np.asarray(
            pile_mesh.point_data["vtkOriginalPointIds"],
            dtype=int,
        )

        undeformed = mesh.copy(deep=True)
        displacement = reader.point_frame("displacement", 0)
        magnitude = np.linalg.norm(displacement[:, :3], axis=1)
        final_displacement = reader.point_frame("displacement", -1)[:, :3]
        maximum_displacement = float(
            max(np.linalg.norm(final_displacement, axis=1).max(), 1.0e-12)
        )
        mesh.point_data["Displacement magnitude"] = magnitude

        plotter = pv.Plotter(off_screen=True, window_size=(1100, 680))
        # plotter.add_mesh(
        #     undeformed,
        #     color="#aeb8b8",
        #     opacity=0.08,
        #     show_edges=True,
        #     edge_color="#718083",
        #     line_width=0.5,
        # )
        plotter.add_mesh(
            mesh,
            scalars="Displacement magnitude",
            cmap="cividis",
            opacity=1.0,
            show_edges=True,
            edge_color="#9b9687",
            line_width=0.6,
            clim=(0.0, maximum_displacement*0.05),
            # scalar_bar_args={"title": "Displacement (m)"},
            show_scalar_bar= False
            
        )
        plotter.add_mesh(
            pile_mesh,
            color="#17252b",
            line_width=10,
            render_lines_as_tubes=True,
        )
        plotter.add_text(
            f"Load factor: 0.00   Deformation scale: {DEFORMATION_SCALE:g}x",
            name="load-factor",
            font_size=12,
        )

        plotter.view_xz()
        #  goes a liittle up to show the pile head
        plotter.camera.elevation = 30
        # plotter.enable_parallel_projection()

        
        # plotter.camera_position = [
        #     (0.0, -34.0, -3.5),
        #     (0.0, 0.0, -3.5),
        #     (0.0, 0.0, 1.0),
        # ]
        plotter.set_background("#f6f4ef")

        MOVIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        plotter.open_movie(
            str(MOVIE_FILE),
            framerate=MOVIE_FRAME_RATE,
            quality=7,
        )
        load_factors = results.times
        if load_factors is None:
            load_factors = np.linspace(0.0, 1.0, results.number_of_steps)

        try:
            for step in tqdm(
                range(results.number_of_steps),
                desc="Rendering lateral deformation",
                unit="frame",
            ):
                displacement = reader.point_frame("displacement", step)[:, :3]
                mesh.points = original_points + DEFORMATION_SCALE * displacement
                mesh.point_data["Displacement magnitude"] = np.linalg.norm(
                    displacement,
                    axis=1,
                )
                pile_mesh.points = mesh.points[pile_point_ids]
                plotter.add_text(
                    (
                        f"Load factor: {float(load_factors[step]):.2f}   "
                        f"Deformation scale: {DEFORMATION_SCALE:g}x"
                    ),
                    name="load-factor",
                    font_size=12,
                )
                plotter.write_frame()
        finally:
            plotter.close()
    return MOVIE_FILE


def generate_results() -> tuple[Path, ...]:
    """Generate the standard static result figures."""
    return (generate_force_plot(),)


def generate_animations() -> tuple[Path, ...]:
    """Generate the optional complete-model deformation animation."""
    return (generate_deformation_movie(),)


def main() -> None:
    generated = (*generate_results(), *generate_animations())
    print("Post-processing outputs:")
    for output in generated:
        print(f"  {output.resolve()}")


if __name__ == "__main__":
    main()
# --8<-- [end:post-processing-workflow]
