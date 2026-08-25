import os
import pyvista as pv
from femora.core.model import Model

# Ensure directory exists
out_dir = "website/docs/assets/assembly"
os.makedirs(out_dir, exist_ok=True)

# Common plotting setup
pv.global_theme.allow_empty_mesh = True
pv.global_theme.window_size = [1200, 800]
pv.global_theme.background = 'white'

def save_plot(plotter, name, save_png=False):
    plotter.export_html(f"{out_dir}/{name}.html")
    if save_png:
        plotter.screenshot(f"{out_dir}/{name}.png")
    plotter.close()

def plot_mesh(plotter, mesh, color="blue", show_points=True, scalars=None, cmap=None):
    if mesh is None or mesh.n_points == 0:
        return
    if scalars is not None and scalars in mesh.cell_data:
        plotter.add_mesh(mesh, scalars=scalars, cmap=cmap, show_edges=True, line_width=4, render_lines_as_tubes=True, show_scalar_bar=False)
    else:
        plotter.add_mesh(mesh, color=color, show_edges=True, line_width=4, render_lines_as_tubes=True, opacity=0.8)
    
    if show_points:
        pts_mesh = pv.PolyData(mesh.points)
        plotter.add_points(pts_mesh, color="red", point_size=18, render_points_as_spheres=True)

# -------------------------------------------------------------------------
# Example 1: Connected frame parts
# -------------------------------------------------------------------------
def run_example_1():
    def build_section(merge_points):
        model = Model()
        section = model.section.create_section("Elastic", user_name="frame_sec", E=1.0, A=1.0, Iz=1.0, Iy=1.0)
        transformation = model.transformation.transformation3d("Linear", 0, 1, 0)
        beam = model.element.beam.disp(ndof=6, section=section, transformation=transformation)

        part1 = model.meshpart.line.single_line("column", element=beam, x0=0.0, y0=0.0, z0=0.0, x1=0.0, y1=0.0, z1=1.0, number_of_lines=4)
        part2 = model.meshpart.line.single_line("beam", element=beam, x0=0.0, y0=0.0, z0=1.0, x1=1.0, y1=0.0, z1=1.0, number_of_lines=4)

        sec = model.assembler.create_section(meshparts=["column", "beam"], merge_points=merge_points, tolerance=1e-5)
        return part1, part2, sec

    part1, part2, sec_true = build_section(True)
    _, _, sec_false = build_section(False)

    cam_pos = [(2.0, 2.0, 2.0), (0.5, 0.0, 0.5), (0, 0, 1)]

    # Before
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    plot_mesh(pl, part1.mesh, color="blue")
    plot_mesh(pl, part2.mesh, color="green")
    pl.camera_position = cam_pos
    save_plot(pl, "connected_frame_before")

    # Section merge=True
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    plot_mesh(pl, sec_true.mesh, scalars="MeshPartTag_celldata", cmap=["blue", "green"])
    pl.camera_position = cam_pos
    save_plot(pl, "connected_frame_section_merge_true")

    # Section merge=False
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    mesh_unmerged = sec_false.mesh.copy()
    pts = mesh_unmerged.points.copy()
    # The first 5 points belong to column, next 5 to beam. Shift beam visibly in Y to show unmerged state.
    if len(pts) == 10:
        pts[5:, 1] += 0.2
    mesh_unmerged.points = pts
    plot_mesh(pl, mesh_unmerged, scalars="MeshPartTag_celldata", cmap=["blue", "green"])
    pl.camera_position = cam_pos
    save_plot(pl, "connected_frame_section_merge_false")

    print("Example 1 generated.")

