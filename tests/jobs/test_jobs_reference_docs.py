"""Keep the Jobs reference source-driven, curated, and executable where safe."""

import ast
from contextlib import contextmanager
from pathlib import Path
import re
import runpy
import subprocess
import sys
from textwrap import dedent
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_jobs_public_classes_have_explicit_documentation_controls():
    for path in (ROOT / "src/femora/jobs").rglob("*.py"):
        if path.name == "tracker_ui.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            assert ast.get_docstring(node), node.name
            controls = next((ast.literal_eval(item.value) for item in node.body
                             if isinstance(item, ast.Assign) and any(
                                 isinstance(target, ast.Name) and target.id == "__doc_controls__"
                                 for target in item.targets)), None)
            assert controls is not None, node.name
            methods = {item.name: item for item in node.body if isinstance(item, ast.FunctionDef)}
            for name in controls["members"]:
                assert not name.startswith("_"), (node.name, name)
                assert name in methods, (node.name, name)
                assert ast.get_docstring(methods[name]), (node.name, name)


def test_jobs_examples_compile_and_overview_runs_without_remote_side_effects(tmp_path):
    for path in (ROOT / "src/femora/jobs").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                for example in re.findall(r"```python\n(.*?)```", ast.get_docstring(node) or "", re.S):
                    compile(dedent(example), str(path), "exec")
    tree = ast.parse((ROOT / "src/femora/jobs/__init__.py").read_text())
    examples = re.findall(r"```python\n(.*?)```", ast.get_docstring(tree), re.S)
    example = next(example for example in examples if "def build_workflow():" in example)
    script = tmp_path / "example.py"
    script.write_text(example, encoding="utf-8")
    completed = subprocess.run([sys.executable, str(script)], cwd=tmp_path,
                               capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "work/prepare/value/value.txt").read_text() == "4"
    assert (tmp_path / "work/manifest.json").is_file()


def test_generated_jobs_routes_include_functions_and_hide_internal_ui(tmp_path, monkeypatch):
    gen_files = pytest.importorskip("mkdocs_gen_files")

    @contextmanager
    def output(path, mode):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(mode, encoding="utf-8") as stream:
            yield stream

    monkeypatch.setitem(sys.modules, "mkdocs_gen_files", SimpleNamespace(
        Nav=gen_files.Nav, open=output, set_edit_path=lambda *args: None))
    namespace = runpy.run_path(str(ROOT / "website/gen_ref_pages.py"))
    reference = tmp_path / "reference"
    jobs = reference / "jobs"
    for slug, target in (("execute", "femora.jobs.runner"),
                         ("tracking", "femora.jobs.tracking"),
                         ("submit", "femora.jobs.submission"),
                         ("bundle", "femora.jobs.bundle"),
                         ("command-line", "femora.jobs.__main__")):
        assert f"::: {target}" in (jobs / slug / "index.md").read_text()
    assert "- list_jobs" in (jobs / "tracking/index.md").read_text()
    assert "- submit" in (jobs / "submit/index.md").read_text()
    assert "summary: true" in (jobs / "TrackedJob/index.md").read_text()
    assert "Classes in this package:" not in (jobs / "index.md").read_text()
    summary = (reference / "SUMMARY.md").read_text()
    for private in ("JobTracker", "Prompt", "Details", "resolve_platform"):
        assert private not in summary
    assert not (reference / "cli.md").exists()
    assert "- setup" in (reference / "runtime/index.md").read_text()
    assert "summary: true" in (reference / "runtime/index.md").read_text()
    stack, paths = [], []
    for item in namespace["nav"].items():
        stack = stack[:item.level] + [item.title]
        paths.append(tuple(stack))
    assert [path[1] for path in paths if len(path) == 2 and path[0] == "jobs"] == [
        "overview", "tasks", "workflows", "execute workflows", "submit remotely",
        "track jobs", "bundles and replay", "command line", "advanced"]
    assert ("runtime", "errors", "RuntimeSetupError") in paths
    assert ("core", "actions", "ActionManager") in paths
    assert ("core", "actions", "extension API", "Action") in paths
    assert ("core", "materials", "NDMaterialManager") in paths
    assert ("core", "analysis", "algorithm", "AlgorithmManager") in paths
    assert ("core", "process", "ProcessManager") in paths
    for internal in ("EventBus", "FemoraPartRegistry", "FemoraPart", "TaggedComponentManager",
                     "TaggedObject", "TaggingPolicy", "CompactRetagPolicy"):
        assert all(path[-1] != internal for path in paths if path[0] == "core")
    assert "Classes in this package:" not in (reference / "core/index.md").read_text()
    section_page = (reference / "core/SectionManager/index.md").read_text()
    for helper in ("_BeamSectionNamespace", "_CompositeSectionNamespace", "_FiberSectionNamespace",
                   "_ShellSectionNamespace", "_SpecialSectionNamespace"):
        assert f"::: femora.core.section_manager.{helper}" in section_page
    for manager, helper in (("MassManager", "femora.core.mass_manager._GlobalMassHelper"),
                            ("RegionManager", "femora.core.region_manager._ElementRegionFactory"),
                            ("InterfaceManager", "femora.core.interface_base._BoundaryNamespace")):
        assert f"::: {helper}" in (reference / f"core/{manager}/index.md").read_text()
    core_groups = [path[1] for path in paths if len(path) == 2 and path[0] == "core"]
    assert core_groups == ["overview", *namespace["CORE_GROUPS"]]
    for group, manager in (("materials", "MaterialManager"), ("mesh parts", "MeshPartManager"),
                           ("selections", "GroupManager")):
        children = [path[-1] for path in paths if len(path) == 3 and path[:2] == ("core", group)]
        assert children[0] == manager
    assert ("jobs", "submit remotely", "TACCPlatform") in paths
    assert ("jobs", "advanced", "platform interfaces", "Platform") in paths
    assert ("jobs", "tasks", "Python") in paths
    assert ("jobs", "workflows", "Workflow") in paths
    assert [path[0] for path in paths if len(path) == 1][:7] == [
        "components", "core", "io", "tools", "Results & Postprocessing", "jobs", "runtime"]


def test_jobs_icons_are_scoped_and_class_names_preserved():
    hook = runpy.run_path(str(ROOT / "website/results_api_hook.py"))
    task = SimpleNamespace(title="Python", meta={}, children=None)
    group = SimpleNamespace(title="workflows", children=[task])
    jobs = SimpleNamespace(title="jobs", children=[group])
    other = SimpleNamespace(title="components", children=[])
    context = {"nav": [other, jobs]}
    hook["on_page_context"](context)
    assert jobs.meta["icon"] == "material/sitemap-outline"
    assert group.meta["icon"] == "material/source-branch"
    assert task.meta["icon"] == "material/language-python"
    assert task.title == "Python"
    assert not hasattr(other, "meta")


def test_curated_icons_exist_in_the_installed_theme():
    material = pytest.importorskip("material")
    icons = Path(material.__file__).parent / "templates/.icons"
    hook = runpy.run_path(str(ROOT / "website/results_api_hook.py"))
    for icon in set(hook["GROUP_ICONS"].values()) | set(hook["CLASS_ICONS"].values()):
        assert (icons / (icon + ".svg")).is_file(), icon
