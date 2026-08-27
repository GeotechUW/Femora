# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-input: examples/inputs/motions/FrequencySweep.acc
# femora-colab-input: examples/inputs/motions/FrequencySweep.time
# femora-postprocess: examples/site_response/nonlinear_layered_soil_column_postprocess.py

# %% [markdown]
# # Nonlinear Layered Soil Column
#
# Build a staged PressureDependMultiYield soil profile, establish gravity in
# its elastic state, activate plasticity, and run transient site response.

# %%
"""Run a staged nonlinear layered-soil analysis with the current Femora API."""

from __future__ import annotations

import os
from pathlib import Path

from femora import Model, runtime
from femora.utils.paths import motions_dir


# --8<-- [start:configuration]
OUTPUT_DIR = Path("example_outputs") / "nonlinear_layered_soil_column"
RESULTS_DIR = OUTPUT_DIR / "results"
OPENSEES = os.environ.get("FEMORA_OPENSEES")
PLOT_MODEL = False

COLUMN_WIDTH = 1.0
COLUMN_DEPTH = 18.0
GRAVITY = 9.81
DYNAMIC_DT = 0.001
DYNAMIC_FINAL_TIME = 40.0
PEAK_SHEAR_STRAIN = 0.1
REFERENCE_PRESSURE = 80.0
PRESSURE_DEPENDENCE = 0.5

SOILS = {
    "dense_ottawa": {
        "shear_modulus": 145.0e6,
        "unit_weight": 19.9,
        "poisson_ratio": 0.3,
        "friction_angle": 40.0,
        "phase_transformation_angle": 27.0,
        "contraction": 0.03,
        "dilation_1": 0.8,
        "dilation_2": 5.0,
        "liquefaction_1": 0.0,
        "liquefaction_2": 0.0,
        "liquefaction_3": 0.0,
        "void_ratio": 0.45,
    },
    "loose_ottawa": {
        "shear_modulus": 75.0e6,
        "unit_weight": 19.1,
        "poisson_ratio": 0.3,
        "friction_angle": 29.0,
        "phase_transformation_angle": 29.0,
        "contraction": 0.21,
        "dilation_1": 0.0,
        "dilation_2": 0.0,
        "liquefaction_1": 10.0,
        "liquefaction_2": 0.02,
        "liquefaction_3": 1.0,
        "void_ratio": 0.85,
    },
    "dense_monterey": {
        "shear_modulus": 42.0e6,
        "unit_weight": 19.8,
        "poisson_ratio": 0.3,
        "friction_angle": 40.0,
        "phase_transformation_angle": 27.0,
        "contraction": 0.03,
        "dilation_1": 0.8,
        "dilation_2": 5.0,
        "liquefaction_1": 0.0,
        "liquefaction_2": 0.0,
        "liquefaction_3": 0.0,
        "void_ratio": 0.45,
    },
}

LAYERS = [
    ("dense_ottawa_lower", "dense_ottawa", 2.6, 1.3),
    ("dense_ottawa_middle", "dense_ottawa", 2.4, 1.2),
    ("dense_ottawa_upper", "dense_ottawa", 5.0, 1.0),
    ("loose_ottawa", "loose_ottawa", 6.0, 0.5),
    ("dense_monterey", "dense_monterey", 2.0, 0.5),
]
# --8<-- [end:configuration]


# %% [markdown]
# ## Define the nonlinear materials
#
# Femora uses a kN-m-s unit system here. Reference moduli are therefore
# converted from Pa to kPa and density from kg/m3 to Mg/m3.

# %%
# --8<-- [start:nonlinear-materials]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
model = Model(
    model_name="nonlinear_layered_soil_column",
    model_path=str(OUTPUT_DIR.resolve()),
)
model.set_results_folder(RESULTS_DIR.resolve().as_posix())

materials = {}
elements = {}
for soil_name, properties in SOILS.items():
    shear_modulus_si = properties["shear_modulus"]
    poisson_ratio = properties["poisson_ratio"]
    density_si = properties["unit_weight"] * 1_000.0 / GRAVITY

    shear_modulus = shear_modulus_si / 1_000.0
    bulk_modulus = (
        2.0
        * shear_modulus_si
        * (1.0 + poisson_ratio)
        / (3.0 * (1.0 - 2.0 * poisson_ratio))
        / 1_000.0
    )
    density = density_si / 1_000.0

    material = model.material.nd.pressure_depend_multi_yield(
        user_name=f"{soil_name}_material",
        nd=3,
        rho=density,
        refShearModul=shear_modulus,
        refBulkModul=bulk_modulus,
        frictionAng=properties["friction_angle"],
        peakShearStra=PEAK_SHEAR_STRAIN,
        refPress=REFERENCE_PRESSURE,
        pressDependCoe=PRESSURE_DEPENDENCE,
        PTAng=properties["phase_transformation_angle"],
        contrac=properties["contraction"],
        dilat1=properties["dilation_1"],
        dilat2=properties["dilation_2"],
        liquefac1=properties["liquefaction_1"],
        liquefac2=properties["liquefaction_2"],
        liquefac3=properties["liquefaction_3"],
        noYieldSurf=20,
        e=properties["void_ratio"],
    )
    materials[soil_name] = material
    elements[soil_name] = model.element.brick.std(
        ndof=3,
        material=material,
        b1=0.0,
        b2=0.0,
        b3=-GRAVITY * density,
    )
