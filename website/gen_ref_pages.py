"""Generate the code reference pages and navigation."""

from __future__ import annotations

import ast
from pathlib import Path

import mkdocs_gen_files

# Folders to completely hide from the generated API docs.
SKIP_FOLDERS = {"gui", "constants", "constant", "styles", "utils"}

# Modules to skip (legacy shims without valid imports - break mkdocstrings if scanned).
SKIP_MODULE_NAMES = {"materialsOpenSees"}

nav = mkdocs_gen_files.Nav()

script_dir = Path(__file__).parent
src_root = (script_dir.parent / "src").resolve()
TOP_LEVEL_LABELS = {
    "components": "components",
    "core": "core",
    "tools": "tools",
    "io": "io",
    "results": "Results & Postprocessing",
}

COMPONENT_PACKAGE_ORDER = [
    "material",
    "section",
    "transformation",
    "element",
    "damping",
    "region",
    "mesh",
    "geometry_ops",
    "interface",
    "constraint",
    "time_series",
    "pattern",
    "ground_motion",
    "load",
    "recorder",
    "actions",
    "analysis",
    "mask",
    "event",
    "partitioner",
    "simcenter",
]
COMPONENT_PACKAGE_ORDER_INDEX = {
    name: index for index, name in enumerate(COMPONENT_PACKAGE_ORDER)
}

for package_name in COMPONENT_PACKAGE_ORDER:
    nav[("components", package_name)] = f"components/{package_name}/index.md"


def display_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Return navigation parts with the top-level ``femora`` package collapsed."""
    if parts and parts[0] == "femora":
        parts = parts[1:]
    if not parts:
        return parts
    if parts[0] == "results" and len(parts) > 1:
        if parts[1] == "readers":
            parts = (parts[0], "Advanced", "File Readers") + parts[2:]
        elif parts[1] == "visualization":
            parts = (parts[0], "Visualization") + parts[2:]
    if parts[:2] == ("jobs", "platforms"):
        parts = ("jobs",) + parts[2:]
    head = TOP_LEVEL_LABELS.get(parts[0], parts[0])
    return (head,) + parts[1:]


def doc_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Return filesystem doc parts with the top-level ``femora`` package collapsed."""
    if parts and parts[0] == "femora":
        return parts[1:]
    return parts


def package_sort_key(item: tuple[tuple[str, ...], Path, str]) -> tuple:
    """Return a stable nav sort key for package landing pages."""
    nav_parts, _path, _description = item
    if len(nav_parts) >= 3 and nav_parts[:2] == ("femora", "components"):
        top_level_name = nav_parts[2]
        return (
            0,
            COMPONENT_PACKAGE_ORDER_INDEX.get(top_level_name, len(COMPONENT_PACKAGE_ORDER)),
            nav_parts[3:],
        )
    return (1, nav_parts)


def should_skip(parts: tuple[str, ...]) -> bool:
    """Return True when a module path should not appear in the docs."""
    if parts in {("femora", "cli"), ("femora", "jobs", "tracker_ui"),
                 ("femora", "jobs", "platforms", "resolve")}:
        return True
    if parts and parts[-1] in SKIP_MODULE_NAMES:
        return True
    if set(parts).intersection(SKIP_FOLDERS):
        return True
    if any(part.startswith("_") for part in parts if part != "__init__"):
        return True
    if parts[-1] == "__main__":
        return True
    return "gui" in parts[-1].lower()


def parse_public_classes(path: Path) -> list[tuple[str, dict]]:
    """Return top-level public class names and doc controls from a module."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except Exception as exc:
        print(f"WARNING: Could not parse {path}: {exc}")
        return []

    classes: list[tuple[str, dict]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            doc_controls: dict = {}
            for class_node in node.body:
                if not isinstance(class_node, ast.Assign):
                    continue
                for target in class_node.targets:
                    if isinstance(target, ast.Name) and target.id == "__doc_controls__":
                        try:
                            doc_controls = ast.literal_eval(class_node.value)
                        except Exception as exc:
                            print(
                                f"WARNING: Could not parse __doc_controls__ "
                                f"for {path}:{node.name}: {exc}",
                            )
                            doc_controls = {}
                        break
            classes.append((node.name, doc_controls))
    return classes


def parse_module_docstring(path: Path) -> str:
    """Return the top-level module docstring, or an empty string."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except Exception as exc:
        print(f"WARNING: Could not parse docstring from {path}: {exc}")
        return ""
    return ast.get_docstring(tree) or ""