# -------------------------------------------------------------------------
# Example 2: Beam versus solid
# -------------------------------------------------------------------------
def run_example_2():
    def build_section(merge_points):
        model = Model()
        soil_material = model.material.nd.elastic_isotropic("soil", E=1.0, nu=0.3, rho=1.0)
        brick = model.element.brick.std(ndof=3, material=soil_material)

        section = model.section.create_section("Elastic", user_name="beam_sec", E=1.0, A=1.0, Iz=1.0, Iy=1.0)
        transformation = model.transformation.transformation3d("Linear", 0, 1, 0)
        beam = model.element.beam.disp(ndof=6, section=section, transformation=transformation)

        part1 = model.meshpart.volume.uniform_rectangular_grid("soil_block", element=brick, x_min=-1.0, x_max=1.0, y_min=-1.0, y_max=1.0, z_min=-1.0, z_max=1.0, nx=2, ny=2, nz=2)
        part2 = model.meshpart.line.single_line("pile_beam", element=beam, x0=-2.0, y0=-2.0, z0=-2.0, x1=2.0, y1=2.0, z1=2.0, number_of_lines=4)

        sec = model.assembler.create_section(meshparts=["soil_block", "pile_beam"], merge_points=merge_points, tolerance=1e-5)
        return part1, part2, sec

    part1, part2, sec_true = build_section(True)
    _, _, sec_false = build_section(False)

    cam_pos = [(8.0, -4.0, 4.0), (0.0, 0.0, 0.0), (0, 0, 1)]

    def plot_ex2_part(plotter, mesh, color, is_beam, shift_pts_z=0.0):
        if mesh is None or mesh.n_points == 0: return
        opacity = 1.0 if is_beam else 0.3
        line_width = 5 if is_beam else 2
        point_size = 14 if is_beam else 8
        if is_beam:
            plotter.add_mesh(mesh, color=color, show_edges=True, opacity=opacity, line_width=line_width, render_lines_as_tubes=True)
        else:
            plotter.add_mesh(mesh, color=color, show_edges=True, opacity=opacity, line_width=line_width)
            
        pts = mesh.points.copy()
        if shift_pts_z != 0.0:
            pts[:, 2] += shift_pts_z
        plotter.add_points(pv.PolyData(pts), color=color, point_size=point_size, render_points_as_spheres=True)

    def plot_ex2_sec(plotter, mesh):
        if mesh is None: return
        solid = mesh.threshold(1.5, scalars="MeshPartTag_celldata", invert=True)
        beam_m = mesh.threshold(1.5, scalars="MeshPartTag_celldata", invert=False)
        plot_ex2_part(plotter, solid, "blue", False)
        # Shift beam points slightly in Z so the separate green and blue points don't fight and are both clearly visible
        plot_ex2_part(plotter, beam_m, "green", True, shift_pts_z=0.03)

    # Before
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    plot_ex2_part(pl, part1.mesh, "blue", False)
    plot_ex2_part(pl, part2.mesh, "green", True)
    pl.camera_position = cam_pos
    save_plot(pl, "beam_vs_solid_before")

    # Section merge=True
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    plot_ex2_sec(pl, sec_true.mesh)
    pl.camera_position = cam_pos
    save_plot(pl, "beam_vs_solid_section_merge_true")

    # Section merge=False
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    plot_ex2_sec(pl, sec_false.mesh)
    pl.camera_position = cam_pos
    save_plot(pl, "beam_vs_solid_section_merge_false")

    print("Example 2 generated.")

