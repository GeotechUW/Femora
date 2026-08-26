# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-input: examples/inputs/motions/FrequencySweep.acc
# femora-colab-input: examples/inputs/motions/FrequencySweep.time
# femora-postprocess: examples/site_response/layered_elastic_soil_column_postprocess.py

# %% [markdown]
# # Layered Elastic Soil Column
#
# Build a five-mesh-part, three-stratum soil column, apply a frequency-sweep
# base excitation, and record the transient response in VTKHDF format.

# %%
"""Run a layered elastic site-response model with the current Femora API."""

from __future__ import annotations

import os
from pathlib import Path

from femora import Model, runtime
from femora.utils.paths import motions_dir


# --8<-- [start:configuration]
OUTPUT_DIR = Path("example_outputs") / "layered_elastic_soil_column"
RESULTS_DIR = OUTPUT_DIR / "results"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_MODEL = False

COLUMN_WIDTH = 1.0
COLUMN_DEPTH = 18.0
GRAVITY = 9.81
MOTION_SCALE = GRAVITY
DYNAMIC_DT = 0.001
DYNAMIC_FINAL_TIME = 50.0

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
# ## Create the model and damping region
#
# The example uses kN, m, and s. Material stiffness and density are converted
# from SI values before they are passed to OpenSees.

# %%
# --8<-- [start:model-and-damping]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model = Model(
    model_name="layered_elastic_soil_column",
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
# --8<-- [end:model-and-damping]


# %% [markdown]
# ## Build the layered column
#
# Each layer owns its material, brick-element definition, and mesh part. The
# layer table drives the complete profile from the base upward.

# %%
# --8<-- [start:layered-mesh]
z_bottom = -COLUMN_DEPTH
layer_names = []

for layer in LAYERS:
    name = layer["name"]
    shear_modulus = layer["shear_modulus"]
    unit_weight = layer["unit_weight"]
    poisson_ratio = layer["poisson_ratio"]
    thickness = layer["thickness"]
    element_size = layer["element_size"]

    density_si = unit_weight * 1_000.0 / GRAVITY
    shear_velocity = (shear_modulus / density_si) ** 0.5
    young_modulus_si = 2.0 * shear_modulus * (1.0 + poisson_ratio)

    # Convert Pa to kPa and kg/m^3 to Mg/m^3 for the kN-m-s unit system.
    young_modulus = young_modulus_si / 1_000.0
    density = density_si / 1_000.0

    print(f"{name:24s} Vs = {shear_velocity:7.2f} m/s")

    material = model.material.nd.elastic_isotropic(
        user_name=f"{name}_material",
        E=young_modulus,
        nu=poisson_ratio,
        rho=density,
    )
    element = model.element.brick.std(
        ndof=3,
        material=material,
        b1=0.0,
        b2=0.0,
        b3=-GRAVITY * density,
    )

    number_of_elements = round(thickness / element_size)
    model.meshpart.volume.uniform_rectangular_grid(
        user_name=name,
        element=element,
        region=soil_region,
        x_min=0.0,
        x_max=COLUMN_WIDTH,
        y_min=0.0,
        y_max=COLUMN_WIDTH,
        z_min=z_bottom,
        z_max=z_bottom + thickness,
        nx=1,
        ny=1,
        nz=number_of_elements,
    )
    layer_names.append(name)
    z_bottom += thickness

if abs(z_bottom) > 1.0e-9:
    raise RuntimeError(f"Layer thicknesses terminate at z={z_bottom}, expected z=0")
# --8<-- [end:layered-mesh]


# %% [markdown]
# ## Assemble and constrain the column
#
# The assembly merges coincident layer boundaries. Laminar constraints tie
# nodes at each elevation, and the base is fixed in all translational DOFs.

# %%
# --8<-- [start:assembly-and-constraints]
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
model.constraint.sp.fix_macro_z_min(
    dofs=[1, 1, 1],
    tol=1.0e-6,
)
# --8<-- [end:assembly-and-constraints]


# %% [markdown]
# ## Define excitation and output
#
# The acceleration and time files form one nonuniform Path time series. A
# uniform-excitation pattern applies it in the global x direction.

# %%
# --8<-- [start:excitation-and-output]
motion_directory = motions_dir()
excitation = model.time_series.path(
    filePath=(motion_directory / "FrequencySweep.acc").resolve().as_posix(),
    fileTime=(motion_directory / "FrequencySweep.time").resolve().as_posix(),
    factor=MOTION_SCALE,
)
uniform_excitation = model.pattern.uniform_excitation(
    dof=1,
    time_series=excitation,
)

response_recorder = model.recorder.vtkhdf(
    file_base_name="site_response.vtkhdf",
    resp_types=["accel", "disp", "vel"],
    delta_t=0.01,
)
# --8<-- [end:excitation-and-output]


# %% [markdown]
# ## Define the staged analyses
#
# Gravity is established first with large transient steps. Femora then resets
# pseudo-time and runs the frequency-sweep excitation with a smaller time step.

# %%
# --8<-- [start:analyses-and-process]
constraint_handler = model.analysis.constraint.transformation()
numberer = model.analysis.numberer.rcm()
system = model.analysis.system.bandgeneral()
algorithm = model.analysis.algorithm.linear()
test = model.analysis.test.normunbalance(tol=1.0e-8, max_iter=10)

newmark_gamma = 0.6
newmark_beta = (newmark_gamma + 0.5) ** 2 / 4.0
integrator = model.analysis.integrator.newmark(
    gamma=newmark_gamma,
    beta=newmark_beta,
)

gravity_analysis = model.analysis.transient(
    name="gravity",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=algorithm,
    test=test,
    integrator=integrator,
    dt=1.0,
    num_steps=30,
)
dynamic_analysis = model.analysis.transient(
    name="frequency_sweep",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=algorithm,
    test=test,
    integrator=integrator,
    dt=DYNAMIC_DT,
    final_time=DYNAMIC_FINAL_TIME,
)

model.process.add_step(gravity_analysis, "Establish gravity")
model.process.add_step(uniform_excitation, "Apply the base excitation")
model.process.add_step(response_recorder, "Record the column response")
model.process.add_step(model.actions.set_time(0.0), "Reset pseudo-time")
model.process.add_step(dynamic_analysis, "Run the site-response analysis")
# --8<-- [end:analyses-and-process]


# %% [markdown]
# ## Export and optionally execute

# %%
# --8<-- [start:export-and-run]
tcl_file = OUTPUT_DIR / "layered_elastic_soil_column.tcl"
model.export_to_tcl(
    filename=str(tcl_file.resolve()),
    progress_callback=lambda *_: None,
)

print("\nLayered elastic soil column")
print(f"  Nodes:       {model.assembled_mesh.n_points}")
print(f"  Elements:    {model.assembled_mesh.n_cells}")
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
    model.assembler.plot(
        show_edges=True,
        scalars="MaterialTag",
    )