def split_front_matter(docstring: str) -> tuple[str, str]:
    """Split YAML front matter from a docstring body, if present."""
    if not docstring:
        return "", ""

    lines = docstring.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", docstring

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        return "", docstring

    front_matter = "\n".join(lines[: closing_index + 1])
    body = "\n".join(lines[closing_index + 1 :]).lstrip()
    return front_matter, body


GROUPED_PACKAGE_TITLES: dict[str, dict[str, str]] = {
    "femora.components.analysis": {
        "constraint_handlers": "⛓ constraint handlers",
        "numberers": "⌗ numberers",
        "systems": "⚙ systems",
        "algorithms": "λ algorithms",
        "convergence_tests": "✓ convergence tests",
        "integrators": "∫ integrators",
        "analysis": "◎ core analysis",
    },
    "femora.components.constraint": {
        "sp_constraints": "sp constraints",
        "mp_constraints": "mp constraints",
    },
    "femora.components.element": {
        "beam": "─ beam",
        "brick": "▣ brick",
        "quad": "▭ quad",
        "special": "✦ special",
    },
}

HIDDEN_PACKAGE_CLASSES: dict[str, set[str]] = {
    "femora.components.analysis": {
        "Algorithm",
        "ConstraintHandler",
        "Test",
        "Integrator",
        "StaticIntegrator",
        "TransientIntegrator",
        "Numberer",
        "System",
    },
}

PACKAGE_GUIDES: dict[str, tuple[str, str]] = {
    "femora.components.event": (
        "guide",
        """# Event Guide

The Femora event system is an advanced runtime API for lifecycle-sensitive
work. It exists so model-owned subsystems can react to assembly and export
stages without hard-coding every extension directly into the core pipeline.

Most modeling workflows do not need this package directly. If you are defining
ordinary materials, elements, loads, sections, or analyses, you can usually
ignore it. This guide is for the cases where *timing* matters: when the right
thing to do depends on whether the mesh has already been assembled, whether
partition ownership has been resolved, or whether an export pipeline has
started.

## The Idea In One Sentence

Femora emits lifecycle events, and advanced components subscribe to those
events when they need to react at exactly the right runtime stage.

## What Happens Under The Hood

At a high level, the runtime flow is:

1. a subsystem such as the assembler reaches a lifecycle boundary
2. it emits a [`FemoraEvent`][femora.components.event.event_bus.FemoraEvent]
3. the model-owned event bus dispatches payload data to subscribers
4. subscribers inspect that payload and react
5. the runtime continues to the next stage

In practice this means the event system is less about creating objects and more
about coordinating *when* an advanced object is allowed to inspect or modify
state.

## The Most Important Lifecycle Stages

The most important practical events are:

- `PRE_ASSEMBLE`
  Called before the final assembled mesh is built. Use this when something
  must be prepared before the assembly pipeline commits the final mesh state.

- `POST_ASSEMBLE`
  Called after the assembled mesh exists. This is the most important hook for
  advanced interfaces because the full model mesh can now be inspected.

- `RESOLVE_CORE_CONFLICTS`
  Called after assembly when partition/core ownership updates may require
  follow-up work.

- `PRE_EXPORT` / `POST_EXPORT`
  Called around export workflows. These are mainly useful for specialized
  export augmentation and compatibility layers.

## When You Should Use Events

Use the event system when the right behavior depends on lifecycle timing, for
example:

- generating extra interface mesh after the final assembled mesh exists
- pairing constrained and retained nodes after assembly
- creating constraints only after geometry relationships have been discovered
- reacting to partition-aware updates
- injecting custom export-time behavior

## When You Should Not Use Events

Do not use the event system as a replacement for ordinary model construction.
If a component can be created directly through a manager or configured entirely
at construction time, that is usually the better design.

## Minimal Subscription Example

```python
from femora.core.model import Model
from femora.components.event.event_bus import FemoraEvent

model = Model()

def on_post_assemble(**payload):
    assembled_mesh = payload.get("assembled_mesh")
    if assembled_mesh is not None:
        print(f"assembled cells: {assembled_mesh.n_cells}")

model.events.subscribe(FemoraEvent.POST_ASSEMBLE, on_post_assemble)
```

This kind of callback is appropriate for diagnostics, inspection, or small
advanced extensions.

## A More Realistic Femora Workflow

The more important use case is a model-owned advanced component.

For example, an interface component may:

1. subscribe to `POST_ASSEMBLE`
2. wait until the assembled mesh exists
3. inspect nearby cells or nodes
4. generate extra interface geometry or constraints
5. register those additions with the owning model

That is why the event package also documents lifecycle mixins such as:

- [`GeneratesMeshMixin`][femora.components.event.mixins.GeneratesMeshMixin]
- [`GeneratesNodesMixin`][femora.components.event.mixins.GeneratesNodesMixin]
- [`GeneratesConstraintsMixin`][femora.components.event.mixins.GeneratesConstraintsMixin]
- [`HandlesDecompositionMixin`][femora.components.event.mixins.HandlesDecompositionMixin]

Those mixins are not end-user features by themselves. They describe the kind
of lifecycle work an advanced component performs.

## Where To Read Next

- Read [`event bus`][femora.components.event.event_bus] for the actual event
  enum and subscription API.
- Read the lifecycle mixin pages when you are implementing or studying an
  advanced interface-like component.
""",
    ),
}

