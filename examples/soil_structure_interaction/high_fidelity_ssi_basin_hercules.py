"""Run Hercules SSI realizations: no basin, then plastic basin, then results.

Units: m, kN, tonne, s. Running with --submit submits to Stampede3; importing
it is safe. Compact histories and all pile files are returned; building and
whole-domain raw files stay remotely. Use --site for an 80-case site campaign,
or --sourcefiles for one 64-case realization.
"""

from pathlib import Path
import json
import gzip
import re
import shutil

import h5py
import numpy as np
import pandas as pd
import pyvista as pv

import femora as fm
from femora import Model
from femora.results import BuildingResults
from femora.tools.buildings import SteelConcentricallyBracedFrame3D


SITES = tuple(range(8))
BUILDINGS = ("five_story", "ten_story")
FOUNDATIONS = ("mat", "pile")
BASIN_CASES = ("no_basin", "plastic")
SOIL_PARTITIONS = 32
ABSORBER_PARTITIONS = 54
RANKS_PER_CASE = SOIL_PARTITIONS + ABSORBER_PARTITIONS + 2
NODES = 28
CORES_PER_NODE = 112

DRM_ROOT = Path("/scratch/08189/amnp95/drm_inputs/h5drm")
CANONICAL_ROOT = Path("/scratch/08189/amnp95/drm_inputs/Canonical_Mw7.0")
# Change both explicitly for each realization; new input paths must not be guessed.
REALIZATION_ID = "reference"
DOWNLOAD_LIMIT_GB = 20.0
CAMPAIGN_REALIZATIONS = 10
RECORD_FULL_DOMAIN = False
INTERFACE_PENALTY = 1.0e6
FINAL_TIME = 35.0
DYNAMIC_DT = 0.01
EXPLICIT_DT = 5.0e-5
RECORDER_DT = 0.02
MUMPS_ICNTL14 = 200


