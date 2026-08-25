# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# %% [markdown]
# # Elastic Cantilever with Femora
#
# Build a four-element 3D cantilever, run it with OpenSees, and compare the
# computed tip displacement with the Euler-Bernoulli solution.

# %%
"""Build and solve a small elastic cantilever with the current Femora API."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import numpy as np

from femora import Model


# --8<-- [start:configuration]
LENGTH = 4.0
TIP_LOAD = -1_000.0
ELASTIC_MODULUS = 200.0e9
AREA = 0.04
SECOND_MOMENT = 1.333333333e-4
SHEAR_MODULUS = 76.923e9
TORSIONAL_CONSTANT = 2.25e-4

OUTPUT_DIR = Path("example_outputs") / "elastic_cantilever"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_MODEL = False
# --8<-- [end:configuration]


# %% [markdown]
# ## Create the building blocks
#
# The section and transformation define the beam behavior. The element combines
# those reusable definitions into the formulation used by the line mesh part.

# %%
# --8<-- [start:building-blocks]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model = Model(
    model_name="elastic_cantilever",
    model_path=str(OUTPUT_DIR.resolve()),
)
model.set_results_folder(OUTPUT_DIR.resolve().as_posix())

section = model.section.beam.elastic(
    user_name="cantilever_section",
    E=ELASTIC_MODULUS,
    A=AREA,
    Iz=SECOND_MOMENT,
    Iy=SECOND_MOMENT,
    G=SHEAR_MODULUS,
    J=TORSIONAL_CONSTANT,
)
transformation = model.transformation.transformation3d(
    transf_type="Linear",
    vecxz_x=0.0,
    vecxz_y=0.0,
    vecxz_z=1.0,
)
beam_element = model.element.beam.elastic(
    ndof=6,
    section=section,
    transformation=transformation,
)
# --8<-- [end:building-blocks]


# %% [markdown]
# ## Mesh and assemble the member
#
# Femora creates four independent line elements and compiles them into the
# assembled model.

# %%
# --8<-- [start:mesh-and-assembly]
model.meshpart.line.single_line(
    user_name="cantilever",
    element=beam_element,
    x0=0.0,
    y0=0.0,
    z0=0.0,
    x1=LENGTH,
    y1=0.0,
    z1=0.0,
    number_of_lines=4,
)
model.assembler.create_section(
    ["cantilever"],
    num_partitions=0,
    merge_points=True,
)
model.assembler.assemble(merge_points=True, progress_callback=lambda *_: None)
# --8<-- [end:mesh-and-assembly]


# %% [markdown]
# ## Constrain and select the assembled nodes
#
# Fix the root and locate the tip geometrically instead of predicting its solver
# tag.

# %%
# --8<-- [start:constraints-and-selection]
model.constraint.sp.fix_x(
    xCoordinate=0.0,
    dofs=[1, 1, 1, 1, 1, 1],
    tol=1.0e-9,
)

tip_nodes = model.mask.nodes.near_point(
    point=(LENGTH, 0.0, 0.0),
    radius=1.0e-9,
)
if len(tip_nodes) != 1:
    raise RuntimeError(f"Expected one cantilever tip node, found {len(tip_nodes)}")
# --8<-- [end:constraints-and-selection]


# %% [markdown]
# ## Apply the load and record the response
#
# The load pattern and recorder both act on the selected tip node.

# %%
# --8<-- [start:loading-and-recording]
load_history = model.time_series.linear(factor=1.0)
lateral_load = model.pattern.plain(time_series=load_history)
lateral_load.add_load.node(
    node_mask=tip_nodes,
    values=[0.0, 0.0, TIP_LOAD, 0.0, 0.0, 0.0],
)

displacement_file = OUTPUT_DIR / "tip_displacement.out"
tip_recorder = model.recorder.node(
    file_name=displacement_file.resolve().as_posix(),
    nodes=tip_nodes.to_tags(),
    dofs=[3],
    resp_type="disp",
    time=True,
    precision=12,
)
# --8<-- [end:loading-and-recording]


# %% [markdown]
# ## Define the analysis and process
#
# The analysis stores the solution settings. The process places the pattern,
# recorder, and analysis into the exported execution sequence.

# %%
# --8<-- [start:analysis-and-process]
static_analysis = model.analysis.static(
    name="tip_load",
    constraint_handler=model.analysis.constraint.transformation(),
    numberer=model.analysis.numberer.rcm(),
    system=model.analysis.system.bandgeneral(),
    algorithm=model.analysis.algorithm.linear(),
    test=model.analysis.test.normunbalance(tol=1.0e-10, max_iter=10),
    integrator=model.analysis.integrator.loadcontrol(incr=0.1),
    num_steps=10,
)

model.process.add_step(lateral_load, "Apply the cantilever tip load")
model.process.add_step(tip_recorder, "Record the tip displacement")
model.process.add_step(static_analysis, "Run the linear static analysis")
# --8<-- [end:analysis-and-process]


# %% [markdown]
# ## Export the model

# %%
# --8<-- [start:export-model]
tcl_file = OUTPUT_DIR / "elastic_cantilever.tcl"
model.export_to_tcl(
    filename=str(tcl_file.resolve()),
    progress_callback=lambda *_: None,
)

print("\nElastic cantilever model")
print(f"  Nodes:       {model.assembled_mesh.n_points}")
print(f"  Elements:    {model.assembled_mesh.n_cells}")
print(f"  Tcl model:   {tcl_file.resolve()}")
# --8<-- [end:export-model]


# %% [markdown]
# ## Run OpenSees and verify the response
#
# The Colab setup cell configures `FEMORA_OPENSEES` automatically. For a local
# run, set the same environment variable before executing this script.

# %%
# --8<-- [start:solve-and-verify]
if OPENSEES is None:
    print("  Solver:      not run (set FEMORA_OPENSEES to run OpenSees)")
else:
    completed = subprocess.run(
        [OPENSEES, str(tcl_file.resolve())],
        cwd=OUTPUT_DIR.resolve(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        if completed.stdout.strip():
            print(completed.stdout.rstrip())
        if completed.stderr.strip():
            print(completed.stderr.rstrip())
        raise RuntimeError(f"OpenSees failed with exit code {completed.returncode}")

    recorder_data = np.atleast_2d(np.loadtxt(displacement_file))
    numerical = float(recorder_data[-1, -1])
    analytical = TIP_LOAD * LENGTH**3 / (
        3.0 * ELASTIC_MODULUS * SECOND_MOMENT
    )
    relative_error = abs((numerical - analytical) / analytical)

    if not np.isclose(numerical, analytical, rtol=1.0e-9, atol=1.0e-12):
        raise RuntimeError(
            "Cantilever verification failed: "
            f"numerical={numerical:.12e}, analytical={analytical:.12e}"
        )

    print(f"  Tip disp.:   {numerical:.6e} m")
    print(f"  Analytical:  {analytical:.6e} m")
    print(f"  Rel. error:  {relative_error:.3e}")
    print("  Verification: passed")
# --8<-- [end:solve-and-verify]


# %% [markdown]
# ## Optional visualization

# %%
# --8<-- [start:visualization]
if PLOT_MODEL:
    model.assembled_mesh.plot(
        show_edges=True,
        line_width=5,
        color="#d67a2f",
        background="#f4f0e8",
    )
# --8<-- [end:visualization]
