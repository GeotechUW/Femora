"""Keep the generated Results reference curated and source-driven."""

import ast
from contextlib import contextmanager
from pathlib import Path
import runpy
import re
import sys
from types import SimpleNamespace
from textwrap import dedent

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_results_navigation_icons_are_scoped_and_preserve_metadata():
    hook = runpy.run_path(str(ROOT / "website/results_api_hook.py"))
    leaf = SimpleNamespace(title="ResultSet", meta={"title": "ResultSet"}, children=None)
    reading = SimpleNamespace(title="Reading Results", children=[leaf])
    results = SimpleNamespace(title="Results & Postprocessing", children=[reading])
    other = SimpleNamespace(title="io", children=[])
    context = {"nav": [other, results]}
    assert hook["on_page_context"](context) is context
    assert results.meta["icon"] == "material/chart-line"
    assert reading.meta["icon"] == "material/folder-open-outline"
    assert results.title == "results & postprocessing"
    assert reading.title == "reading results"
    assert leaf.title == "ResultSet"
    assert leaf.meta == {"title": "ResultSet", "icon": "material/cube-outline"}
    assert not hasattr(other, "meta")
    hook["on_page_context"](context)
    assert leaf.meta["title"] == "ResultSet"


def test_result_member_controls_have_documented_members():
    for path in (ROOT / "src/femora/results").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            assignments = [item for item in node.body if isinstance(item, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "__doc_controls__"
                                   for target in item.targets)]
            assert assignments, f"Missing member controls: {node.name}"
            members = ast.literal_eval(assignments[0].value)["members"]
            methods = {item.name: item for item in node.body
                       if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for name in members:
                assert name in methods, f"Unknown documented member {node.name}.{name}"
                assert ast.get_docstring(methods[name]), f"Missing docstring {node.name}.{name}"
                assert not name.startswith("_"), f"Implementation detail exposed: {name}"


def test_docstring_examples_are_valid_python_and_returns_have_types():
    griffe = pytest.importorskip("griffe")
    package = griffe.GriffeLoader(search_paths=[ROOT / "src"], allow_inspection=False).load("femora.results")
    for path in (ROOT / "src/femora/results").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            for snippet in re.findall(r"```python\n(.*?)```", doc, flags=re.S):
                compile(dedent(snippet), str(path), "exec")
    building = package["building"]["BuildingResults"]
    for name in ("members", "floor_displacement", "floor_acceleration", "interstory_drift",
                 "member_forces", "story_shear", "base_shear", "overturning_moment",
                 "summary", "export_csv"):
        sections = building[name].docstring.parse("google")
        returns = next(section for section in sections if section.kind.value == "returns")
        assert len(returns.value) == 1
        assert returns.value[0].annotation is not None


def test_generator_includes_functions_classes_and_curated_navigation(tmp_path, monkeypatch):
    gen_files = pytest.importorskip("mkdocs_gen_files")

    @contextmanager
    def output(path, mode):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(mode, encoding="utf-8") as stream:
            yield stream

    monkeypatch.setitem(sys.modules, "mkdocs_gen_files", SimpleNamespace(
        Nav=gen_files.Nav, open=output, set_edit_path=lambda *args: None,
    ))
    namespace = runpy.run_path(str(ROOT / "website/gen_ref_pages.py"))
    reference = tmp_path / "reference/results"
    assert "members:\n        - open_results" in (reference / "open-results/index.md").read_text()
    assert "::: femora.results.result_set.ResultSet" in (reference / "ResultSet/index.md").read_text()
    assert "::: femora.results.register_reader" in (reference / "register-reader/index.md").read_text()
    assert "members: []" in (reference / "PointSelection/index.md").read_text()
    building = (reference / "BuildingResults/index.md").read_text()
    assert "- floor_displacement" in building and "- _bind" not in building
    summary = (tmp_path / "reference/SUMMARY.md").read_text()
    assert "Results & Postprocessing" in summary
    assert "Open Result Files" in summary and "Building Responses" in summary
    assert "Reader Extensions" in summary and "DeformationRenderer" in summary
    for page in (reference / "ResultSet/index.md", reference / "BuildingResults/index.md",
                 reference / "visualization/DeformationRenderer/index.md"):
        assert "summary: true" in page.read_text()
    navigation = namespace["nav"]
    stack, result_paths = [], []
    for item in navigation.items():
        stack = stack[:item.level] + [item.title]
        if stack[0] == "Results & Postprocessing":
            result_paths.append(tuple(stack))
    assert [keys[1] for keys in result_paths if len(keys) == 2] == [
        "Overview", "Reading Results", "Building Responses", "Visualization", "Advanced",
    ]
    prefix = ("Results & Postprocessing",)
    assert prefix + ("Reading Results", "ResultSet") in result_paths
    assert prefix + ("Reading Results", "PointSelection") in result_paths
    assert prefix + ("Building Responses", "BuildingResults") in result_paths
    assert prefix + ("Visualization", "DeformationRenderer") in result_paths
    assert prefix + ("Advanced", "File Readers", "VTKHDFResultReader") in result_paths
    assert prefix + ("Advanced", "Errors", "ResultFormatError") in result_paths
    assert "icon: material/chart-line" in (reference / "index.md").read_text()
    assert "Classes in this package:" not in (reference / "index.md").read_text()

    # Windows-authored source files with a BOM must not disappear from the API.
    source = tmp_path / "bom.py"
    source.write_text('"""Package guide."""\nclass Example:\n    """Public class."""\n', encoding="utf-8-sig")
    assert namespace["parse_module_docstring"](source) == "Package guide."
    assert namespace["parse_public_classes"](source) == [("Example", {})]