# -------------------------------------------------------------------------
# Example 3: Local merge versus final merge
# -------------------------------------------------------------------------
def run_example_3():
    def build_model(exclude_right_from_final_merge):
        model = Model()
        soil_material = model.material.nd.elastic_isotropic("soil", E=1.0, nu=0.3, rho=1.0)
        brick = model.element.brick.std(ndof=3, material=soil_material)

        left_a = model.meshpart.volume.uniform_rectangular_grid("left_a", element=brick, x_min=0.0, x_max=1.0, y_min=0.0, y_max=1.0, z_min=0.0, z_max=1.0, nx=1, ny=1, nz=1)
        left_b = model.meshpart.volume.uniform_rectangular_grid("left_b", element=brick, x_min=1.0, x_max=2.0, y_min=0.0, y_max=1.0, z_min=0.0, z_max=1.0, nx=1, ny=1, nz=1)
        right_a = model.meshpart.volume.uniform_rectangular_grid("right_a", element=brick, x_min=2.0, x_max=3.0, y_min=0.0, y_max=1.0, z_min=0.0, z_max=1.0, nx=1, ny=1, nz=1)
        right_b = model.meshpart.volume.uniform_rectangular_grid("right_b", element=brick, x_min=3.0, x_max=4.0, y_min=0.0, y_max=1.0, z_min=0.0, z_max=1.0, nx=1, ny=1, nz=1)

        left_section = model.assembler.create_section(meshparts=["left_a", "left_b"], merge_points=True, merge_in_final=True)
        right_section = model.assembler.create_section(meshparts=["right_a", "right_b"], merge_points=False, merge_in_final=not exclude_right_from_final_merge)

        model.assembler.assemble(merge_points=True)
        return left_section, right_section, model

    left_section_a, right_section_a, model_excluded = build_model(True)
    left_section_b, right_section_b, model_included = build_model(False)

    cam_pos = [(2.0, -4.0, 3.0), (2.0, 0.0, 0.5), (0, 0, 1)]

    # Left Section (Merged)
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    mesh = left_section_a.mesh.copy()
    plot_mesh(pl, mesh, scalars="MeshPartTag_celldata", cmap=["blue", "green"], show_points=True)
    pl.camera_position = cam_pos
    save_plot(pl, "local_vs_final_merge_left_section")

    # Right Section (Unmerged)
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    mesh = right_section_a.mesh.copy()
    pts = mesh.points.copy()
    if len(pts) == 16:
        pts[8:, 1] += 0.2  # Shift right_b visually
    mesh.points = pts
    plot_mesh(pl, mesh, scalars="MeshPartTag_celldata", cmap=["red", "purple"], show_points=True)
    pl.camera_position = cam_pos
    save_plot(pl, "local_vs_final_merge_right_section")

    # Final Excluded (28 points)
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    mesh = model_excluded.assembled_mesh.copy()
    pts = mesh.points.copy()
    if len(pts) == 28:
        pts[12:, 1] += 0.2 # Shift right section visually
        pts[20:, 1] += 0.2 # Shift right_b additionally
    mesh.points = pts
    plot_mesh(pl, mesh, scalars="MeshPartTag_celldata", cmap=["blue", "green", "red", "purple"], show_points=True)
    pl.camera_position = cam_pos
    save_plot(pl, "local_vs_final_merge_final_excluded")

    # Final Included (20 points)
    pl = pv.Plotter(off_screen=True)
    pl.add_axes()
    mesh = model_included.assembled_mesh.copy()
    plot_mesh(pl, mesh, scalars="MeshPartTag_celldata", cmap=["blue", "green", "red", "purple"], show_points=True)
    pl.camera_position = cam_pos
    save_plot(pl, "local_vs_final_merge_final_included")

    print("Example 3 generated.")

# -------------------------------------------------------------------------
# Example 4: Single-core versus partitioned domain
# -------------------------------------------------------------------------
def run_example_4():
    def build_model(partitions, partitioner=None):
        model = Model()
        soil_material = model.material.nd.elastic_isotropic("soil", E=1.0, nu=0.3, rho=1.0)
        brick = model.element.brick.std(ndof=3, material=soil_material)

        model.meshpart.volume.uniform_rectangular_grid("soil", element=brick, x_min=0.0, x_max=2.0, y_min=0.0, y_max=1.0, z_min=0.0, z_max=1.0, nx=2, ny=1, nz=1)
        
        if partitioner:
            model.assembler.create_section(meshparts=["soil"], num_partitions=partitions, partitioner=partitioner)
        else:
            model.assembler.create_section(meshparts=["soil"], num_partitions=partitions)

        model.assembler.assemble()
        return model.assembled_mesh

    mesh_single = build_model(1)
    mesh_part = build_model(2, "kd-tree")

    # Single core
    pl = pv.Plotter(off_screen=True)
    plot_mesh(pl, mesh_single, scalars="Core", cmap="viridis", show_points=False)
    pl.camera_position = 'iso'
    save_plot(pl, "partitioning_single_core")

    # Partitioned
    pl = pv.Plotter(off_screen=True)
    plot_mesh(pl, mesh_part, scalars="Core", cmap="coolwarm", show_points=False)
    pl.camera_position = 'iso'
    save_plot(pl, "partitioning_partitioned")

    # Overview PNG
    pl = pv.Plotter(off_screen=True)
    plot_mesh(pl, mesh_part, scalars="Core", cmap="coolwarm", show_points=False)
    pl.camera_position = 'iso'
    save_plot(pl, "partitioning_overview", save_png=True)
    print("Example 4 generated.")

if __name__ == "__main__":
    run_example_1()
    run_example_2()
    run_example_3()
    run_example_4()
    print("All assets generated.")
