"""Documentation contracts for the curated Core API."""

import ast
from pathlib import Path
import re
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src/femora/core"
DOCUMENTED = ("action_base", "action_manager", "process_manager", "model",
              "material_manager", "nd_material_manager", "uniaxial_material_manager", "material_base",
              "element_manager", "beam_element_manager", "brick_element_manager",
              "quad_element_manager", "special_element_manager", "element_base",
              "section_manager", "section_base", "transformation_manager", "transformation_base",
              "meshpart_manager", "meshpart_base", "line_meshpart_base", "assembler",
              "constraint_manager", "constraint_base", "sp_constraint_manager",
              "mp_constraint_manager", "interface_base", "damping_manager", "damping_base",
              "region_manager", "region_base", "mass_manager", "mask_manager", "group",
              "load_manager", "load_base", "time_series_manager", "time_series_base",
              "ground_motion_manager", "ground_motion_base", "pattern_manager", "pattern_base",
              "recorder_manager", "recorder_base", "event_bus", "analysis_manager",
              "analysis_component_base", "numberer_manager",
              "analysis/algorithm_manager", "analysis/constraint_handler_manager",
              "analysis/system_manager", "analysis/test_manager", "analysis/integrator_manager",
              "analysis/algorithm", "analysis/constraint_handler", "analysis/system",
              "analysis/test", "analysis/numberer", "analysis/integrator", "tagged_component_manager")


def test_completed_core_explicit_members_are_documented():
    for name in DOCUMENTED:
        tree = ast.parse((CORE / f"{name}.py").read_text(encoding="utf-8-sig"))
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            if cls.name.startswith("_"):
                for method in (n for n in cls.body if isinstance(n, ast.FunctionDef)
                               and not n.name.startswith("_")):
                    assert ast.get_docstring(method), (cls.name, method.name)
                continue
            controls = next(ast.literal_eval(node.value) for node in cls.body
                            if isinstance(node, ast.Assign) and any(
                                isinstance(t, ast.Name) and t.id == "__doc_controls__"
                                for t in node.targets))
            methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
            for member in controls["members"]:
                assert ast.get_docstring(methods[member]), (cls.name, member)


def test_core_examples_compile():
    for name in ("__init__", *DOCUMENTED):
        path = CORE / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                for code in re.findall(r"```python\n(.*?)```", ast.get_docstring(node) or "", re.S):
                    compile(dedent(code), str(path), "exec")


def test_action_process_examples_execute_without_solver():
    from femora import Model

    model = Model()
    assert model.process.add_step(model.actions.load_const(), "Hold gravity") == 0
    assert model.process.add_step(model.actions.set_time(0.0), "Reset clock") == 1
    text = model.process.to_tcl()
    assert "loadConst" in text and "setTime" in text
    assert "-time" not in model.actions.load_const().to_tcl()
    assert model.process.get_step(-1) is None
    assert not model.process.remove_step(-1)
    assert model.process.insert_step(-1, model.actions.tcl("puts ready"))
    assert "puts ready" in model.process.to_tcl()


def test_material_examples_and_model_clear_semantics():
    from femora import Model

    model = Model(model_name="site", model_path="example_outputs/site")
    soil = model.material.nd.elastic_isotropic(user_name="soil", E=108000.0, nu=1/3, rho=1.8)
    steel = model.material.uniaxial.elastic(user_name="steel", E=200e6)
    assert model.material.get(soil.tag) is soil
    assert model.material.get_by_name("steel") is steel
    snapshot = model.material.get_all()
    snapshot.clear()
    assert len(model.material) == 2
    model.set_results_folder("results")
    model.clear_model()
    assert model.model_name == "site"
    assert model.model_path == "example_outputs/site"
    assert model.get_results_folder() == "results"
    assert model.assembled_mesh is None
    assert not model.material.get_all()


def test_documented_examples_execute_without_solver(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("__init__", *DOCUMENTED):
        path = CORE / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                for code in re.findall(r"```python\n(.*?)```", ast.get_docstring(node) or "", re.S):
                    exec(compile(dedent(code), str(path), "exec"), {})


def test_region_damping_lifecycle_contracts():
    import pytest
    from femora import Model

    model = Model()
    damping = model.damping.frequency_rayleigh(damping_factor=0.03, f1=3, f2=15)
    region = model.region.element(user_name="soil", damping=damping)
    assert model.region.get("soil") is region
    assert region.damping is damping
    assert model.region.get_all()[0] is model.region.global_region
    with pytest.raises(ValueError, match="global region"):
        model.region.remove(0)
    old_global = model.region.global_region
    model.region.clear()
    assert model.region.global_region is not old_global
    assert old_global.tag is None
    assert model.damping.get(damping.tag) is damping


def test_all_visible_core_classes_are_covered_by_documentation_audit():
    hidden = {"part_registry", "tagging", "element_group"}
    audited = set(DOCUMENTED)
    for path in CORE.rglob("*.py"):
        if path.stem in hidden or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        public = [node for node in tree.body if isinstance(node, ast.ClassDef)
                  and not node.name.startswith("_")]
        if public:
            assert path.relative_to(CORE).with_suffix("").as_posix() in audited, path
            for cls in public:
                assert ast.get_docstring(cls), (path, cls.name)
