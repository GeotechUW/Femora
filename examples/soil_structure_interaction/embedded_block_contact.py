# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-postprocess: examples/soil_structure_interaction/embedded_block_contact_postprocess.py

"""Build and optionally run a foundation block with frictional soil contact."""

from __future__ import annotations

import os
from pathlib import Path

from femora import Model, runtime


# --8<-- [start:configuration]
OUTPUT_DIR = Path("example_outputs") / "embedded_block_contact"
RESULTS_DIR = OUTPUT_DIR / "results"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_INTERFACES = False

TOTAL_LATERAL_LOAD = 150.0  # kN
LATERAL_DT = 1.0e-5
LATERAL_DURATION = 1.0
# --8<-- [end:configuration]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

model = Model(model_name="embedded_block_contact", model_path=str(OUTPUT_DIR))
model.clear_model()
model.set_results_folder(RESULTS_DIR.resolve().as_posix())

# --8<-- [start:mesh]
# Units are kN, m, tonne, and s.
soil = model.material.nd.elastic_isotropic(
    user_name="soil", E=377000.0, nu=0.3, rho=19.9 / 9.81
)
soil_element = model.element.brick.std(
    ndof=3, material=soil, b1=0.0, b2=0.0, b3=-19.9, lumped=True
)
model.meshpart.volume.geometric_rectangular_grid(
    user_name="soil",
    element=soil_element,
    x_min=-2.5, x_max=2.5,
    y_min=-2.5, y_max=2.5,
    z_min=-5.0, z_max=0.0,
    nx=4, ny=4, nz=4,
)

concrete = model.material.nd.elastic_isotropic(
    user_name="concrete", E=30.0e6, nu=0.2, rho=2.5
)
block_element = model.element.brick.std(
    ndof=3, material=concrete, b1=0.0, b2=0.0, b3=-24.525, lumped=True
)
model.meshpart.volume.geometric_rectangular_grid(
    user_name="foundation_block",
    element=block_element,
    x_min=-1.0, x_max=1.0,
    y_min=-1.0, y_max=1.0,
    z_min=-0.25, z_max=1.75,
    nx=4, ny=4, nz=4,
)
# --8<-- [end:mesh]

# --8<-- [start:interfaces]
model.assembler.create_section(
    meshparts=["soil", "foundation_block"],
    num_partitions=0,
    merge_points=False,
)

# The filters select the five buried faces by their outward block normals.
contact_bottom = model.interface.node_interface(
    name="block_soil_contact_bottom",
    constrained_node="foundation_block",
    retained_nodes=["soil"],
    normal_filter=[0.0, 0.0, -1.0],
    contact=True, Kn=1.0e8, Kt=1.0e8, mu=0.5, int_type=1,
)
contact_x_min = model.interface.node_interface(
    name="block_soil_contact_x_min",
    constrained_node="foundation_block",
    retained_nodes=["soil"],
    normal_filter=[-1.0, 0.0, 0.0],
    contact=True, Kn=1.0e8, Kt=1.0e8, mu=0.5, int_type=1,
)
contact_x_max = model.interface.node_interface(
    name="block_soil_contact_x_max",
    constrained_node="foundation_block",
    retained_nodes=["soil"],
    normal_filter=[1.0, 0.0, 0.0],
    contact=True, Kn=1.0e8, Kt=1.0e8, mu=0.5, int_type=1,
)
contact_y_min = model.interface.node_interface(
    name="block_soil_contact_y_min",
    constrained_node="foundation_block",
    retained_nodes=["soil"],
    normal_filter=[0.0, -1.0, 0.0],
    contact=True, Kn=1.0e8, Kt=1.0e8, mu=0.5, int_type=1,
)
contact_y_max = model.interface.node_interface(
    name="block_soil_contact_y_max",
    constrained_node="foundation_block",
    retained_nodes=["soil"],
    normal_filter=[0.0, 1.0, 0.0],
    contact=True, Kn=1.0e8, Kt=1.0e8, mu=0.5, int_type=1,
)

model.assembler.assemble(merge_points=False, progress_callback=lambda *_: None)
# --8<-- [end:interfaces]