MANUAL_PACKAGE_PAGES: dict[str, dict] = {
    "femora.results": {
        "modules": {
            "result_set": {
                "nav": ("Reading Results", "Open Result Files"),
                "slug_parts": ("open-results", "index.md"),
                "title": "Open Result Files",
                "order": 0,
                "options": {"members": ["open_results"], "show_root_heading": False},
            },
        },
        "functions": {
            "register_reader": {
                "nav": ("Advanced", "Reader Extensions", "Register A Reader"),
                "slug_parts": ("register-reader", "index.md"),
                "title": "Register A Reader",
                "order": 9,
            },
        },
        "classes": {
            "ResultSet": {
                "nav": ("Reading Results", "ResultSet"),
                "slug_parts": ("ResultSet", "index.md"),
                "title": "ResultSet", "order": 1,
            },
            "PointSelection": {
                "nav": ("Reading Results", "PointSelection"),
                "slug_parts": ("PointSelection", "index.md"),
                "title": "PointSelection", "order": 2,
            },
            "BuildingResults": {
                "nav": ("Building Responses", "BuildingResults"),
                "slug_parts": ("BuildingResults", "index.md"),
                "title": "BuildingResults", "order": 3,
            },
            "ResultReader": {
                "nav": ("Advanced", "Reader Extensions", "ResultReader"),
                "slug_parts": ("ResultReader", "index.md"),
                "title": "ResultReader", "order": 7,
            },
            "ResultReaderRegistry": {
                "nav": ("Advanced", "Reader Extensions", "ResultReaderRegistry"),
                "slug_parts": ("ResultReaderRegistry", "index.md"),
                "title": "ResultReaderRegistry", "order": 8,
            },
            **{name: {
                "nav": ("Advanced", "Errors", name), "slug_parts": (name, "index.md"),
                "title": name, "order": 10 + index,
            } for index, (name, label) in enumerate([
                ("ResultError", "Result Error"),
                ("ResultFormatError", "Invalid Result Data"),
                ("UnsupportedResultOperation", "Unsupported Operation"),
            ])},
        },
    },
    "femora.results.visualization": {
        "classes": {
            "DeformationRenderer": {
                "nav": ("DeformationRenderer",),
                "slug_parts": ("DeformationRenderer", "index.md"),
                "title": "DeformationRenderer", "order": 0,
            },
        },
    },
    "femora.results.readers": {
        "classes": {
            "VTKHDFResultReader": {
                "nav": ("VTKHDFResultReader",),
                "slug_parts": ("VTKHDFResultReader", "index.md"),
                "title": "VTKHDFResultReader", "order": 0,
            },
        },
    },
    "femora.components.event": {
        "guide": {
            "nav": ("guide",),
            "slug_parts": ("guide", "index.md"),
            "title": "Event Guide",
            "order": 0,
        },
        "modules": {
            "event_bus": {
                "nav": ("event bus",),
                "slug_parts": ("event-bus", "index.md"),
                "title": "Event Bus",
                "order": 1,
                "options": {
                    "members": ["FemoraEvent", "ModelEventBus", "EventBus"],
                },
            },
        },
        "classes": {
            "GeneratesMeshMixin": {
                "nav": ("lifecycle mixins", "mesh generation"),
                "slug_parts": ("lifecycle-mixins", "mesh-generation", "index.md"),
                "title": "Mesh Generation Mixin",
                "order": 2,
            },
            "GeneratesNodesMixin": {
                "nav": ("lifecycle mixins", "node generation"),
                "slug_parts": ("lifecycle-mixins", "node-generation", "index.md"),
                "title": "Node Generation Mixin",
                "order": 3,
            },
            "GeneratesConstraintsMixin": {
                "nav": ("lifecycle mixins", "constraint generation"),
                "slug_parts": ("lifecycle-mixins", "constraint-generation", "index.md"),
                "title": "Constraint Generation Mixin",
                "order": 4,
            },
            "HandlesDecompositionMixin": {
                "nav": ("lifecycle mixins", "decomposition updates"),
                "slug_parts": ("lifecycle-mixins", "decomposition-updates", "index.md"),
                "title": "Decomposition Update Mixin",
                "order": 5,
            },
        },
    },
}

