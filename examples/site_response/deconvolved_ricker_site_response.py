# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-input: examples/inputs/motions/ricker_surface.acc
# femora-colab-input: examples/inputs/motions/ricker_surface.time
# femora-postprocess: examples/site_response/deconvolved_ricker_site_response_postprocess.py

# %% [markdown]
# # Deconvolved Ricker-Wave Site Response
#
# Start from a target surface acceleration, deconvolve it through an elastic
# layered profile, and apply the resulting base motion to a Femora model.

# %%
"""Run elastic site response using a deconvolved Ricker-wave base motion."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from femora import Model, runtime
from femora.tools.transferFunction import TimeHistory, TransferFunction
from femora.utils.paths import motions_dir


# --8<-- [start:configuration]
OUTPUT_DIR = Path("example_outputs") / "deconvolved_ricker_site_response"
RESULTS_DIR = OUTPUT_DIR / "results"
MOTIONS_OUTPUT_DIR = OUTPUT_DIR / "motions"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_MODEL = False

COLUMN_WIDTH = 1.0
COLUMN_DEPTH = 18.0
GRAVITY = 9.81
DYNAMIC_DT = 0.001
DYNAMIC_FINAL_TIME = 5.0

LAYERS = [
    {
        "name": "dense_ottawa_lower",
        "shear_modulus": 145.0e6,
        "unit_weight": 19.9,
        "poisson_ratio": 0.3,
        "thickness": 2.6,
        "element_size": 1.3,
    },
    {
        "name": "dense_ottawa_middle",
        "shear_modulus": 145.0e6,
        "unit_weight": 19.9,
        "poisson_ratio": 0.3,
        "thickness": 2.4,
        "element_size": 1.2,
    },
    {
        "name": "dense_ottawa_upper",
        "shear_modulus": 145.0e6,
        "unit_weight": 19.9,
        "poisson_ratio": 0.3,
        "thickness": 5.0,
        "element_size": 1.0,
    },
    {
        "name": "loose_ottawa",
        "shear_modulus": 75.0e6,
        "unit_weight": 19.1,
        "poisson_ratio": 0.3,
        "thickness": 6.0,
        "element_size": 0.5,
    },
    {
        "name": "dense_monterey",
        "shear_modulus": 42.0e6,
        "unit_weight": 19.8,
        "poisson_ratio": 0.3,
        "thickness": 2.0,
        "element_size": 0.5,
    },
]
# --8<-- [end:configuration]


# %% [markdown]
# ## Deconvolve the target surface motion
#
# The analytical profile maps base motion to surface motion. Deconvolution
# applies the inverse of that transfer function to obtain the required input.

# %%
# --8<-- [start:deconvolution]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MOTIONS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

motion_directory = motions_dir()
target_surface_motion = TimeHistory.load(
    acc_file=str(motion_directory / "ricker_surface.acc"),
    time_file=str(motion_directory / "ricker_surface.time"),
    unit_in_g=True,
    gravity=GRAVITY,
)

analytical_profile = [
    {
        "h": 2.0,
        "vs": 144.2535646321813,
        "rho": 19.8 * 1_000.0 / GRAVITY,
        "damping": 0.03,
        "damping_type": "rayleigh",
        "f1": 2.76,
        "f2": 13.84,
    },
    {
        "h": 6.0,
        "vs": 196.2675276462639,
        "rho": 19.1 * 1_000.0 / GRAVITY,
        "damping": 0.03,
        "damping_type": "rayleigh",
        "f1": 2.76,
        "f2": 13.84,
    },
    {
        "h": 10.0,
        "vs": 262.5199305117452,
        "rho": 19.9 * 1_000.0 / GRAVITY,
        "damping": 0.03,
        "damping_type": "rayleigh",
        "f1": 2.76,
        "f2": 13.84,
    },
]
rock = {"vs": 8_000.0, "rho": 2_000.0, "damping": 0.0}
transfer_function = TransferFunction(
    soil_profile=analytical_profile,
    rock=rock,
    f_max=50.0,
)
base_motion, aligned_target_motion, _ = transfer_function.deconvolve(
    target_surface_motion,
    return_all=True,
)

base_acceleration_file = MOTIONS_OUTPUT_DIR / "ricker_base.acc"
base_time_file = MOTIONS_OUTPUT_DIR / "ricker_base.time"
target_acceleration_file = MOTIONS_OUTPUT_DIR / "ricker_surface_aligned.acc"
target_time_file = MOTIONS_OUTPUT_DIR / "ricker_surface_aligned.time"

np.savetxt(base_acceleration_file, base_motion.acceleration, fmt="%.10e")
np.savetxt(base_time_file, base_motion.time, fmt="%.10e")
np.savetxt(
    target_acceleration_file,
    aligned_target_motion.acceleration,
    fmt="%.10e",
)
np.savetxt(target_time_file, aligned_target_motion.time, fmt="%.10e")
# --8<-- [end:deconvolution]


# %% [markdown]
# ## Build the layered column

# %%
# --8<-- [start:model-and-mesh]
model = Model(
    model_name="deconvolved_ricker_site_response",
    model_path=str(OUTPUT_DIR.resolve()),
)
model.set_results_folder(RESULTS_DIR.resolve().as_posix())

rayleigh_damping = model.damping.frequency_rayleigh(
    user_name="soil_damping",
    f1=2.76,
    f2=13.84,
    damping_factor=0.03,
)
soil_region = model.region.element(
    user_name="soil_column",
    damping=rayleigh_damping,
)

z_bottom = -COLUMN_DEPTH
layer_names = []
for layer in LAYERS:
    density_si = layer["unit_weight"] * 1_000.0 / GRAVITY
    density = density_si / 1_000.0
    young_modulus = (
        2.0
        * layer["shear_modulus"]
        * (1.0 + layer["poisson_ratio"])
        / 1_000.0
    )
    material = model.material.nd.elastic_isotropic(
        user_name=f"{layer['name']}_material",
        E=young_modulus,
        nu=layer["poisson_ratio"],
        rho=density,
    )
    element = model.element.brick.std(
        ndof=3,
        material=material,
        b1=0.0,
        b2=0.0,
        b3=-GRAVITY * density,
    )
    model.meshpart.volume.uniform_rectangular_grid(
        user_name=layer["name"],
        element=element,
        region=soil_region,
        x_min=0.0,
        x_max=COLUMN_WIDTH,
        y_min=0.0,
        y_max=COLUMN_WIDTH,
        z_min=z_bottom,
        z_max=z_bottom + layer["thickness"],
        nx=1,
        ny=1,
        nz=round(layer["thickness"] / layer["element_size"]),
    )
    layer_names.append(layer["name"])
    z_bottom += layer["thickness"]

if abs(z_bottom) > 1.0e-9:
    raise RuntimeError(f"Layer thicknesses terminate at z={z_bottom}, expected z=0")
# --8<-- [end:model-and-mesh]


# %% [markdown]
# ## Assemble, constrain, and excite the model

# %%
# --8<-- [start:assembly-loading-and-output]
model.assembler.create_section(
    meshparts=layer_names,
    num_partitions=0,
    merge_points=True,
)
model.assembler.assemble(merge_points=True, progress_callback=lambda *_: None)

model.constraint.mp.laminar_boundary(
    bounds=(-COLUMN_DEPTH + 0.1, 0.0),
    dofs=[1, 2, 3],
    direction=3,
)
model.constraint.sp.fix_macro_z_min(dofs=[1, 1, 1], tol=1.0e-6)

base_time_series = model.time_series.path(
    filePath=base_acceleration_file.resolve().as_posix(),
    fileTime=base_time_file.resolve().as_posix(),
    factor=GRAVITY,
)
uniform_excitation = model.pattern.uniform_excitation(
    dof=1,
    time_series=base_time_series,
)
response_recorder = model.recorder.vtkhdf(
    file_base_name="site_response.vtkhdf",
    resp_types=["accel", "disp", "vel"],
    delta_t=DYNAMIC_DT,
)
# --8<-- [end:assembly-loading-and-output]


# %% [markdown]
# ## Define and run the staged analysis

# %%
# --8<-- [start:analysis-and-process]
constraint_handler = model.analysis.constraint.transformation()
numberer = model.analysis.numberer.rcm()
system = model.analysis.system.bandgeneral()
algorithm = model.analysis.algorithm.linear()
test = model.analysis.test.normunbalance(tol=1.0e-8, max_iter=10)

newmark_gamma = 0.6
newmark_beta = (newmark_gamma + 0.5) ** 2 / 4.0
gravity_integrator = model.analysis.integrator.newmark(
    gamma=newmark_gamma,
    beta=newmark_beta,
)
dynamic_integrator = model.analysis.integrator.newmark(
    gamma=0.5,
    beta=0.25,
)
gravity_analysis = model.analysis.transient(
    name="gravity",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=algorithm,
    test=test,
    integrator=gravity_integrator,
    dt=1.0,
    num_steps=30,
)
dynamic_analysis = model.analysis.transient(
    name="ricker_wave",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=algorithm,
    test=test,
    integrator=dynamic_integrator,
    dt=DYNAMIC_DT,
    final_time=DYNAMIC_FINAL_TIME,
)

model.process.add_step(gravity_analysis, "Establish gravity")
model.process.add_step(uniform_excitation, "Apply the deconvolved base motion")
model.process.add_step(response_recorder, "Record the column response")
model.process.add_step(model.actions.set_time(0.0), "Reset pseudo-time")
model.process.add_step(dynamic_analysis, "Run the Ricker-wave analysis")
# --8<-- [end:analysis-and-process]


# %% [markdown]
# ## Export and optionally execute

# %%
# --8<-- [start:export-and-run]
tcl_file = OUTPUT_DIR / "deconvolved_ricker_site_response.tcl"
model.export_to_tcl(
    filename=str(tcl_file.resolve()),
    progress_callback=lambda *_: None,
)

print("\nDeconvolved Ricker-wave site response")
print(f"  Nodes:          {model.assembled_mesh.n_points}")
print(f"  Elements:       {model.assembled_mesh.n_cells}")
print(f"  Base samples:   {base_motion.time.size}")
print(f"  Base motion:    {base_acceleration_file.resolve()}")
print(f"  Tcl model:      {tcl_file.resolve()}")

if OPENSEES is None:
    print("  Solver:         not run (set FEMORA_OPENSEES to run OpenSees)")
else:
    runtime.run(
        tcl_file,
        executable=OPENSEES,
        cwd=OUTPUT_DIR.resolve(),
    )
    print("  Solver:         completed")
# --8<-- [end:export-and-run]


# %% [markdown]
# ## Optional visualization

# %%
if PLOT_MODEL:
    model.assembler.plot(show_edges=True, scalars="MaterialTag")