model.constraint.mp.laminar_boundary(
    bounds=(-4.9, 0.0), dofs=[1, 2, 3], direction=3
)
model.constraint.sp.fix_macro_z_min(dofs=[1, 1, 1], tol=1.0e-3)

# --8<-- [start:gravity]
# Contact begins closed, so an implicit step efficiently establishes gravity.
gravity_analysis = model.analysis.static(
    name="implicit_gravity",
    constraint_handler=model.analysis.constraint.transformation(),
    numberer=model.analysis.numberer.rcm(),
    system=model.analysis.system.bandgeneral(),
    test=model.analysis.test.normdispincr(tol=1.0e-8, max_iter=30),
    algorithm=model.analysis.algorithm.newton(),
    integrator=model.analysis.integrator.loadcontrol(incr=1.0),
    num_steps=1,
)
model.process.add_step(gravity_analysis, "Establish equilibrium under self-weight")
model.process.add_step(model.actions.load_const(), "Keep the gravity state")
model.process.add_step(model.actions.set_time(0.0), "Reset time for lateral loading")
# --8<-- [end:gravity]

# --8<-- [start:lateral-loading]
top_nodes = model.mask.nodes.by_bbox(
    xmin=-1.001, xmax=1.001,
    ymin=-1.001, ymax=1.001,
    zmin=1.749, zmax=1.751,
)
if len(top_nodes) != 25:
    raise RuntimeError(f"Expected 25 block-top nodes, found {len(top_nodes)}")

lateral_series = model.time_series.ramp(
    tStart=0.0, tRamp=LATERAL_DURATION, smoothness=1.0
)
lateral_pattern = model.pattern.plain(time_series=lateral_series)
lateral_pattern.add_load.node(
    node_mask=top_nodes,
    values=[TOTAL_LATERAL_LOAD / len(top_nodes), 0.0, 0.0],
)

response_recorder = model.recorder.vtkhdf(
    file_base_name="block_contact.vtkhdf",
    resp_types=["disp"],
    delta_t=0.01,
)
explicit_lateral = model.analysis.transient(
    name="explicit_lateral_loading",
    constraint_handler=model.analysis.constraint.transformation(),
    numberer=model.analysis.numberer.rcm(),
    system=model.analysis.system.bandgeneral(),
    test=model.analysis.test.normdispincr(tol=1.0e-8, max_iter=1),
    algorithm=model.analysis.algorithm.linear(),
    integrator=model.analysis.integrator.explicitdifference(),
    dt=LATERAL_DT,
    num_steps=round(LATERAL_DURATION / LATERAL_DT),
    max_retries=0,
    initialize=True,
)
model.process.add_step(response_recorder, "Record the deformation animation")
model.process.add_step(lateral_pattern, "Ramp the distributed lateral load")
model.process.add_step(explicit_lateral, "Rock the block with explicit integration")
# --8<-- [end:lateral-loading]

# --8<-- [start:export-and-run]
tcl_file = OUTPUT_DIR / "embedded_block_contact.tcl"
model.export_to_tcl(str(tcl_file.resolve()), progress_callback=lambda *_: None)

print("\nEmbedded block contact")
print(f"  Nodes:       {model.assembled_mesh.n_points}")
print(f"  Elements:    {model.assembled_mesh.n_cells}")
print(f"  Tcl model:   {tcl_file.resolve()}")
if OPENSEES is None:
    print("  Solver:      not run (set FEMORA_OPENSEES to a compatible OpenSees executable)")
else:
    runtime.run(tcl_file, executable=OPENSEES, cwd=OUTPUT_DIR.resolve())
    print("  Solver:      completed")
# --8<-- [end:export-and-run]

if PLOT_INTERFACES:
    contact_bottom.plot(show_mesh=True, show_selected_hosts=True, show_normals=True)
    contact_x_min.plot(show_mesh=True, show_selected_hosts=True, show_normals=True)
    contact_x_max.plot(show_mesh=True, show_selected_hosts=True, show_normals=True)
    contact_y_min.plot(show_mesh=True, show_selected_hosts=True, show_normals=True)
    contact_y_max.plot(show_mesh=True, show_selected_hosts=True, show_normals=True)