def build_model(context, *, site, basin_case, building_type, foundation_type,
                realization_id=REALIZATION_ID, drm_root=None):
    """Build one independent case in its workflow task directory."""
    SITE = site
    BASIN_CASE = basin_case
    BUILDING_TYPE = building_type
    FOUNDATION_TYPE = foundation_type
    PLOT_MODEL = False
    LUMPED = BASIN_CASE == "plastic"

    # =================================================================
    # CHECK OPTIONS
    # =================================================================
    # Check the selected options.
    if SITE not in range(8):
        raise ValueError("SITE must be a Hercules box index from 0 through 7")

    if BASIN_CASE not in ("no_basin", "elastic", "plastic"):
        raise ValueError("BASIN_CASE must be no_basin, elastic, or plastic")

    if BUILDING_TYPE not in ("five_story", "ten_story"):
        raise ValueError("BUILDING_TYPE must be five_story or ten_story")

    if FOUNDATION_TYPE not in ("mat", "pile"):
        raise ValueError("FOUNDATION_TYPE must be mat or pile")


    # Keep each case in its own output folder.
    case_name = f"site_{SITE}_{BASIN_CASE}_{BUILDING_TYPE}_{FOUNDATION_TYPE}"
    output = Path(context.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    drm_file = Path(drm_root or DRM_ROOT) / f"Hercules_V2_DRM_Box_{SITE}.h5drm"

    # Coordinates are North-East-Down; prepared V2 motions are East-North-Down.
    # Match hercules.py: transform coordinates only; OpenSees handles motion Z.
    drm_transform = np.array([[0., 1., 0.], [1., 0., 0.], [0., 0., -1.]])
    with h5py.File(drm_file, "r") as source:
        metadata = source["DRM_Metadata"]
        start = float(np.asarray(metadata["tstart"]).item())
        end = float(np.asarray(metadata["tend"]).item())
        dt = float(np.asarray(metadata["dt"]).item())
        box_origin = np.asarray(metadata["drmbox_x0"], dtype=float).reshape(3)
        xyz = np.asarray(source["DRM_Data/xyz"], dtype=float)
        if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
            raise ValueError("Invalid Hercules DRM coordinates")
        local_xyz = (xyz - box_origin) @ drm_transform.T
        if not np.allclose(local_xyz.min(axis=0), [-64, -64, -48], atol=1e-6, rtol=0):
            raise ValueError("Hercules box minimum must map to (-64, -64, -48)")
        if not np.allclose(local_xyz.max(axis=0), [64, 64, 0], atol=1e-6, rtol=0):
            raise ValueError("Hercules box maximum must map to (64, 64, 0)")
        if not np.allclose(local_xyz / 4, np.round(local_xyz / 4), atol=1e-6, rtol=0):
            raise ValueError("Hercules DRM coordinates must match the 4 m grid")
        displacement = source["DRM_Data/displacement"]
        acceleration = source["DRM_Data/acceleration"]
        if displacement.ndim != 2 or acceleration.shape != displacement.shape:
            raise ValueError("Hercules displacement and acceleration must have matching 2D shapes")
        locations = np.asarray(source["DRM_Data/data_location"], dtype=int)
        if locations.shape != (len(xyz),) or np.any(locations < 0) or np.any(locations + 2 >= displacement.shape[0]):
            raise ValueError("Invalid Hercules DRM motion row offsets")
        if source["DRM_Data/internal"].shape != (len(xyz),):
            raise ValueError("Hercules boundary flags must match the DRM coordinates")
        if not np.isfinite([start, end, dt, FINAL_TIME]).all() or dt <= 0 or start != 0 or FINAL_TIME <= 0:
            raise ValueError("Invalid Hercules DRM time range or FINAL_TIME")
        last_sample = start + (displacement.shape[1] - 1) * dt
        if FINAL_TIME >= min(end, last_sample):
            raise ValueError(f"FINAL_TIME must be below {min(end, last_sample):g} s")


    # =================================================================
    # BUILD MODEL COMPONENTS
    # =================================================================
    # Create a fresh model.
    model = Model(
        model_name=case_name,
        model_path=str(output),
    )
    model.clear_model()
    model.set_results_folder((output / "results").as_posix())

    # Hercules background profiles from hercules.py; all layers use a 4 m grid.
    # name, density (tonne/m3), Vp, Vs (m/s), Rayleigh damping ratio, thickness (m).
    # These are travel-time-preserving layer approximations, not exact attenuation.
    if SITE == 4:
        layers = [
            ("layer_1", 1.8, 795.102, 425.000, 0.02, 8),
            ("layer_2", 1.8, 889.855, 475.648, 0.02, 4),
            ("layer_3", 1.8, 1010.247, 540.000, 0.02, 16),
            ("layer_4", 1.8, 1103.632, 589.916, 0.02, 4),
            ("layer_5", 1.8, 1216.039, 650.000, 0.02, 16),
        ]
    else:
        layers = [
            ("layer_1", 1.8, 598.665, 320.000, 0.02, 8),
            ("layer_2", 1.8, 649.979, 347.429, 0.02, 4),
            ("layer_3", 1.8, 710.915, 380.000, 0.02, 8),
            ("layer_4", 1.8, 757.686, 405.000, 0.02, 8),
            ("layer_5", 1.8, 771.462, 412.364, 0.02, 4),
            ("layer_6", 1.8, 785.748, 420.000, 0.02, 8),
            ("layer_7", 1.8, 823.165, 440.000, 0.02, 8),
        ]

    # BASIN_CASE optionally replaces host cells with the separate local basin.
    # Choose no_basin to retain the complete Hercules background profile.

    # Both basin materials start with the same elastic stiffness.
    basin_density = 1.8
    basin_shear_modulus = 40500.0
    basin_bulk_modulus = 108000.0

    if BASIN_CASE == "elastic":
        basin_material = model.material.nd.elastic_isotropic(
            user_name="basin",
            E=108000.0,
            nu=1. / 3,
            rho=basin_density,
        )

    elif BASIN_CASE == "plastic":
        basin_material = model.material.nd.pressure_independ_multi_yield(
            user_name="basin",
            nd=3,
            rho=basin_density,
            refShearModul=basin_shear_modulus,
            refBulkModul=basin_bulk_modulus,
            cohesi=8.0,
            peakShearStra=0.1,
        )

    # No basin material or element is needed for the no-basin case.
    if BASIN_CASE != "no_basin":
        basin_damping = model.damping.frequency_rayleigh(
            damping_factor=0.03,
            f1=3,
            f2=15,
        )
        basin_region = model.region.element(
            user_name="basin",
            damping=basin_damping,
        )
        basin_element = model.element.brick.std(
            ndof=3,
            material=basin_material,
            lumped=LUMPED,
            b3=-9.81 * basin_density,
        )



    soil_parts = []
    top = 0.0

    for name, density, vp, vs, damping_ratio, thickness in layers:
        bottom = top - thickness

        # Define this layer's material, damping, and brick element.
        shear_modulus = density * vs**2
        nu = (vp**2 - 2 * vs**2) / (2 * (vp**2 - vs**2))

        material = model.material.nd.elastic_isotropic(
            user_name=name,
            E=2 * shear_modulus * (1 + nu),
            nu=nu,
            rho=density,
        )
        damping = model.damping.frequency_rayleigh(
            damping_factor=damping_ratio,
            f1=3,
            f2=15,
        )
        region = model.region.element(user_name=name, damping=damping)
        element = model.element.brick.std(
            ndof=3,
            material=material,
            lumped=LUMPED,
            b3=-9.81 * density,
        )

        # Build the layer on the shared 4 m grid.
        x, y, z = np.meshgrid(
            np.linspace(-64, 64, 33),
            np.linspace(-64, 64, 33),
            np.linspace(bottom, top, int(thickness / 4) + 1),
            indexing="ij",
        )
        grid = pv.StructuredGrid(x, y, z).cast_to_unstructured_grid()

        # Select whole bricks inside the basin.
        in_basin = np.zeros(grid.n_cells, dtype=bool)
        if BASIN_CASE != "no_basin":
            centers = grid.cell_centers().points
            in_basin = np.linalg.norm(centers - [0, 0, 70], axis=1) <= 85

        # Host soil outside the basin.
        if (~in_basin).any():
            host_name = f"{name}_host"
            model.meshpart.general.external_mesh(
                user_name=host_name,
                element=element,
                region=region,
                mesh=grid.extract_cells(~in_basin),
            )
            soil_parts.append(host_name)

        # Basin soil replaces the selected host bricks.
        if in_basin.any():
            basin_name = f"{name}_basin"
            model.meshpart.general.external_mesh(
                user_name=basin_name,
                element=basin_element,
                region=basin_region,
                mesh=grid.extract_cells(in_basin),
            )
            soil_parts.append(basin_name)

        top = bottom


    # Excavate the foundation footprint, removing whole 4 m soil bricks.
    for name in soil_parts:
        part = model.meshpart.get(name)
        centers = part.mesh.cell_centers().points

        inside_foundation = (
            (np.abs(centers[:, 0]) < 16)
            & (np.abs(centers[:, 1]) < 16)
            & (centers[:, 2] > -4)
        )

        part.remove_cells(inside_foundation)


    # Concrete block: excavated soil is not retained inside it.
    concrete = model.material.nd.elastic_isotropic(
        user_name="concrete", E=20.68e6, nu=.3, rho=2.403,
    )
    block_element = model.element.brick.std(
        ndof=3, material=concrete, lumped=LUMPED, b3=-9.81 * 2.403,
    )
    model.meshpart.volume.geometric_rectangular_grid(
        user_name="foundation", element=block_element,
        x_min=-16, x_max=16, y_min=-16, y_max=16, z_min=-4, z_max=-2,
        nx=22, ny=22, nz=2,
    )


    # Building: both heights use the saved numerical-model brace properties.
    # Steel properties: kN/mÂ² and tonne/mÂ³.
    steel_E = 199947888.8957778
    steel_G = steel_E / 2.6
    steel_density = 7.849040650691395

    # Floor masses in tonnes, ordered from bottom to top.
    if BUILDING_TYPE == "five_story":
        stories = 5
        floor_masses = [362.722569, 362.722569] + [356.523082] * 3
        brace_scale = 1.5
        building_frequency = 2.0634  # Fixed-base first-mode frequency (Hz).
    else:
        stories = 10
        floor_masses = (
            [362.722569, 362.722569]
            + [356.523082] * 7
            + [384.053010]
        )
        brace_scale = 0.5
        building_frequency = 0.6526  # Fixed-base first-mode frequency (Hz).

    # Custom brace geometry reproduces the original numerical models.
    brace_properties = {
        "A": 37.69 * 0.0254**2,
        "Iy": 0.349 * 0.0254**4,
        "Iz": 3.10 * 0.0254**4,
    }

    steel = model.material.uniaxial.elastic(
        user_name="building_steel",
        E=steel_E,
    )

    building = SteelConcentricallyBracedFrame3D(
        name_prefix="building",
        num_stories=stories,
        x_bays=[9.144] * 3,
        y_bays=[9.144] * 3,
        story_heights=[4.0] + [3.5] * (stories - 1),
        floor_masses=floor_masses,
        column_sections="W14X90",
        beam_sections="W18X35",
        brace_properties=brace_properties,
        brace_area_scale=brace_scale,
        member_formulation="displacement_based",
        origin=(-13.716, -13.716, -2.0),
    )

    building_part = building.build(
        model,
        material=steel,
        G=steel_G,
        material_density=steel_density,
    )

    # Structural damping only; soil and absorber damping remain separate.
    building_damping = model.damping.uniform(
        dampingRatio=0.05,
        freql=building_frequency,
        freq2=10 * building_frequency,
    )
    building_part.set_damping(building_damping)



    # Optional pile geometry. Both cases use the same concrete block above.
    pile_parts = []
    if FOUNDATION_TYPE == "pile":
        # The cap has no direct soil tie: forces reach the soil through nine piles.
        diameter = .8
        area = np.pi * diameter**2 / 4
        inertia = np.pi * diameter**4 / 64
        section = model.section.beam.elastic(
            user_name="pile_section", E=steel_E, G=steel_E / 2.6,
            A=area, Iy=inertia, Iz=inertia, J=2 * inertia,
        )
        transformation = model.transformation.transformation3d("Linear", 1, 0, 0)
        pile_element = model.element.beam.disp(
            ndof=6, section=section, transformation=transformation,
            numIntgrPts=5, massDens=0.0,
        )
        for i, px in enumerate((-14, 0, 14)):
            for j, py in enumerate((-14, 0, 14)):
                name = f"pile_{i}_{j}"
                model.meshpart.line.single_line(
                    user_name=name, element=pile_element,
                    x0=px, y0=py, z0=-10, x1=px, y1=py, z1=-3, number_of_lines=5,
                    # Explicit dynamics uses nodal translational and rotary masses.
                    density=steel_density,
                )
                pile_parts.append(name)


    # Interfaces: attach the building to the block, then connect the foundation to soil.
    building_interface = model.interface.node_interface(
        name="building_foundation", constrained_node="building", retained_nodes=["foundation"],
        rot=True, K=INTERFACE_PENALTY, KP=INTERFACE_PENALTY, offset=0,
    )
    if FOUNDATION_TYPE == "mat":
        model.interface.node_interface(
            name="mat_soil_interface", constrained_node="foundation", retained_nodes=soil_parts,
            rot=False, K=INTERFACE_PENALTY,
        )
    else:
        for name in pile_parts:
            model.interface.node_interface(
                name=f"{name}_cap", constrained_node=name, retained_nodes=["foundation"],
                rot=True, K=INTERFACE_PENALTY, KP=INTERFACE_PENALTY, offset=0,
            )
            model.interface.beam_solid_interface(
                name=f"{name}_soil", beam_part=name, solid_parts=soil_parts,
                radius=diameter / 2, n_long=4, n_peri=8,
                penalty_param=INTERFACE_PENALTY, g_penalty=True,
            )

    # Absorbing boundary setup is last; assembly generates the boundary and interfaces.
    model.interface.boundary.absorber(
        num_layers=8, num_partitions=ABSORBER_PARTITIONS, partition_algo="metis",
        geometry="Rectangular", boundary_type="Rayleigh",
        rayleigh_damping=.95, match_damping=False,
    )

    # Partition the components independently. Keep the cap and all piles together.
    model.assembler.create_section(
        meshparts=soil_parts, num_partitions=SOIL_PARTITIONS,
        merge_points=True, partition_algorithm="kd-tree",
    )
    model.assembler.create_section(
        meshparts=["building"], num_partitions=1,
        merge_points=True, partition_algorithm="kd-tree",
    )
    model.assembler.create_section(
        meshparts=["foundation"] + pile_parts, num_partitions=1,
        merge_points=True, partition_algorithm="kd-tree",
    )


    # Keep component nodes distinct; the interfaces provide their connections.
    model.assembler.assemble(merge_points=False, progress_callback=lambda *_: None)


    building.create_rigid_diaphragms(model, verbose=False)
    # Do not fix the building bases: they are supported by the concrete block.
    model.constraint.sp.fix_macro_x_min(dofs=[1, 1, 1], tol=.01)
    model.constraint.sp.fix_macro_x_max(dofs=[1, 1, 1], tol=.01)
    model.constraint.sp.fix_macro_y_min(dofs=[1, 1, 1], tol=.01)
    model.constraint.sp.fix_macro_y_max(dofs=[1, 1, 1], tol=.01)
    model.constraint.sp.fix_macro_z_min(dofs=[1, 1, 1], tol=.01)

    mesh = model.assembled_mesh


    # Apply floor gravity only; member and pile masses remain inertia properties.
    # Soil and concrete retain their existing brick body forces.
    floor_gravity = building.create_gravity_pattern(model, g=9.81)


    # Gravity analyses. Constant patterns keep full weight applied in both phases.
    # The step counter is a load-equilibrium index, not physical earthquake time.
    gravity_elastic = model.analysis.static(
        name="gravity_elastic",
        constraint_handler=model.analysis.constraint.transformation(),
        numberer=model.analysis.numberer.parallelrcm(),
        system=model.analysis.system.mumps(icntl14=MUMPS_ICNTL14, icntl7=7),
        test=model.analysis.test.energyincr(tol=1e-8, max_iter=30, print_flag=0),
        algorithm=model.analysis.algorithm.modifiednewton(factor_once=True),
        integrator=model.analysis.integrator.loadcontrol(incr=1.0),
        num_steps=10, max_retries=0,
    )
    gravity_reequilibrate = model.analysis.static(
        name="gravity_reequilibrate",
        constraint_handler=model.analysis.constraint.transformation(),
        numberer=model.analysis.numberer.parallelrcm(),
        system=model.analysis.system.mumps(icntl14=MUMPS_ICNTL14, icntl7=7),
        test=model.analysis.test.energyincr(tol=1e-4, max_iter=200, print_flag=0),
        algorithm=model.analysis.algorithm.modifiednewton(),
        integrator=model.analysis.integrator.loadcontrol(incr=1.0),
        num_steps=10, max_retries=0,
    )

    # Apply the Hercules V2 wave field using the convention in hercules.py.
    drm = model.pattern.h5drm(
        filepath=drm_file.as_posix(),
        factor=1.0,
        crd_scale=1.0,
        distance_tolerance=0.01,
        do_coordinate_transformation=1,
        transform_matrix=drm_transform.ravel().tolist(),
        origin=[0, 0, 0],
    )

    # DRM acceleration is absolute; do not add ground motion again afterward.
    response_recorder = model.recorder.vtkhdf(
        file_base_name="earthquake_response.vtkhdf",
        resp_types=["disp", "vel", "accel", "force3D", "localForce3D", "stress3D6", "strain3D6"],
        delta_t=RECORDER_DT,
    ) if RECORD_FULL_DOMAIN else None

    # Select soil by mesh-part membership, never by assumed MPI ownership.
    centers = mesh.cell_centers().points
    part_tags = [model.meshpart.get(name).tag for name in soil_parts]
    soil = np.isin(mesh.cell_data["MeshPartTag_celldata"], part_tags)
    borehole_cells = []
    for index in np.flatnonzero(soil & (mesh.celltypes == 12)):
        points = mesh.get_cell(int(index)).points
        lo, hi = points.min(axis=0), points.max(axis=0)
        if (lo[0] <= 0 <= hi[0] and lo[1] <= 0 <= hi[1]
                and -48 < centers[index, 2] < -4):
            borehole_cells.append(int(index))
    if len(borehole_cells) != 44:
        raise ValueError(f"Expected 44 center-adjacent soil bricks, found {len(borehole_cells)}")
    borehole_group = model.group.element.from_cells("center_borehole", borehole_cells)
    borehole_recorder = model.recorder.vtkhdf(
        file_base_name="borehole_response.vtkhdf", element_group=borehole_group,
        cores=sorted(map(int, np.unique(mesh.cell_data["Core"][borehole_cells]))),
        resp_types=["disp", "vel", "accel", "stress3D6", "strain3D6"], delta_t=RECORDER_DT,
    )
    cap_tag = model.meshpart.get("foundation").tag
    cap_ids = np.flatnonzero(mesh.cell_data["MeshPartTag_celldata"] == cap_tag)
    cap_centers = centers[cap_ids]
    corner_cells = cap_ids[
        np.isclose(np.abs(cap_centers[:, 0]), np.abs(cap_centers[:, 0]).max())
        & np.isclose(np.abs(cap_centers[:, 1]), np.abs(cap_centers[:, 1]).max())]
    foundation_group = model.group.element.from_cells("foundation_corners", corner_cells)
    foundation_recorder = model.recorder.vtkhdf(
        file_base_name="foundation_response.vtkhdf", element_group=foundation_group,
        cores=sorted(map(int, np.unique(mesh.cell_data["Core"][corner_cells]))),
        resp_types=["disp", "vel", "accel"], delta_t=RECORDER_DT,
    )

    # Dedicated structural files are smaller and easier to postprocess independently.
    building_recorder = building.get_recorders(
        model,
        file_name="building_response.vtkhdf",
        whole_model=False,
        delta_t=RECORDER_DT,
        node_responses=["disp", "vel", "accel"],
        element_responses=["force3D", "localForce3D"],
        acceleration_basis="absolute",
        abscissa="time_s",
    )

    if pile_parts:
        pile_recorder = model.recorder.pile_vtkhdf(
            meshparts=pile_parts,
            file_base_name="pile_response.vtkhdf",
            resp_types=["disp", "vel", "accel", "force3D", "localForce3D"],
            delta_t=RECORDER_DT,
        )

    if LUMPED:
        # Explicit updates have no Newton iterations or automatic stability detection.
        dynamic_system = model.analysis.system.mpidiagonal()
        dynamic_algorithm = model.analysis.algorithm.linear()
        dynamic_integrator = model.analysis.integrator.explicitdifference()
        dynamic_dt = EXPLICIT_DT
    else:
        dynamic_system = model.analysis.system.mumps(icntl14=MUMPS_ICNTL14, icntl7=7)
        dynamic_algorithm = model.analysis.algorithm.modifiednewton(factor_once=True)
        dynamic_integrator = model.analysis.integrator.newmark(gamma=0.5, beta=0.25)
        dynamic_dt = DYNAMIC_DT

    dynamic = model.analysis.transient(
        name="earthquake_response",
        constraint_handler=model.analysis.constraint.transformation(),
        numberer=model.analysis.numberer.parallelrcm(),
        system=dynamic_system,
        test=model.analysis.test.energyincr(tol=1e-4, max_iter=8, print_flag=0),
        algorithm=dynamic_algorithm,
        integrator=dynamic_integrator,
        dt=dynamic_dt,
        final_time=FINAL_TIME,
        initialize=True,
        max_retries=0 if LUMPED else 1,
        num_sublevels=None if LUMPED else 3,
        num_substeps=None if LUMPED else 2,
    )

    model.process.add_step(floor_gravity, "Apply floor weights")
    model.process.add_step(model.actions.update_material_stage_to_elastic(), "Elastic initialization")
    model.process.add_step(gravity_elastic, "Equilibrate elastic self-weight")
    if BASIN_CASE == "plastic":
        model.process.add_step(model.actions.update_material_stage_to_plastic(), "Activate basin plasticity")
    model.process.add_step(gravity_reequilibrate, "Re-equilibrate the gravity state")
    model.process.add_step(model.actions.load_const(), "Hold gravity loads")
    model.process.add_step(model.actions.set_time(0.0), "Reset dynamic clock")
    model.process.add_step(drm, "Apply regional wave field")
    if response_recorder is not None:
        model.process.add_step(response_recorder, "Record earthquake response")
    model.process.add_step(borehole_recorder, "Record center soil column")
    model.process.add_step(foundation_recorder, "Record foundation corner motions")
    model.process.add_step(building_recorder, "Record building response")
    if pile_parts:
        model.process.add_step(pile_recorder, "Record pile response")
    model.process.add_step(dynamic, "Run coupled earthquake analysis")
    model.process.add_step(model.actions.remove_recorders(), "Close recorders")

    if len(np.unique(mesh.cell_data["Core"])) != RANKS_PER_CASE or int(mesh.cell_data["Core"].max()) + 1 != RANKS_PER_CASE:
        raise RuntimeError(f"Assembled partition layout does not match {RANKS_PER_CASE} MPI ranks")

    # Export explicitly using a compatible OpenSeesMP build.
    building.export_metadata(
        model, output / "building.structure.h5",
        units=dict(length="m", force="kN", moment="kN*m", acceleration="m/s^2"),
        acceleration_basis="absolute",
        abscissa="time_s",
    )
    model.export_to_tcl(str(output / "model.tcl"), progress_callback=lambda *_: None)
    mesh.save(output / "assembled_model.vtu")
    source_stat = drm_file.stat()
    (output / "case.json").write_text(json.dumps(dict(
        realization_id=realization_id, site=SITE, basin_case=BASIN_CASE,
        building_type=BUILDING_TYPE, foundation_type=FOUNDATION_TYPE,
        drm_file=str(drm_file), drm_bytes=source_stat.st_size,
        drm_mtime_ns=source_stat.st_mtime_ns, final_time=FINAL_TIME,
        recorder_dt=RECORDER_DT, dynamic_dt=dynamic_dt,
        mumps_icntl14=MUMPS_ICNTL14,
        ranks_per_case=RANKS_PER_CASE,
        soil_partitions=SOIL_PARTITIONS,
        absorber_partitions=ABSORBER_PARTITIONS,
        absorber_partitioner="metis",
        units=dict(length="m", force="kN", time="s"),
        software_version=getattr(fm, "__version__", "unknown"),
        borehole_exclusions="Node at z=-48 and cells touching z=-48 flagged; retained raw",
    ), indent=2), encoding="utf-8")
    print(f"Assembled: {case_name}; nodes={mesh.n_points}, cells={mesh.n_cells}")
    print(f"Partition layout: {SOIL_PARTITIONS} soil + {ABSORBER_PARTITIONS} absorber + 1 building + 1 foundation/piles = {RANKS_PER_CASE} MPI ranks.")
    print(f"Preview mesh: {output / 'assembled_model.vtu'}")
    print(f"DRM input (read by OpenSees): {drm_file}")
    print(f"Analysis Tcl: {output / 'model.tcl'}")
    print(f"Dynamic scheme: {'explicit (trial stability step)' if LUMPED else 'implicit Newmark'}; dt={dynamic_dt:g} s")
    print("Gravity and earthquake analyses exported, not run. No gravity recorder is created.")
    if PLOT_MODEL:
        # Remove half the soil visually to expose the block and any piles.
        soil_tags = [model.meshpart.get(name).tag for name in soil_parts]
        cell_parts = mesh.cell_data["MeshPartTag_celldata"]
        soil_cells = np.isin(cell_parts, soil_tags)
        view = pv.Plotter()
        view.add_mesh(mesh.extract_cells(soil_cells).clip(normal="y", origin=(0, 0, 0)),
                      color="tan", opacity=.25, show_edges=True)
        view.add_mesh(mesh.extract_cells(cell_parts == model.meshpart.get("foundation").tag),
                      color="slategray", opacity=.8, show_edges=True)
        view.add_mesh(mesh.extract_cells(cell_parts == model.meshpart.get("building").tag),
                      color="firebrick", line_width=3)
        if pile_parts:
            pile_tags = [model.meshpart.get(name).tag for name in pile_parts]
            view.add_mesh(mesh.extract_cells(np.isin(cell_parts, pile_tags)), color="steelblue", line_width=5)
        view.add_axes()
        view.show_grid()
        view.show()
    return output


def compact_recorder(files, output, *, borehole=False):
    """Preserve selected raw histories; validate time coverage and partition copies.

    No soil tensor conversion or DRM correction is made. Foundation rotations
    below are small-angle least-squares fits, not directly recorded DOFs.
    """
    entities = {"nodes": {}, "cells": {}}
    times = None
    for path in files:
        with h5py.File(path, "r") as source:
            r = source["VTKHDF"]
            t = r["Steps/Values"][:].reshape(-1)
            if (not np.isfinite(t).all() or len(t) < 2 or not np.all(np.diff(t) > 0)
                    or not np.isclose(t[0], 0) or not np.isclose(t[-1], FINAL_TIME)
                    or np.max(np.diff(t)) > RECORDER_DT * 1.01):
                raise ValueError(f"Incomplete or invalid times: {path}")
            if times is not None and (t.shape != times.shape or not np.allclose(t, times, rtol=0, atol=1e-9)):
                raise ValueError("Recorder partition time arrays disagree")
            times = t
            points, types = r["Points"][:], r["Types"][:]
            offsets, conn = r["Offsets"][:], r["Connectivity"][:]
            for group, location, tagname, fields in [
                ("nodes", "PointData", "nodeTags", ("displacement", "velocity", "acceleration")),
                ("cells", "CellData", "eleTags", ("stress3D6", "strain3D6")),
            ]:
                if group == "cells" and not borehole:
                    continue
                count = len(points) if group == "nodes" else len(types)
                tags = r[f"{location}/{tagname}"][:].reshape(-1)
                if len(tags) != count:
                    raise ValueError("Expected static topology/tag arrays")
                for i in range(count):
                    if group == "nodes":
                        xyz, vertices = points[i], None
                        if borehole and not (np.allclose(xyz[:2], [0, 0], rtol=0, atol=1e-7)
                                             and -48.000001 <= xyz[2] <= -3.999999):
                            continue
                    else:
                        if types[i] != 12:
                            raise ValueError("Borehole selection contains a non-hex cell")
                        vertices = points[conn[offsets[i]:offsets[i + 1]]]
                        xyz = vertices.mean(axis=0)
                    histories = {}
                    for name in fields:
                        ds = r[f"{location}/{name}"]
                        starts = r[f"Steps/{location}Offsets/{name}"][:].reshape(-1)
                        if len(starts) != len(t) or np.any(starts < 0) or np.any(starts + count > len(ds)):
                            raise ValueError(f"Invalid response offsets: {name}")
                        rows = starts.astype(np.int64) + i
                        if np.all(np.diff(rows) == count):
                            values = ds[int(rows[0]):int(rows[-1])+1:count]
                        elif np.all(np.diff(rows) > 0):
                            values = ds[rows]
                        else:
                            raise ValueError("Non-increasing response offsets")
                        expected = 3 if group == "nodes" else 6
                        if values.shape != (len(t), expected) or not np.isfinite(values).all():
                            raise ValueError(f"Invalid history {path}/{name}/{i}")
                        histories[name] = values
                    tag = int(tags[i])
                    item = dict(xyz=xyz, histories=histories, vertices=vertices,
                                sources=[dict(file=path.name, index=i)])
                    if tag in entities[group]:
                        old = entities[group][tag]
                        if not np.allclose(old["xyz"], xyz, rtol=0, atol=1e-7) or any(
                            not np.allclose(old["histories"][name], values, rtol=1e-7, atol=1e-9)
                            for name, values in histories.items()):
                            raise ValueError(f"Conflicting partition copies: {tag}")
                        old["sources"].extend(item["sources"])
                    else:
                        entities[group][tag] = item
    if times is None or not entities["nodes"]:
        raise ValueError("No recorder data found")
    if borehole and (len(entities["nodes"]) != 12 or len(entities["cells"]) != 44):
        raise ValueError("Incomplete center soil column")
    with h5py.File(output, "x") as dest:
        dest["time_s"] = times
        dest.attrs["notes"] = ("Raw recorded values, SI-derived m-kN-s units; initial sample retained. "
                               "Stress/strain components c0-c5 and sampling convention unverified. "
                               "No DRM correction or depth-reference subtraction applied.")
        for group, items in entities.items():
            if not items:
                continue
            ordered = sorted(items)
            xyz = np.array([items[k]["xyz"] for k in ordered])
            g = dest.create_group(group)
            g["tags"], g["coordinates"] = ordered, xyz
            g.attrs["sources"] = json.dumps([items[k]["sources"] for k in ordered])
            if borehole:
                g["exclude_from_soil_comparison"] = (np.isclose(xyz[:, 2], -48)
                    if group == "nodes" else [np.isclose(items[k]["vertices"][:, 2].min(), -48) for k in ordered])
            for name in items[ordered[0]]["histories"]:
                a = np.stack([items[k]["histories"][name] for k in ordered], axis=1)
                ds = g.create_dataset(name, data=a, compression="gzip", shuffle=True)
                ds.attrs["axes"] = "time,entity,component"
                g[f"initial/{name}"] = a[0]
            if not borehole and group == "nodes":
                origin = xyz.mean(axis=0)
                relative = xyz - origin
                design = []
                for x, y, z in relative:
                    design.extend([[1, 0, 0, 0, z, -y], [0, 1, 0, -z, 0, x], [0, 0, 1, y, -x, 0]])
                design = np.array(design)
                if np.linalg.matrix_rank(design) != 6:
                    raise ValueError("Foundation nodes cannot resolve six rigid-motion components")
                u = g["displacement"][:].reshape(len(times), -1)
                fit = u @ np.linalg.pinv(design).T
                dest["rigid_fit/origin"] = origin
                dest["rigid_fit/translation_m"] = fit[:, :3]
                dest["rigid_fit/rotation_rad"] = fit[:, 3:]
                dest["rigid_fit/residual_rms_m"] = np.sqrt(np.mean((u - fit @ design.T)**2, axis=1))
                dest["rigid_fit"].attrs["definition"] = "Small-angle least-squares u=t+theta cross (X-origin); not exact finite rotation"
    return dict(samples=len(times), nodes=len(entities["nodes"]), cells=len(entities["cells"]),
                all_finite=True, bytes=Path(output).stat().st_size)


def postprocess_building(context, *, case_name, build_stage, site, basin_case,
                         building_type, foundation_type, realization_id=REALIZATION_ID,
                         drm_root=None):
    """Extract building histories and summaries after all 64 solves finish."""
    folder = Path(context.result(build_stage, case_name))
    files = sorted((folder / "results").glob("building_response*.vtkhdf"))
    if not files:
        raise FileNotFoundError(f"No building recorder files for {case_name}")
    summaries = []
    with BuildingResults.open(files, metadata=folder / "building.structure.h5") as results:
        for direction in ("x", "y"):
            results.export_csv(
                context.output_dir,
                responses=["floor_displacement", "floor_acceleration",
                           "interstory_drift", "base_shear"],
                direction=direction,
            )
            results.floor_displacement(direction, relative_to_base=True).to_csv(
                context.output_dir / f"floor_displacement_relative_to_base_{direction}.csv")
            results.floor_displacement(direction, include_base=True).iloc[:, :1].to_csv(
                context.output_dir / f"structural_base_displacement_{direction}.csv")
            results.floor_acceleration(direction, include_base=True).iloc[:, :1].to_csv(
                context.output_dir / f"structural_base_acceleration_{direction}.csv")
            summary = results.summary(responses=["floor_displacement", "floor_acceleration",
                                                "interstory_drift", "base_shear"], direction=direction).copy()
            for key, value in dict(case=case_name, site=site, basin_case=basin_case,
                                   building_type=building_type,
                                   foundation_type=foundation_type,
                                   direction=direction, realization_id=realization_id).items():
                summary[key] = value
            summaries.append(summary)
    output = context.output_dir / "summary.csv"
    pd.concat(summaries, ignore_index=True).to_csv(output, index=False)
    validation = {}
    for name, is_borehole in (("borehole", True), ("foundation", False)):
        validation[name] = compact_recorder(
            sorted((folder / "results").glob(f"{name}_response*.vtkhdf")),
            context.output_dir / f"{name}_histories.h5", borehole=is_borehole)
    if foundation_type == "pile":
        piles = list((folder / "results").glob("pile_response*.vtkhdf"))
        if len(piles) != 1:
            raise ValueError("Expected one dedicated file containing all nine piles")
        with h5py.File(piles[0], "r") as source:
            r = source["VTKHDF"]
            t = r["Steps/Values"][:]
            if not np.isfinite(t).all() or not np.all(np.diff(t) > 0) or not np.isclose(t[-1], FINAL_TIME):
                raise ValueError("Invalid pile time coverage")
            for group, names in (("PointData", ("displacement", "velocity", "acceleration")),
                                 ("CellData", ("force3D", "localForce3D"))):
                for name in names:
                    ds = r[f"{group}/{name}"]
                    for start in range(0, len(ds), 65536):
                        if not np.isfinite(ds[start:start+65536]).all():
                            raise ValueError(f"Nonfinite pile response: {name}")
        shutil.copy2(piles[0], context.output_dir / "piles.vtkhdf")
    for name in ("case.json", "building.structure.h5", "assembled_model.vtu"):
        shutil.copy2(folder / name, context.output_dir / name)
    with (folder / "model.tcl").open("rb") as source, gzip.open(context.output_dir / "model.tcl.gz", "wb") as target:
        shutil.copyfileobj(source, target)
    (context.output_dir / "validation.json").write_text(json.dumps(validation, indent=2))
    return output


def combine_summaries(context):
    """Combine all case summaries, retaining case and direction identifiers."""
    tables = [pd.read_csv(path) for path in context.results["postprocess"].values()]
    output = context.output_dir / "all_building_summaries.csv"
    pd.concat(tables, ignore_index=True).to_csv(output, index=False)
    directories = {Path(path).parent for path in context.results["postprocess"].values()}
    sizes = {str(folder.name): sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
             for folder in directories}
    size = sum(sizes.values())
    (context.output_dir / "storage_budget.json").write_text(json.dumps(dict(
        case_bytes=sizes, measured_cases=len(sizes), total_bytes=size,
        projected_640_case_bytes=size / len(sizes) * 640,
        projected_campaign_bytes=size / len(sizes) * 64 * CAMPAIGN_REALIZATIONS,
        limit_decimal_gb=DOWNLOAD_LIMIT_GB,
        projected_within_limit=size / len(sizes) * 64 * CAMPAIGN_REALIZATIONS <= DOWNLOAD_LIMIT_GB * 1e9,
        note="Uncompressed file-byte estimate, not a guarantee for other realizations; includes complete pile files",
    ), indent=2))
    return output


def build_workflow(inputs=None):
    """Build an ordered campaign; each basin solve phase finishes before the next."""
    inputs = inputs or {}
    if "realizations" in inputs:
        configurations = inputs["realizations"]
        if not isinstance(configurations, list) or not configurations:
            raise ValueError("realizations must be a nonempty list of input configurations")
        if any("realizations" in options for options in configurations):
            raise ValueError("Nested realization lists are not supported")
        children = [build_workflow(options) for options in configurations]
        stage_names = [s.name for s in children[0].stages]
        if any([s.name for s in child.stages] != stage_names for child in children):
            raise ValueError("All realization configurations must use the same basin phases")
        capacity_nodes = inputs.get("capacity_nodes", NODES)
        if type(capacity_nodes) is not int or capacity_nodes < 1:
            raise ValueError("capacity_nodes must be a positive integer")
        workflow = fm.Workflow(inputs.get("workflow_name", "hercules-multi-realization-pilot"))
        for index, name in enumerate(stage_names):
            if name == "summary":
                workflow.add(name, tasks=[fm.tasks.Python("combined", combine_summaries)])
                continue
            tasks = [t for child in children for t in child.stages[index].tasks]
            if len({t.name for t in tasks}) != len(tasks):
                raise ValueError("Realization configurations produce duplicate case names")
            if name.startswith("solve_"):
                capacity = capacity_nodes * CORES_PER_NODE
                waves, wave, used = [], [], 0
                for task in tasks:
                    if task.ranks > capacity:
                        raise ValueError("One solve exceeds the configured node capacity")
                    if used + task.ranks > capacity:
                        waves.append(wave)
                        wave, used = [], 0
                    wave.append(task)
                    used += task.ranks
                if wave:
                    waves.append(wave)
                for number, wave in enumerate(waves, 1):
                    wave_name = name if number == 1 else f"{name}_wave_{number}"
                    workflow.add(wave_name, parallel=True, tasks=wave)
            else:
                workflow.add(name, parallel=children[0].stages[index].parallel, tasks=tasks)
        workflow.outputs("postprocess/**/*", "summary/**/*")
        return workflow
    required = len(SITES) * len(BUILDINGS) * len(FOUNDATIONS) * RANKS_PER_CASE
    if required > NODES * CORES_PER_NODE:
        raise ValueError(f"Each solve phase needs {required} allocated rank slots")
    basin_cases = tuple(inputs.get("basin_cases", BASIN_CASES))
    if not basin_cases or len(set(basin_cases)) != len(basin_cases) or any(b not in BASIN_CASES for b in basin_cases):
        raise ValueError("basin_cases must select no_basin and/or plastic without duplicates")
    sites = tuple(inputs.get("sites", SITES))
    if not sites or len(set(sites)) != len(sites) or any(type(s) is not int or s not in SITES for s in sites):
        raise ValueError("sites must be unique integers from 0 through 7")
    realization = inputs.get("realization_id", REALIZATION_ID)
    if not isinstance(realization, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", realization):
        raise ValueError("realization_id must contain only letters, digits, underscores or hyphens")
    if realization != "reference" and not inputs.get("drm_root"):
        raise ValueError("Supply an explicit drm_root for a new realization")
    drm_root = str(inputs.get("drm_root", DRM_ROOT))
    workflow = fm.Workflow(f"hercules-{realization}-64-case-ssi")
    postprocessing = []
    for basin_case in basin_cases:
        build_stage = f"build_{basin_case}"
        builds, solves = [], []
        for site in sites:
            for building_type in BUILDINGS:
                for foundation_type in FOUNDATIONS:
                    case_name = f"{realization}_site_{site}_{basin_case}_{building_type}_{foundation_type}"
                    options = dict(site=site, basin_case=basin_case,
                                   building_type=building_type, foundation_type=foundation_type,
                                   realization_id=realization, drm_root=drm_root)
                    builds.append(fm.tasks.Python(case_name, build_model, kwargs=options))
                    solves.append(fm.tasks.OpenSees(
                        case_name, f"{build_stage}/{case_name}/model.tcl", ranks=RANKS_PER_CASE,
                    ))
                    postprocessing.append(fm.tasks.Python(
                        case_name, postprocess_building,
                        kwargs=dict(options, case_name=case_name, build_stage=build_stage),
                    ))
        # Python builds run sequentially on the coordinator.
        workflow.add(build_stage, tasks=builds)
        # Concurrent solves use non-overlapping ibrun rank offsets.
        workflow.add(f"solve_{basin_case}", parallel=True, tasks=solves)
    workflow.add("postprocess", tasks=postprocessing)
    workflow.add("summary", tasks=[fm.tasks.Python("combined", combine_summaries)])
    workflow.outputs(
        "postprocess/**/*", "summary/**/*",
    )
    return workflow


def realization_inputs(index, *, pilot=False):
    """Map the supplied Canonical_Mw7.0 sourcefiles layout without input staging."""
    if type(index) is not int or index not in range(1, 11):
        raise ValueError("sourcefiles index must be 1 through 10")
    options = dict(realization_id=f"sourcefiles{index}",
                   drm_root=(CANONICAL_ROOT / f"sourcefiles{index}" / "h5drm").as_posix())
    if pilot:
        options["sites"] = [0]
    return options


def site_campaign_inputs(site):
    """Select all ten known realizations at one site: 40 reference + 40 plastic."""
    if type(site) is not int or site not in SITES:
        raise ValueError("site must be an integer from 0 through 7")
    configurations = []
    for index in range(1, 11):
        options = realization_inputs(index)
        options["sites"] = [site]
        options["basin_cases"] = ["no_basin", "plastic"]
        configurations.append(options)
    return dict(realizations=configurations, capacity_nodes=32,
                workflow_name=f"hercules-site-{site}-10-realizations")


def requested_nodes(workflow):
    """Minimum CPU-slot count for the largest simultaneous solve phase."""
    ranks = max(sum(t.ranks for t in stage.tasks) for stage in workflow.stages
                if stage.name.startswith("solve_"))
    return (ranks + CORES_PER_NODE - 1) // CORES_PER_NODE


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realization", default=None)
    parser.add_argument("--drm-root", default=None)
    parser.add_argument("--sourcefiles", type=int, choices=range(1, 11),
                        help="Use Canonical_Mw7.0/sourcefilesN/h5drm")
    parser.add_argument("--site", type=int, choices=range(8),
                        help="Production: all 10 realizations at this site; 80 cases, up to 32 nodes")
    parser.add_argument("--pilot", action="store_true", help="8 cases at site 0, using both buildings/foundations/basin conditions")
    parser.add_argument("--no-basin-only", action="store_true", help="With --pilot, run only the four no-basin cases")
    parser.add_argument("--pilot-realizations", type=int, default=1, choices=range(1, 9),
                        help="Consecutive sourcefiles realizations starting at --sourcefiles; requires --pilot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--submit", action="store_true")
    mode.add_argument("--bundle", type=Path, help="Create a local bundle without submission")
    args = parser.parse_args()
    if args.site is not None and (args.sourcefiles is not None or args.realization or args.drm_root
                                  or args.pilot or args.no_basin_only or args.pilot_realizations != 1):
        parser.error("--site cannot be combined with realization or pilot options")
    if args.no_basin_only and not args.pilot:
        parser.error("--no-basin-only requires --pilot")
    if args.pilot_realizations != 1 and (not args.pilot or args.sourcefiles is None):
        parser.error("--pilot-realizations requires --pilot and --sourcefiles")
    if args.sourcefiles is not None:
        if args.realization or args.drm_root:
            parser.error("--sourcefiles cannot be combined with --realization or --drm-root")
        run_inputs = realization_inputs(args.sourcefiles, pilot=args.pilot)
    else:
        run_inputs = dict(realization_id=args.realization or REALIZATION_ID)
        if args.drm_root:
            run_inputs["drm_root"] = args.drm_root
        if args.pilot:
            run_inputs["sites"] = [0]
    if args.no_basin_only:
        run_inputs["basin_cases"] = ["no_basin"]
    if args.pilot_realizations > 1:
        if args.sourcefiles + args.pilot_realizations > 11:
            parser.error("Requested sourcefiles range extends beyond realization 10")
        configurations = []
        for index in range(args.sourcefiles, args.sourcefiles + args.pilot_realizations):
            options = realization_inputs(index, pilot=True)
            if args.no_basin_only:
                options["basin_cases"] = ["no_basin"]
            configurations.append(options)
        run_inputs = dict(realizations=configurations)
    if args.site is not None:
        run_inputs = site_campaign_inputs(args.site)
    configured = build_workflow(run_inputs)
    if args.bundle:
        from femora.jobs.bundle import bundle
        print(bundle(source=__file__, destination=args.bundle, inputs=run_inputs))
        raise SystemExit(0)
    if not args.submit:
        count = len(configured.stages[-2].tasks)
        print(f"Validated {count}-case workflow configuration; {requested_nodes(configured)} nodes; "
              f"MUMPS icntl14={MUMPS_ICNTL14}. Use --bundle PATH to inspect, or --submit to submit.")
        raise SystemExit(0)
    job = fm.submit(
        function=build_workflow,
        inputs=run_inputs,
        platform="tacc",
        settings={
            "app_id": "amnp95-femora-workflow-stampede3",
            "system": "stampede3",
            "queue": "spr",
            "allocation": "DesignSafe-SimCenter",
            "nodes": requested_nodes(configured),
            "cores_per_node": CORES_PER_NODE,
            "minutes": 2880,
        },
    )
    print(f"Job UUID: {job.id}")
