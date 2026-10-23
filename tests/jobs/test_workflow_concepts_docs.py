"""Two concept pages teach workflows and jobs through one runnable example."""

from pathlib import Path
import re
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website/docs"
PAGES = [DOCS / "concepts/workflows.md", DOCS / "concepts/jobs.md"]


def expand_snippet(match):
    path, tag = match.group(1).rsplit(":", 1)
    source = (ROOT / path).read_text(encoding="utf-8-sig")
    start = f"# --8<-- [start:{tag}]"
    end = f"# --8<-- [end:{tag}]"
    assert start in source and end in source
    return source.split(start, 1)[1].split(end, 1)[0].strip()


def test_workflow_concepts_use_valid_examples_and_existing_icons():
    import material

    icons = Path(material.__file__).parent / "templates/.icons"
    assert len(PAGES) == 2
    for path in PAGES:
        content = path.read_text(encoding="utf-8")
        icon = re.search(r"^icon: (.+)$", content, re.M).group(1)
        assert (icons / (icon + ".svg")).is_file(), (path, icon)
        for example in re.findall(r"```python\n(.*?)```", content, re.S):
            expanded = re.sub(r'--8<-- "([^"]+)"', expand_snippet, example)
            compile(dedent(expanded), str(path), "exec")


def test_concept_navigation_has_only_workflows_then_jobs():
    config = (ROOT / "website/mkdocs.yml").read_text(encoding="utf-8")
    expected = ["- Process: concepts/process.md", "- Workflows: concepts/workflows.md",
                "- Jobs: concepts/jobs.md"]
    offsets = [config.index(page) for page in expected]
    assert offsets == sorted(offsets)
    assert "concepts/workflows/" not in config
    assert "workflow-walkthrough" not in config
    assert not (DOCS / "concepts/workflow-walkthrough.md").exists()
    assert not list((DOCS / "concepts/workflows").glob("*.md"))
    workflow = PAGES[0].read_text()
    assert "workspace-view" in workflow
    for name in ("input", "calculate", "report", "workflow", "execute"):
        assert f'workflow_basics.py:{name}"' in workflow
    assert "A task can represent work done in Python" in workflow
    assert "Femora currently provides three task types" not in workflow
    assert "## 9. Understand Cores, Ranks, And Parallel Stages" in workflow
    assert "### Try A Controlled Failure" in workflow
    assert "## 1. Submit The Same Example" in PAGES[1].read_text()
    for page in PAGES:
        assert "reference/" in page.read_text()