# Curated routes retain source-generated content and stable class-page paths.
JOB_CLASS_ROUTES = {
    "Workflow": ("workflows", "Workflow"),
    "Python": ("tasks", "Python"),
    "Command": ("tasks", "Command"),
    "OpenSees": ("tasks", "OpenSees"),
    "TaskContext": ("tasks", "TaskContext"),
    "RunResult": ("execute workflows", "RunResult"),
    "ProcessResult": ("execute workflows", "ProcessResult"),
    "TACC": ("execute workflows", "allocation backends", "TACC"),
    "TrackedJob": ("track jobs", "TrackedJob"),
    "JobRecord": ("track jobs", "JobRecord"),
    "JobRegistry": ("advanced", "tracking registry", "JobRegistry"),
    "WorkflowExecutionError": ("advanced", "errors", "WorkflowExecutionError"),
}
PLATFORM_CLASS_ROUTES = {
    "TACCPlatform": ("submit remotely", "TACCPlatform"),
    "TACCSettings": ("submit remotely", "TACCSettings"),
    "TACCValidator": ("submit remotely", "resource validation", "TACCValidator"),
    "QueueLimits": ("submit remotely", "resource validation", "QueueLimits"),
    "ValidationIssue": ("submit remotely", "resource validation", "ValidationIssue"),
    "ValidationReport": ("submit remotely", "resource validation", "ValidationReport"),
    "JobStatus": ("track jobs", "JobStatus"),
    "TACCJob": ("track jobs", "TACCJob"),
    "JobCleanupPlan": ("track jobs", "JobCleanupPlan"),
    "JobSummary": ("track jobs", "JobSummary"),
    **{name: ("advanced", "platform interfaces", name) for name in
       ("Platform", "PlatformValidator", "JobHandle", "JobDiscovery", "TACCSubmitter")},
    **{name: ("advanced", "errors", name) for name in
       ("SubmissionValidationError", "RemoteSubmissionError")},
}
for package, routes in (("femora.jobs", JOB_CLASS_ROUTES),
                        ("femora.jobs.platforms", PLATFORM_CLASS_ROUTES)):
    MANUAL_PACKAGE_PAGES[package] = {"classes": {
        name: {"nav": route, "slug_parts": (name, "index.md"),
               "title": name, "order": index}
        for index, (name, route) in enumerate(routes.items())
    }}
MANUAL_PACKAGE_PAGES["femora.jobs"]["modules"] = {
    name: {"nav": route, "slug_parts": (slug, "index.md"), "title": route[-1],
           "order": -10 + index, "options": {"members": members, "show_root_heading": False}}
    for index, (name, route, slug, members) in enumerate([
        ("runner", ("execute workflows", "run workflows"), "execute", ["execute"]),
        ("submission", ("submit remotely", "submit workflows"), "submit", ["submit"]),
        ("tracking", ("track jobs", "discover and reconnect"), "tracking",
         ["list_jobs", "add", "sync", "connect"]),
        ("bundle", ("bundles and replay",), "bundle", ["bundle", "replay"]),
    ])
}
MANUAL_PACKAGE_PAGES["femora"] = {
    "modules": {"runtime": {"nav": ("runtime", "overview"),
        "slug_parts": ("runtime", "index.md"), "title": "runtime overview", "order": 0,
        "options": {"members": ["setup", "run"], "show_root_heading": False}}},
    "classes": {name: {"nav": ("runtime", "errors", name) if name.endswith("Error")
                       else ("runtime", name),
        "slug_parts": ("runtime", name, "index.md"), "title": name, "order": 1}
        for name in ("RuntimeInfo", "RuntimeSetupError", "RuntimeExecutionError")},
}


