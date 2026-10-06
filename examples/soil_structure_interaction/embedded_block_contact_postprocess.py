"""Render the embedded foundation contact response as a two-panel movie."""

from pathlib import Path

import numpy as np
import pyvista as pv

import femora as fm


RESULTS = Path("example_outputs/embedded_block_contact/results").resolve()
MOVIE = RESULTS / "block_contact_tilt.mp4"
DEFORMATION_SCALE = 2.0


with fm.results.open(str(RESULTS / "block_contact*.vtkhdf")) as results:
    if results.number_of_partitions != 1:
        raise RuntimeError("The temporary model expects one VTKHDF partition")
    if "displacement" not in results.readers[0].available_point_responses:
        raise RuntimeError("The VTKHDF result does not contain displacement")

    reader = results.readers[0]
    mesh = results.mesh(copy=True)
    original_points = mesh.points.copy()

    # Soil cell centers are below the embedded block's bottom at z = -0.25 m.
    centers = mesh.cell_centers().points
    block_3d = mesh.extract_cells(centers[:, 2] > -0.25)
    soil_3d = mesh.extract_cells(
        (centers[:, 2] < -0.25) & (centers[:, 2] > -2.6)
    )
    # Retain only the back half of the upper soil layer. This exposes the
    # embedded faces and makes opening at the contact readable in side view.
    block_section = block_3d.copy(deep=True)
    soil_section = mesh.extract_cells(
        (centers[:, 2] < -0.25)
        & (centers[:, 2] > -2.6)
        & (centers[:, 1] > 0.0)
    )
    block_3d_ids = np.asarray(
        block_3d.point_data["vtkOriginalPointIds"], dtype=int
    )
    soil_3d_ids = np.asarray(
        soil_3d.point_data["vtkOriginalPointIds"], dtype=int
    )
    block_section_ids = np.asarray(
        block_section.point_data["vtkOriginalPointIds"], dtype=int
    )
    soil_section_ids = np.asarray(
        soil_section.point_data["vtkOriginalPointIds"], dtype=int
    )
    undeformed_block_3d = block_3d.copy(deep=True)
    undeformed_block_section = block_section.copy(deep=True)

    top_left = results.nearest_point((-1.0, 0.0, 1.75), tolerance=1.0e-6)
    top_right = results.nearest_point((1.0, 0.0, 1.75), tolerance=1.0e-6)
    left_index = top_left.index
    right_index = top_right.index

    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(1600, 720))

    plotter.subplot(0, 0)
    plotter.add_mesh(
        soil_3d,
        color="#b89b72",
        opacity=0.20,
        show_edges=False,
    )
    plotter.add_mesh(
        soil_3d,
        style="wireframe",
        color="#665845",
        opacity=1.0,
        line_width=1.2,
    )
    plotter.add_mesh(
        undeformed_block_3d,
        style="wireframe",
        color="#77716a",
        opacity=0.45,
        line_width=1.0,
    )
    plotter.add_mesh(
        block_3d,
        color="#d56345",
        show_edges=True,
        edge_color="#542d24",
        line_width=1.2,
    )
    plotter.set_background("#f4f1e8")
    plotter.reset_camera()
    plotter.camera_position = [
        (-7.2, -9.0, 4.8),
        (0.0, 0.0, -0.4),
        (0.0, 0.0, 1.0),
    ]
    plotter.reset_camera_clipping_range()
    plotter.add_text("3D model", font_size=14, color="#2d2925")
    load_arrow_3d = pv.Arrow(
        start=(-2.2, -0.05, 1.35),
        direction=(1.0, 0.0, 0.0),
        scale=1.1,
        tip_length=0.12,
        tip_radius=0.055,
        shaft_radius=0.020,
    )
    plotter.add_mesh(load_arrow_3d, color="#2f6f8f")

    plotter.subplot(0, 1)
    plotter.add_mesh(
        soil_section,
        color="#b89b72",
        opacity=0.38,
        show_edges=False,
    )
    plotter.add_mesh(
        soil_section,
        style="wireframe",
        color="#665845",
        opacity=1.0,
        line_width=1.2,
    )
    plotter.add_mesh(
        undeformed_block_section,
        style="wireframe",
        color="#77716a",
        opacity=0.50,
        line_width=1.0,
    )
    plotter.add_mesh(
        block_section,
        color="#d56345",
        show_edges=True,
        edge_color="#542d24",
        line_width=1.2,
    )
    plotter.set_background("#f4f1e8")
    plotter.enable_parallel_projection()
    plotter.view_xz()
    plotter.reset_camera()
    plotter.camera.zoom(1.20)
    plotter.add_text("Contact section", font_size=14, color="#2d2925")
    load_arrow_section = pv.Arrow(
        start=(-2.2, -0.05, 1.35),
        direction=(1.0, 0.0, 0.0),
        scale=1.1,
        tip_length=0.12,
        tip_radius=0.055,
        shaft_radius=0.020,
    )
    plotter.add_mesh(load_arrow_section, color="#2f6f8f")
    plotter.open_movie(str(MOVIE), framerate=25, quality=8)

    times = results.times
    try:
        for step in range(results.number_of_steps):
            displacement = reader.point_frame("displacement", step)[:, :3]
            deformed = original_points + DEFORMATION_SCALE * displacement
            block_3d.points = deformed[block_3d_ids]
            soil_3d.points = deformed[soil_3d_ids]
            block_section.points = deformed[block_section_ids]
            soil_section.points = deformed[soil_section_ids]

            dz = displacement[right_index, 2] - displacement[left_index, 2]
            rotation = np.degrees(np.arctan2(dz, 2.0))
            load_fraction = min(max(float(times[step]) / float(times[-1]), 0.0), 1.0)
            plotter.subplot(0, 1)
            plotter.add_text(
                f"Time {times[step]:.2f} s | Load {100.0 * load_fraction:.0f}% | "
                f"Rotation {rotation:.3f} deg | {DEFORMATION_SCALE:g}x deformation",
                name="status",
                position="lower_left",
                font_size=13,
                color="#2d2925",
            )
            plotter.write_frame()
    finally:
        plotter.close()

print(f"Created {MOVIE}")
