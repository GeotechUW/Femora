# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-postprocess: examples/soil_structure_interaction/laterally_loaded_pile_postprocess.py

# %% [markdown]
# # Laterally Loaded Pile
#
# Embed a displacement-based pile in a graded elastic soil domain, apply a
# horizontal head load, and recover the pile force and moment distributions.

# %%
"""Build and optionally run the laterally loaded pile example."""

from __future__ import annotations

import math
import os
from pathlib import Path

from femora import Model, runtime


# --8<-- [start:configuration]
OUTPUT_DIR = Path("example_outputs") / "laterally_loaded_pile"
RESULTS_DIR = OUTPUT_DIR / "results"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_MODEL = False

SOIL_BOUNDS = (-8.0, 8.0, -8.0, 8.0, -10.0, 0.0)
SOIL_DIVISIONS = (8, 8, 10)
SOIL_GRADING_RATIO = 0.8

PILE_BOTTOM = (0.0, 0.0, -10.0)
PILE_HEAD = (0.0, 0.0, 1.0)
PILE_DIAMETER = 1.0
PILE_ELEMENTS = 20
HEAD_LOAD = 1.0e6
# --8<-- [end:configuration]


# %% [markdown]
# ## Build the graded soil domain
#
# Four independently graded mesh parts place smaller cells near the pile while
# preserving a wider far-field boundary. All values use a consistent N-m-s
# unit system.

# %%
# --8<-- [start:soil-domain]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
model = Model(
    model_name="laterally_loaded_pile",
    model_path=str(OUTPUT_DIR.resolve()),
)
model.set_results_folder(RESULTS_DIR.resolve().as_posix())

soil_material = model.material.nd.elastic_isotropic(
    user_name="elastic_soil",
    E=2.0e8,
    nu=0.4,
    rho=2100.0,
)
soil_element = model.element.brick.std(
    ndof=3,
    material=soil_material,
)

x_min, x_max, y_min, y_max, z_min, z_max = SOIL_BOUNDS
nx, ny, nz = SOIL_DIVISIONS
r = SOIL_GRADING_RATIO
soil_blocks = [
    ("soil_sw", x_min, 0.0, y_min, 0.0, r, r),
    ("soil_se", 0.0, x_max, y_min, 0.0, 1.0 / r, r),
    ("soil_nw", x_min, 0.0, 0.0, y_max, r, 1.0 / r),
    ("soil_ne", 0.0, x_max, 0.0, y_max, 1.0 / r, 1.0 / r),
]

soil_part_names = []
for name, block_x_min, block_x_max, block_y_min, block_y_max, x_ratio, y_ratio in soil_blocks:
    model.meshpart.volume.geometric_rectangular_grid(
        user_name=name,
        element=soil_element,
        x_min=block_x_min,
        x_max=block_x_max,
        y_min=block_y_min,
        y_max=block_y_max,
        z_min=z_min,
        z_max=z_max,
        nx=nx,
        ny=ny,
        nz=nz,
        x_ratio=x_ratio,
        y_ratio=y_ratio,
        z_ratio=r,
    )
    soil_part_names.append(name)
# --8<-- [end:soil-domain]


# %% [markdown]
# ## Define the pile
#
# The pile is a circular elastic beam-column with six degrees of freedom per
# node. Its line mesh crosses the ground surface and continues one meter above
# it so the loaded head remains visible and accessible.

# %%
# --8<-- [start:pile]
pile_radius = PILE_DIAMETER / 2.0
pile_E = 1.0e10
pile_nu = 0.3
pile_G = pile_E / (2.0 * (1.0 + pile_nu))
pile_area = math.pi * PILE_DIAMETER**2 / 4.0
pile_I = math.pi * PILE_DIAMETER**4 / 64.0
pile_J = math.pi * PILE_DIAMETER**4 / 32.0

pile_section = model.section.beam.elastic(
    user_name="pile_section",
    E=pile_E,
    A=pile_area,
    Iz=pile_I,
    Iy=pile_I,
    G=pile_G,
    J=pile_J,
)
pile_transformation = model.transformation.transformation3d(
    transf_type="PDelta",
    vecxz_x=-1.0,
    vecxz_y=0.0,
    vecxz_z=0.0,
)
pile_element = model.element.beam.disp(
    ndof=6,
    section=pile_section,
    transformation=pile_transformation,
    numIntgrPts=5,
)
model.meshpart.line.single_line(
    user_name="pile",
    element=pile_element,
    x0=PILE_BOTTOM[0],
    y0=PILE_BOTTOM[1],
    z0=PILE_BOTTOM[2],
    x1=PILE_HEAD[0],
    y1=PILE_HEAD[1],
    z1=PILE_HEAD[2],
    number_of_lines=PILE_ELEMENTS,
)
# --8<-- [end:pile]