def is_hidden_package_class(package_ident: str, class_name: str) -> bool:
    """Return whether a class should be omitted from generated package docs."""
    return class_name in HIDDEN_PACKAGE_CLASSES.get(package_ident, set())


def package_group_title(package_ident: str, module_name: str) -> str:
    """Return the display heading for one grouped package module section."""
    titles = GROUPED_PACKAGE_TITLES.get(package_ident, {})
    return titles.get(module_name, module_name.replace("_", " "))


def parse_element_manager_groups() -> dict[str, str]:
    """Return element module -> sub-manager group from the runtime API."""
    manager_files = {
        "beam": src_root / "femora" / "core" / "beam_element_manager.py",
        "brick": src_root / "femora" / "core" / "brick_element_manager.py",
        "quad": src_root / "femora" / "core" / "quad_element_manager.py",
        "special": src_root / "femora" / "core" / "special_element_manager.py",
    }
    grouped_modules: dict[str, str] = {}

    for group_name, path in manager_files.items():
        try:
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
        except Exception as exc:
            print(f"WARNING: Could not parse {path} for element grouping: {exc}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None or not node.module.startswith("femora.components.element."):
                continue
            module_name = node.module.rsplit(".", 1)[-1]
            grouped_modules[module_name] = group_name

    return grouped_modules


ELEMENT_MANAGER_GROUPS = parse_element_manager_groups()
ELEMENT_GROUP_TITLES = GROUPED_PACKAGE_TITLES["femora.components.element"]
GROUPED_PACKAGE_TITLES["femora.components.element"] = {
    module_name: ELEMENT_GROUP_TITLES.get(group_name, group_name)
    for module_name, group_name in ELEMENT_MANAGER_GROUPS.items()
}


def write_package_index(
    doc_path: Path,
    ident: str,
    title: str,
    description: str,
    class_links: list[tuple[str, str, str]],
    edit_path: Path,
) -> None:
    """Write a minimal package landing page with links to class pages."""
    with mkdocs_gen_files.open(doc_path, "w") as fd:
        front_matter, description_body = split_front_matter(description)
        if front_matter:
            fd.write(f"{front_matter}\n\n")
        if front_matter and ident.startswith(("femora.results", "femora.jobs")):
            for line in front_matter.splitlines():
                if line.startswith("title:"):
                    title = line.partition(":")[2].strip()
        fd.write(f"# {title}\n\n")
        if description_body:
            fd.write(f"{description_body}\n\n")
        if class_links and ident != "femora.results" and not ident.startswith("femora.jobs"):
            if ident in GROUPED_PACKAGE_TITLES:
                grouped: dict[str, list[tuple[str, str]]] = {}
                for module_name, class_name, href in class_links:
                    grouped.setdefault(module_name, []).append((class_name, href))

                preferred_order = list(GROUPED_PACKAGE_TITLES[ident].keys())
                ordered_modules = [
                    module_name for module_name in preferred_order if module_name in grouped
                ]
                ordered_modules.extend(
                    sorted(module_name for module_name in grouped if module_name not in preferred_order)
                )

                for module_name in ordered_modules:
                    fd.write(f"## {package_group_title(ident, module_name)}\n\n")
                    for class_name, href in grouped[module_name]:
                        fd.write(f"- [{class_name}]({href})\n")
                    fd.write("\n")
            else:
                fd.write("Classes in this package:\n\n")
                for _module_name, class_name, href in class_links:
                    fd.write(f"- [{class_name}]({href})\n")
    mkdocs_gen_files.set_edit_path(doc_path, edit_path)


def write_manual_event_index(doc_path: Path, description: str, edit_path: Path) -> None:
    """Write the curated landing page for the event package."""
    with mkdocs_gen_files.open(doc_path, "w") as fd:
        front_matter, description_body = split_front_matter(description)
        if front_matter:
            fd.write(f"{front_matter}\n\n")
        fd.write("# event\n\n")
        if description_body:
            fd.write(f"{description_body}\n\n")
        fd.write("## Start here\n\n")
        fd.write("- [guide](guide/)\n")
        fd.write("- [event bus](event-bus/)\n\n")
        fd.write("## lifecycle mixins\n\n")
        fd.write("- [mesh generation](lifecycle-mixins/mesh-generation/)\n")
        fd.write("- [node generation](lifecycle-mixins/node-generation/)\n")
        fd.write("- [constraint generation](lifecycle-mixins/constraint-generation/)\n")
        fd.write("- [decomposition updates](lifecycle-mixins/decomposition-updates/)\n")
    mkdocs_gen_files.set_edit_path(doc_path, edit_path)


def write_class_page(
    doc_path: Path,
    ident: str,
    edit_path: Path,
    doc_controls: dict | None = None,
    page_title: str | None = None,
) -> None:
    """Write one page for an individual public class."""
    with mkdocs_gen_files.open(doc_path, "w") as fd:
        if page_title:
            fd.write(f"---\ntitle: {page_title}\n---\n\n")
        fd.write(f"::: {ident}\n")
        effective_doc_controls = dict(doc_controls or {})
        if effective_doc_controls.get("members") == ["__init__"]:
            effective_doc_controls.setdefault("show_category_heading", False)
        if effective_doc_controls:
            fd.write("    options:\n")
            for key, value in effective_doc_controls.items():
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                    fd.write(f"      {key}: {rendered}\n")
                elif isinstance(value, list):
                    if value:
                        fd.write(f"      {key}:\n")
                        for item in value:
                            fd.write(f"        - {item}\n")
                    else:
                        fd.write(f"      {key}: []\n")
                else:
                    fd.write(f"      {key}: {value}\n")
    mkdocs_gen_files.set_edit_path(doc_path, edit_path)


def write_module_page(
    doc_path: Path,
    ident: str,
    edit_path: Path,
    page_title: str | None = None,
    options: dict | None = None,
) -> None:
    """Write one page for a module-level API reference."""
    with mkdocs_gen_files.open(doc_path, "w") as fd:
        if page_title:
            fd.write(f"---\ntitle: {page_title}\n---\n\n")
        fd.write(f"::: {ident}\n")
        if options:
            fd.write("    options:\n")
            for key, value in options.items():
                if isinstance(value, bool):
                    rendered = "true" if value else "false"
                    fd.write(f"      {key}: {rendered}\n")
                elif isinstance(value, list):
                    if value:
                        fd.write(f"      {key}:\n")
                        for item in value:
                            fd.write(f"        - {item}\n")
                    else:
                        fd.write(f"      {key}: []\n")
                else:
                    fd.write(f"      {key}: {value}\n")
    mkdocs_gen_files.set_edit_path(doc_path, edit_path)


files = sorted(src_root.rglob("*.py"))
print(f"DEBUG: Found {len(files)} python files in {src_root}")

package_infos: list[tuple[tuple[str, ...], Path, str]] = []
package_classes: dict[tuple[str, ...], list[tuple[str, str]]] = {}
manual_package_nav_entries: dict[str, list[tuple[int, tuple[str, ...], str]]] = {}
grouped_package_nav_entries: dict[str, list[tuple[int, tuple[str, ...], str]]] = {}

command_page = Path("reference/jobs/command-line/index.md")
nav[("jobs", "command line")] = command_page.relative_to("reference").as_posix()
write_module_page(command_page, "femora.jobs.__main__", src_root / "femora/jobs/__main__.py",
                  "command line", {"members": [], "show_root_heading": False})

for path in files:
    module_path = path.relative_to(src_root).with_suffix("")
    parts = tuple(module_path.parts)

    if should_skip(parts):
        continue

    if parts[-1] == "__init__":
        nav_parts = parts[:-1]
        if not nav_parts:
            continue
        if nav_parts == ("femora",):
            continue
        package_infos.append((nav_parts, path, parse_module_docstring(path)))
        continue

    class_entries = parse_public_classes(path)

    # Explicit module pages can coexist with class pages (e.g. open_results
    # beside ResultSet). Previously the class branch silently skipped them.
    package_ident = ".".join(parts[:-1])
    manual_package = MANUAL_PACKAGE_PAGES.get(package_ident)
    mixed_module_page = bool(class_entries and manual_package
                             and parts[-1] in manual_package.get("modules", {}))
    if mixed_module_page:
        page_config = manual_package["modules"][parts[-1]]
        doc_path = Path("reference", *doc_parts(parts[:-1]), *page_config["slug_parts"])
        manual_package_nav_entries.setdefault(package_ident, []).append((
            page_config["order"], display_parts(parts[:-1]) + page_config["nav"],
            doc_path.relative_to("reference").as_posix(),
        ))
        write_module_page(doc_path, ".".join(parts), path,
                          page_config["title"], page_config.get("options"))

    # Keep the older class-page style, but flatten the navigation so packages
    # list classes directly instead of showing a file name before the class.
    if class_entries:
        package_ident = ".".join(parts[:-1])
        visible_class_entries = [
            (class_name, doc_controls)
            for class_name, doc_controls in class_entries
            if not is_hidden_package_class(package_ident, class_name)
        ]
        package_classes.setdefault(parts[:-1], []).extend(
            (parts[-1], class_name) for class_name, _ in visible_class_entries
        )
        for class_name, doc_controls in visible_class_entries:
            manual_package = MANUAL_PACKAGE_PAGES.get(package_ident)
            if manual_package and class_name in manual_package.get("classes", {}):
                page_config = manual_package["classes"][class_name]
                class_doc_path = Path("reference", *doc_parts(parts[:-1]), *page_config["slug_parts"])
                manual_package_nav_entries.setdefault(package_ident, []).append(
                    (
                        page_config["order"],
                        display_parts(parts[:-1]) + page_config["nav"],
                        class_doc_path.relative_to("reference").as_posix(),
                    )
                )
                write_class_page(
                    class_doc_path,
                    ".".join(parts) + "." + class_name,
                    path,
                    doc_controls,
                    page_config["title"],
                )
            else:
                class_doc_path = Path("reference", *doc_parts(parts[:-1]), class_name, "index.md")
                if package_ident in GROUPED_PACKAGE_TITLES:
                    grouped_package_nav_entries.setdefault(package_ident, []).append(
                        (
                            list(GROUPED_PACKAGE_TITLES[package_ident].keys()).index(parts[-1])
                            if parts[-1] in GROUPED_PACKAGE_TITLES[package_ident]
                            else len(GROUPED_PACKAGE_TITLES[package_ident]),
                            display_parts(parts[:-1])
                            + (package_group_title(package_ident, parts[-1]), class_name),
                            class_doc_path.relative_to("reference").as_posix(),
                        )
                    )
                else:
                    nav[display_parts(parts[:-1]) + (class_name,)] = class_doc_path.relative_to(
                        "reference"
                    ).as_posix()
                write_class_page(class_doc_path, ".".join(parts) + "." + class_name, path, doc_controls)
    else:
        package_ident = ".".join(parts[:-1])
        manual_package = MANUAL_PACKAGE_PAGES.get(package_ident)
        if manual_package and parts[-1] in manual_package.get("modules", {}):
            page_config = manual_package["modules"][parts[-1]]
            doc_path = Path("reference", *doc_parts(parts[:-1]), *page_config["slug_parts"])
            manual_package_nav_entries.setdefault(package_ident, []).append(
                (
                    page_config["order"],
                    display_parts(parts[:-1]) + page_config["nav"],
                    doc_path.relative_to("reference").as_posix(),
                )
            )
            write_module_page(
                doc_path,
                ".".join(parts),
                path,
                page_config["title"],
                page_config.get("options"),
            )
        else:
            doc_path = Path("reference", *doc_parts(parts)).with_suffix(".md")
            nav[display_parts(parts)] = doc_path.relative_to("reference").as_posix()
            write_module_page(doc_path, ".".join(parts), path)

for nav_parts, path, description in sorted(package_infos, key=package_sort_key):
    doc_path = Path("reference", *doc_parts(nav_parts), "index.md")
    landing_nav = display_parts(nav_parts)
    if nav_parts == ("femora", "results"):
        landing_nav += ("Overview",)
    elif nav_parts == ("femora", "jobs"):
        landing_nav += ("overview",)
    elif nav_parts == ("femora", "jobs", "platforms"):
        landing_nav = ("jobs", "advanced", "platform interfaces", "overview")
    nav[landing_nav] = doc_path.relative_to("reference").as_posix()
    class_links = [
        (module_name, class_name, f"{class_name}/")
        for module_name, class_name in package_classes.get(nav_parts, [])
    ]
    package_ident = ".".join(nav_parts)
    for function_name, page_config in MANUAL_PACKAGE_PAGES.get(package_ident, {}).get("functions", {}).items():
        function_path = Path("reference", *doc_parts(nav_parts), *page_config["slug_parts"])
        manual_package_nav_entries.setdefault(package_ident, []).append((
            page_config["order"], display_parts(nav_parts) + page_config["nav"],
            function_path.relative_to("reference").as_posix(),
        ))
        write_module_page(function_path, f"{package_ident}.{function_name}", path,
                          page_config["title"])
    if package_ident == "femora.components.event":
        write_manual_event_index(doc_path, description, path)
    else:
        write_package_index(
            doc_path=doc_path,
            ident=package_ident,
            title=nav_parts[-1],
            description=description,
            class_links=class_links,
            edit_path=path,
        )
    if package_ident in PACKAGE_GUIDES:
        guide_slug, guide_body = PACKAGE_GUIDES[package_ident]
        manual_package = MANUAL_PACKAGE_PAGES.get(package_ident)
        if manual_package:
            guide_config = manual_package["guide"]
            guide_doc_path = Path("reference", *doc_parts(nav_parts), *guide_config["slug_parts"])
            manual_package_nav_entries.setdefault(package_ident, []).append(
                (
                    guide_config["order"],
                    display_parts(nav_parts) + guide_config["nav"],
                    guide_doc_path.relative_to("reference").as_posix(),
                )
            )
        else:
            guide_doc_path = Path("reference", *doc_parts(nav_parts), guide_slug, "index.md")
            nav[display_parts(nav_parts) + ("guide",)] = guide_doc_path.relative_to("reference").as_posix()
        with mkdocs_gen_files.open(guide_doc_path, "w") as fd:
            fd.write(guide_body)
        mkdocs_gen_files.set_edit_path(guide_doc_path, path)

for package_ident, entries in manual_package_nav_entries.items():
    del package_ident
    for _order, nav_parts, rel_path in sorted(entries, key=lambda item: item[0]):
        nav[nav_parts] = rel_path

for package_ident, entries in grouped_package_nav_entries.items():
    del package_ident
    for _order, nav_parts, rel_path in sorted(entries, key=lambda item: (item[0], item[1])):
        nav[nav_parts] = rel_path

def order_results_navigation(source_nav):
    """Order Results by user task, keeping other API navigation unchanged."""
    entries = []
    stack = []
    for item in source_nav.items():
        stack = stack[:item.level] + [item.title]
        if item.filename is not None:
            entries.append((tuple(stack), item.filename))
    heading = TOP_LEVEL_LABELS["results"]
    results = [(keys, path) for keys, path in entries if keys[0] == heading]
    order = {"Overview": 0, "Reading Results": 1, "Building Responses": 2,
             "Visualization": 3, "Advanced": 4}
    advanced_order = {"File Readers": 0, "Reader Extensions": 1, "Errors": 2}
    results.sort(key=lambda item: (
        order.get(item[0][1], 99),
        advanced_order.get(item[0][2], 99)
        if len(item[0]) > 2 and item[0][1] == "Advanced" else 0,
    ))
    ordered = mkdocs_gen_files.Nav()
    inserted = False
    for keys, path in entries:
        if keys[0] != heading:
            ordered[keys] = path
        elif not inserted:
            for result_keys, result_path in results:
                ordered[result_keys] = result_path
            inserted = True
    return ordered


nav = order_results_navigation(nav)


def order_jobs_navigation(source_nav):
    """Keep the Jobs lifecycle readable without changing other reference sections."""
    entries, stack = [], []
    for item in source_nav.items():
        stack = stack[:item.level] + [item.title]
        if item.filename is not None:
            entries.append((tuple(stack), item.filename))
    order = {name: index for index, name in enumerate((
        "overview", "tasks", "workflows", "execute workflows", "submit remotely",
        "track jobs", "bundles and replay", "command line", "advanced"))}
    jobs = [(keys, path) for keys, path in entries if keys[0] == "jobs"]
    jobs.sort(key=lambda entry: order.get(entry[0][1], 99))
    ordered, inserted = mkdocs_gen_files.Nav(), False
    for keys, path in entries:
        if keys[0] != "jobs":
            ordered[keys] = path
        elif not inserted:
            for job_keys, job_path in jobs:
                ordered[job_keys] = job_path
            inserted = True
    return ordered


nav = order_jobs_navigation(nav)


def order_reference_navigation(source_nav):
    """Place execution APIs after modeling/support APIs and before results."""
    entries, stack = [], []
    for item in source_nav.items():
        stack = stack[:item.level] + [item.title]
        if item.filename is not None:
            entries.append((tuple(stack), item.filename))
    order = {name: index for index, name in enumerate((
        "components", "core", "io", "tools", "jobs", "runtime",
        TOP_LEVEL_LABELS["results"]))}
    entries.sort(key=lambda item: order.get(item[0][0], len(order)))
    ordered = mkdocs_gen_files.Nav()
    for keys, path in entries:
        ordered[keys] = path
    return ordered


nav = order_reference_navigation(nav)
with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.write("- [Overview](index.md)\n")
    nav_file.writelines(nav.build_literate_nav())
