"""Validate the campaign without reading DRM inputs or submitting jobs."""

import importlib.util
import ast
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd
import numpy as np
import h5py
import pytest

from femora.jobs.backends import TACC
from femora.jobs.bundle import bundle


def load_example():
    path = Path(__file__).resolve().parents[2] / "examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py"
    spec = importlib.util.spec_from_file_location("hercules_ssi_campaign", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_case_count_resources_and_phase_order():
    module = load_example()
    workflow = module.build_workflow()
    assert [stage.name for stage in workflow.stages] == [
        "build_no_basin", "solve_no_basin", "build_plastic", "solve_plastic",
        "postprocess", "summary",
    ]
    backend = TACC()
    for stage in workflow.stages:
        backend.validate(stage)
    for build, solve in ((workflow.stages[0], workflow.stages[1]),
                         (workflow.stages[2], workflow.stages[3])):
        assert len(build.tasks) == len(solve.tasks) == 32
        assert not build.parallel and solve.parallel
        assert sum(task.ranks for task in solve.tasks) == 2816
        assert {task.name for task in build.tasks} == {task.name for task in solve.tasks}
        assert all(task.script == f"{build.name}/{task.name}/model.tcl" for task in solve.tasks)
    post = workflow.stages[4]
    assert len(post.tasks) == len({task.name for task in post.tasks}) == 64
    options = [task.kwargs for task in post.tasks]
    assert {item["site"] for item in options} == set(range(8))
    assert {item["basin_case"] for item in options} == {"no_basin", "plastic"}
    assert {item["building_type"] for item in options} == {"five_story", "ten_story"}
    assert {item["foundation_type"] for item in options} == {"mat", "pile"}
    assert module.NODES * module.CORES_PER_NODE == 3136
    assert module.RANKS_PER_CASE == module.SOIL_PARTITIONS + module.ABSORBER_PARTITIONS + 2 == 88
    assert module.FINAL_TIME == 35.0
    assert module.EXPLICIT_DT == 5e-5
    assert module.DYNAMIC_DT == 0.01


def test_single_file_bundle_and_combined_summary(tmp_path):
    module = load_example()
    archive = bundle(source=module.__file__, destination=tmp_path / "workflow.zip", inputs={})
    with ZipFile(archive) as contents:
        assert set(contents.namelist()) == {"workflow.py", "inputs.json", "bundle.json"}

    summaries = {}
    for index in range(64):
        path = tmp_path / f"case_{index}.csv"
        pd.DataFrame({"case": [f"case_{index}"], "peak": [index]}).to_csv(path, index=False)
        summaries[f"case_{index}"] = path
    output = module.combine_summaries(SimpleNamespace(
        output_dir=tmp_path, results={"postprocess": summaries},
    ))
    combined = pd.read_csv(output)
    assert len(combined) == combined["case"].nunique() == 64


def test_realization_ids_and_explicit_inputs():
    module = load_example()
    with pytest.raises(ValueError, match="explicit drm_root"):
        module.build_workflow({"realization_id": "r01"})
    with pytest.raises(ValueError, match="realization_id"):
        module.build_workflow({"realization_id": "../r01"})
    workflow = module.build_workflow({"realization_id": "r01", "drm_root": "/inputs/r01"})
    tasks = workflow.stages[0].tasks
    assert all(t.name.startswith("r01_site_") for t in tasks)
    assert all(t.kwargs["drm_root"] == "/inputs/r01" for t in tasks)
    assert workflow.output_patterns == ("postprocess/**/*", "summary/**/*")


def test_canonical_realizations_total_640_and_pilot():
    module = load_example()
    names = set()
    for i in range(1, 11):
        options = module.realization_inputs(i)
        assert options["drm_root"].replace("\\", "/").endswith(f"Canonical_Mw7.0/sourcefiles{i}/h5drm")
        workflow = module.build_workflow(options)
        names.update(t.name for t in workflow.stages[-2].tasks)
    assert len(names) == 640
    pilot = module.build_workflow(module.realization_inputs(1, pilot=True))
    assert len(pilot.stages[-2].tasks) == 8
    assert sum(t.ranks for t in pilot.stages[1].tasks) == 352
    with pytest.raises(ValueError):
        module.build_workflow({"sites": [0, 0]})


def test_no_basin_only_pilot():
    module = load_example()
    options = module.realization_inputs(1, pilot=True)
    options["basin_cases"] = ["no_basin"]
    workflow = module.build_workflow(options)
    assert [s.name for s in workflow.stages] == ["build_no_basin", "solve_no_basin", "postprocess", "summary"]
    assert len(workflow.stages[-2].tasks) == 4
    assert sum(t.ranks for t in workflow.stages[1].tasks) == 352
    assert all(t.kwargs["basin_case"] == "no_basin" for t in workflow.stages[-2].tasks)


def test_four_realization_no_basin_pilot():
    module = load_example()
    options = []
    for i in range(1, 5):
        config = module.realization_inputs(i, pilot=True)
        config["basin_cases"] = ["no_basin"]
        options.append(config)
    workflow = module.build_workflow({"realizations": options})
    assert len(workflow.stages[-2].tasks) == 16
    solve = workflow.stages[1]
    assert solve.parallel and sum(t.ranks for t in solve.tasks) == 1408
    assert module.requested_nodes(workflow) == 13
    post = workflow.stages[-2].tasks
    assert {t.kwargs["realization_id"] for t in post} == {f"sourcefiles{i}" for i in range(1,5)}
    assert len({t.name for t in post}) == 16
    assert [s.name for s in workflow.stages] == ["build_no_basin", "solve_no_basin", "postprocess", "summary"]
    with pytest.raises(ValueError, match="duplicate"):
        module.build_workflow({"realizations": [options[0], options[0]]})


def test_site_campaign_phase_order_resources_and_total_640():
    module = load_example()
    all_cases = set()
    for site in range(8):
        workflow = module.build_workflow(module.site_campaign_inputs(site))
        assert [s.name for s in workflow.stages] == [
            "build_no_basin", "solve_no_basin",
            "build_plastic", "solve_plastic", "postprocess", "summary"]
        assert workflow.name == f"hercules-site-{site}-10-realizations"
        assert module.requested_nodes(workflow) == 32
        for build_index, solve_index in ((0,1),(2,3)):
            build = workflow.stages[build_index]
            waves = [workflow.stages[solve_index]]
            solves = [t for wave in waves for t in wave.tasks]
            assert len(build.tasks) == len(solves) == 40
            assert not build.parallel and all(w.parallel for w in waves)
            assert [len(w.tasks) for w in waves] == [40]
            assert all(sum(t.ranks for t in w.tasks) <= 32*112 for w in waves)
            assert sum(t.ranks for t in solves) == 3520
            assert {t.name for t in build.tasks} == {t.name for t in solves}
            assert all(t.script == f"{build.name}/{t.name}/model.tcl" for t in solves)
        post = workflow.stages[-2].tasks
        assert len(post) == 80
        assert {t.kwargs["site"] for t in post} == {site}
        assert {t.kwargs["realization_id"] for t in post} == {f"sourcefiles{i}" for i in range(1,11)}
        all_cases.update(t.name for t in post)
        for stage in workflow.stages:
            TACC().validate(stage)
    assert len(all_cases) == 640
    with pytest.raises(ValueError):
        module.site_campaign_inputs(8)


def test_all_mumps_calls_use_200_margin():
    module = load_example()
    assert module.MUMPS_ICNTL14 == 200
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node,ast.Call)
             and isinstance(node.func,ast.Attribute) and node.func.attr=="mumps"]
    assert len(calls)==3
    for call in calls:
        value = next(k.value for k in call.keywords if k.arg=="icntl14")
        assert isinstance(value,ast.Name) and value.id=="MUMPS_ICNTL14"