# %% [markdown]
# ## Couple and assemble the model
#
# The interface is declared before assembly because it needs to observe the
# assembled pile and soil cells while Femora resolves their coupling.

# %%
# --8<-- [start:interface-and-assembly]
pile_soil_interface = model.interface.beam_solid_interface(
    name="pile_soil_interface",
    beam_part="pile",
    solid_parts=soil_part_names,
    radius=pile_radius,
    n_peri=8,
    n_long=4,
    penalty_param=1.0e12,
    g_penalty=True,
)

model.assembler.create_section(
    meshparts=soil_part_names,
    num_partitions=0,
    merge_points=True,
    tolerance=5.0e-2,
)
model.assembler.create_section(
    meshparts=["pile"],
    num_partitions=0,
    merge_points=False,
)
model.assembler.assemble(merge_points=True, progress_callback=lambda *_: None)

model.constraint.sp.fix_macro_x_min(dofs=[1, 1, 1], tol=1.0e-6)
model.constraint.sp.fix_macro_x_max(dofs=[1, 1, 1], tol=1.0e-6)
model.constraint.sp.fix_macro_y_min(dofs=[1, 1, 1], tol=1.0e-6)
model.constraint.sp.fix_macro_y_max(dofs=[1, 1, 1], tol=1.0e-6)
model.constraint.sp.fix_macro_z_min(dofs=[1, 1, 1], tol=1.0e-6)
# --8<-- [end:interface-and-assembly]


# %% [markdown]
# ## Apply the head load and record response

# %%
# --8<-- [start:loading-and-output]
pile_head_nodes = model.mask.nodes.near_point(point=PILE_HEAD, radius=1.0e-4)
if len(pile_head_nodes) != 1:
    raise RuntimeError(f"Expected one pile-head node, found {len(pile_head_nodes)}")

load_series = model.time_series.linear(factor=1.0)
lateral_pattern = model.pattern.plain(time_series=load_series)
lateral_pattern.add_load.node(
    node_mask=pile_head_nodes,
    values=[HEAD_LOAD, 0.0, 0.0, 0.0, 0.0, 0.0],
)

domain_recorder = model.recorder.vtkhdf(
    file_base_name="pile_response.vtkhdf",
    resp_types=["disp"],
)
pile_force_recorder = model.recorder.beam_force(
    meshparts=["pile"],
    force_type="globalForce",
    file_prefix="pile_force",
    include_time=True,
    output_format="xml",
)
# --8<-- [end:loading-and-output]


# %% [markdown]
# ## Define the static analysis and process

# %%
# --8<-- [start:analysis-and-process]
static_analysis = model.analysis.static(
    name="lateral_head_load",
    constraint_handler=model.analysis.constraint.penalty(
        alpha_s=1.0e15,
        alpha_m=1.0e15,
    ),
    numberer=model.analysis.numberer.rcm(),
    system=model.analysis.system.bandgeneral(),
    algorithm=model.analysis.algorithm.modifiednewton(factor_once=True),
    test=model.analysis.test.normdispincr(
        tol=1.0e-3,
        max_iter=5,
        print_flag=2,
    ),
    integrator=model.analysis.integrator.loadcontrol(incr=0.01),
    num_steps=100,
)

model.process.add_step(lateral_pattern, "Apply the lateral pile-head load")
model.process.add_step(domain_recorder, "Record the soil and pile displacement")
model.process.add_step(pile_force_recorder, "Record pile forces and moments")
model.process.add_step(static_analysis, "Run the static loading analysis")
# --8<-- [end:analysis-and-process]


# %% [markdown]
# ## Export and optionally execute

# %%
# --8<-- [start:export-and-run]
tcl_file = OUTPUT_DIR / "laterally_loaded_pile.tcl"
model.export_to_tcl(
    filename=str(tcl_file.resolve()),
    progress_callback=lambda *_: None,
)

print("\nLaterally loaded pile")
print(f"  Nodes:       {model.assembled_mesh.n_points}")
print(f"  Elements:    {model.assembled_mesh.n_cells}")
print(f"  Soil parts:  {len(soil_part_names)} graded blocks")
print(f"  Pile:        {PILE_ELEMENTS} beam elements")
print(f"  Tcl model:   {tcl_file.resolve()}")

if OPENSEES is None:
    print("  Solver:      not run (set FEMORA_OPENSEES to run OpenSees)")
else:
    runtime.run(
        tcl_file,
        executable=OPENSEES,
        cwd=OUTPUT_DIR.resolve(),
    )
    print("  Solver:      completed")
# --8<-- [end:export-and-run]


# %% [markdown]
# ## Optional visualization

# %%
if PLOT_MODEL:
    pile_soil_interface.plot(show_mesh=True, show_envelope=True)