# --8<-- [end:nonlinear-materials]


# %% [markdown]
# ## Build and assemble the layered mesh

# %%
# --8<-- [start:mesh-and-assembly]
rayleigh_damping = model.damping.frequency_rayleigh(
    user_name="soil_damping",
    f1=2.76,
    f2=13.84,
    damping_factor=0.03,
)
soil_region = model.region.element(
    user_name="nonlinear_soil_column",
    damping=rayleigh_damping,
)

z_bottom = -COLUMN_DEPTH
layer_names = []
for layer_name, soil_name, thickness, element_size in LAYERS:
    model.meshpart.volume.uniform_rectangular_grid(
        user_name=layer_name,
        element=elements[soil_name],
        region=soil_region,
        x_min=0.0,
        x_max=COLUMN_WIDTH,
        y_min=0.0,
        y_max=COLUMN_WIDTH,
        z_min=z_bottom,
        z_max=z_bottom + thickness,
        nx=1,
        ny=1,
        nz=round(thickness / element_size),
    )
    layer_names.append(layer_name)
    z_bottom += thickness

if abs(z_bottom) > 1.0e-9:
    raise RuntimeError(f"Layer thicknesses terminate at z={z_bottom}, expected z=0")

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
# --8<-- [end:mesh-and-assembly]


# %% [markdown]
# ## Define excitation and nonlinear output

# %%
# --8<-- [start:loading-and-output]
motion_directory = motions_dir()
excitation_series = model.time_series.path(
    filePath=(motion_directory / "FrequencySweep.acc").resolve().as_posix(),
    fileTime=(motion_directory / "FrequencySweep.time").resolve().as_posix(),
    factor=GRAVITY,
)
uniform_excitation = model.pattern.uniform_excitation(
    dof=1,
    time_series=excitation_series,
)
response_recorder = model.recorder.vtkhdf(
    file_base_name="site_response.vtkhdf",
    resp_types=["accel", "disp", "vel", "stress3D6", "strain3D6"],
    delta_t=0.01,
)
# --8<-- [end:loading-and-output]


# %% [markdown]
# ## Stage gravity and activate plasticity
#
# Stage 0 establishes geostatic stress with elastic material response. Stage 1
# activates the yield surfaces, followed by a short re-equilibration analysis.

# %%
# --8<-- [start:staging-and-analysis]
constraint_handler = model.analysis.constraint.transformation()
numberer = model.analysis.numberer.rcm()
system = model.analysis.system.bandgeneral()

gravity_algorithm = model.analysis.algorithm.newton()
dynamic_algorithm = model.analysis.algorithm.modifiednewton(factor_once=True)

test = model.analysis.test.normunbalance(tol=1.0e-7, max_iter=30)
dynamic_test = model.analysis.test.normdispincr(tol=1.0e-5, max_iter=5)

gravity_integrator = model.analysis.integrator.newmark(gamma=0.6, beta=0.3025)
dynamic_integrator = model.analysis.integrator.newmark(gamma=0.5, beta=0.25)

elastic_gravity = model.analysis.transient(
    name="elastic_gravity",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=gravity_algorithm,
    test=test,
    integrator=gravity_integrator,
    dt=1.0,
    num_steps=30,
)

plastic_equilibration = model.analysis.transient(
    name="plastic_equilibration",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=dynamic_algorithm,
    test=test,
    integrator=gravity_integrator,
    dt=0.01,
    num_steps=100,
)
dynamic_analysis = model.analysis.transient(
    name="nonlinear_frequency_sweep",
    constraint_handler=constraint_handler,
    numberer=numberer,
    system=system,
    algorithm=dynamic_algorithm,
    test=dynamic_test,
    integrator=dynamic_integrator,
    dt=DYNAMIC_DT,
    final_time=DYNAMIC_FINAL_TIME,
    max_retries=1,
    num_sublevels=2,
    num_substeps=2,
)

model.process.add_step(
    model.actions.update_material_stage_to_elastic(),
    "Set nonlinear materials to elastic stage 0",
)
model.process.add_step(elastic_gravity, "Establish gravity stress")
model.process.add_step(
    model.actions.update_material_stage_to_plastic(),
    "Activate plastic material stage 1",
)
model.process.add_step(plastic_equilibration, "Re-equilibrate after staging")
model.process.add_step(uniform_excitation, "Apply the frequency sweep")
model.process.add_step(response_recorder, "Record fields and material response")
model.process.add_step(model.actions.set_time(0.0), "Reset pseudo-time")
model.process.add_step(dynamic_analysis, "Run nonlinear site response")
# --8<-- [end:staging-and-analysis]


# %% [markdown]
# ## Export and optionally execute

# %%
# --8<-- [start:export-and-run]
tcl_file = OUTPUT_DIR / "nonlinear_layered_soil_column.tcl"
model.export_to_tcl(
    filename=str(tcl_file.resolve()),
    progress_callback=lambda *_: None,
)

print("\nNonlinear layered soil column")
print(f"  Nodes:       {model.assembled_mesh.n_points}")
print(f"  Elements:    {model.assembled_mesh.n_cells}")
print(f"  Materials:   {len(materials)} nonlinear soil materials")
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
    model.assembler.plot(show_edges=True, scalars="MaterialTag")