def write_recorder(path, points, cells, displacement=None):
    points, cells = np.asarray(points, dtype=float), np.asarray(cells, dtype=int)
    times = np.array([0., 17.5, 35.])
    with h5py.File(path, "w") as f:
        r = f.create_group("VTKHDF")
        r["Points"], r["Types"] = points, np.full(len(cells), 12)
        r["Offsets"], r["Connectivity"] = np.arange(len(cells)+1)*8, cells.reshape(-1)
        r["Steps/Values"] = times
        r["PointData/nodeTags"] = np.arange(1,len(points)+1)
        r["CellData/eleTags"] = np.arange(1,len(cells)+1)
        for location, names, count, components in [
            ("PointData", ("displacement", "velocity", "acceleration"), len(points), 3),
            ("CellData", ("stress3D6", "strain3D6"), len(cells), 6),
        ]:
            for name in names:
                a = np.ones((3, count, components))
                if name == "displacement" and displacement is not None:
                    a = displacement
                r[f"{location}/{name}"] = a.reshape(-1,components)
                r[f"Steps/{location}Offsets/{name}"] = np.arange(3)*count


def test_compact_foundation_rigid_fit_and_nonfinite_rejection(tmp_path):
    module = load_example()
    module.RECORDER_DT = 17.5
    points = np.array([[-1,-1,-4],[1,-1,-4],[1,1,-4],[-1,1,-4],
                       [-1,-1,-2],[1,-1,-2],[1,1,-2],[-1,1,-2]], dtype=float)
    theta = np.array([.001,-.002,.003])
    translation = np.array([.1,.2,.3])
    u = np.stack([i*(translation + np.cross(theta, points-points.mean(axis=0))) for i in range(3)])
    source = tmp_path / "foundation0.vtkhdf"
    write_recorder(source, points, [range(8)], u)
    output = tmp_path / "foundation.h5"
    report = module.compact_recorder([source], output)
    assert report["nodes"] == 8
    with h5py.File(output) as f:
        np.testing.assert_allclose(f["rigid_fit/rotation_rad"][-1], 2*theta, atol=1e-12)
        np.testing.assert_allclose(f["rigid_fit/translation_m"][-1], 2*translation, atol=1e-12)
        assert np.max(f["rigid_fit/residual_rms_m"][:]) < 1e-12
        np.testing.assert_allclose(f["nodes/displacement"][:], u)
    with h5py.File(source, "r+") as f:
        f["VTKHDF/PointData/displacement"][0,0] = np.nan
    with pytest.raises(ValueError, match="Invalid history"):
        module.compact_recorder([source], tmp_path/"bad.h5")


def test_compact_borehole_complete_selection_and_flags(tmp_path):
    module = load_example()
    module.RECORDER_DT = 17.5
    points = np.array([[x,y,z] for z in range(-48,-3,4) for y in (-4,0,4) for x in (-4,0,4)])
    cells=[]
    for k in range(11):
        for j in range(2):
            for i in range(2):
                n=k*9+j*3+i
                cells.append([n,n+1,n+4,n+3,n+9,n+10,n+13,n+12])
    source=tmp_path/"borehole0.vtkhdf"
    write_recorder(source,points,cells)
    output=tmp_path/"borehole.h5"
    report=module.compact_recorder([source],output,borehole=True)
    assert report["nodes"]==12 and report["cells"]==44
    with h5py.File(output) as f:
        assert f["nodes/exclude_from_soil_comparison"][:].sum()==1
        assert f["cells/exclude_from_soil_comparison"][:].sum()==4
        assert f["cells/strain3D6"].shape==(3,44,6)
