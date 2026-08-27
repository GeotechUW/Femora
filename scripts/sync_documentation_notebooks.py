# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate documentation notebooks from canonical percent-format scripts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Optional

import jupytext
import nbformat


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (
    ROOT / "examples" / "tutorials",
    ROOT / "examples" / "site_response",
)
COLAB_INPUT_PREFIX = "# femora-colab-input:"
COLAB_ENV_PREFIX = "# femora-colab-env:"
COLAB_SOURCE_PREFIX = "# femora-colab-source:"
POSTPROCESS_PREFIX = "# femora-postprocess:"

COLAB_SETUP_MARKDOWN = """## Configure the Colab runtime

This generated cell installs Femora and configures the packaged OpenSees runtime.
It is intentionally not part of the canonical local Python example.
"""

COLAB_SETUP_CODE = """import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlretrieve

if importlib.util.find_spec("femora") is None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "https://github.com/GeotechUW/Femora/archive/refs/heads/main.zip",
        ]
    )

import femora as fm

runtime = fm.runtime.setup("colab")
print(f"OpenSees {runtime.version or 'runtime'} configured at {runtime.executable}")
"""


def _discover_sources() -> tuple[Path, ...]:
    """Return canonical documentation scripts in deterministic order."""
    sources = []
    for directory in SOURCE_DIRS:
        sources.extend(
            path
            for path in sorted(directory.glob("*.py"))
            if not path.name.startswith("_")
            and not path.stem.endswith("_postprocess")
        )
    return tuple(sources)


def _colab_inputs(source: Path) -> tuple[str, ...]:
    """Read repository-relative Colab input declarations from a source file."""
    inputs = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith(COLAB_INPUT_PREFIX):
            inputs.append(line.removeprefix(COLAB_INPUT_PREFIX).strip())
    return tuple(inputs)


def _colab_environment(source: Path) -> dict[str, str]:
    """Read Colab-only environment assignments from a canonical source."""
    environment = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith(COLAB_ENV_PREFIX):
            continue
        declaration = line.removeprefix(COLAB_ENV_PREFIX).strip()
        key, separator, value = declaration.partition("=")
        if not separator or not key.strip():
            raise ValueError(
                f"Invalid Colab environment declaration in {source}: {declaration}"
            )
        environment[key.strip()] = value.strip()
    return environment


def _repository_source(owner: Path, declaration: str) -> Path:
    """Resolve and validate a repository-relative source declaration."""
    resolved = (ROOT / declaration).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(
            f"Source declared by {owner} must remain inside the repository: {resolved}"
        ) from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"Source declared by {owner} was not found: {resolved}")
    return resolved


def _additional_colab_sources(source: Path) -> tuple[Path, ...]:
    """Resolve transitive source dependencies required by a Colab companion."""
    discovered = []
    visited = {source.resolve()}
    pending = [source]
    while pending:
        current = pending.pop(0)
        for line in current.read_text(encoding="utf-8").splitlines():
            if not line.startswith(COLAB_SOURCE_PREFIX):
                continue
            declaration = line.removeprefix(COLAB_SOURCE_PREFIX).strip()
            dependency = _repository_source(current, declaration)
            if dependency in visited:
                continue
            visited.add(dependency)
            discovered.append(dependency)
            pending.append(dependency)
    return tuple(discovered)


def _postprocess_source(source: Path) -> Optional[Path]:
    """Return the declared companion post-processing source, if present."""
    declarations = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith(POSTPROCESS_PREFIX):
            declarations.append(line.removeprefix(POSTPROCESS_PREFIX).strip())
    if len(declarations) > 1:
        raise ValueError(f"{source} declares more than one post-processing file")
    if not declarations:
        return None

    return _repository_source(source, declarations[0])


def _colab_setup_code(source: Path) -> str:
    inputs = _colab_inputs(source)
    environment = _colab_environment(source)
    postprocess_source = _postprocess_source(source)
    additional_sources = list(_additional_colab_sources(source))
    if postprocess_source is not None:
        additional_sources.insert(0, postprocess_source)
        additional_sources.extend(_additional_colab_sources(postprocess_source))
    additional_sources = list(dict.fromkeys(additional_sources))

    if not inputs and not environment and not additional_sources:
        return COLAB_SETUP_CODE

    setup = COLAB_SETUP_CODE
    if environment:
        setup += f"""

colab_environment = {environment!r}
os.environ.update(colab_environment)
print(f"Configured Colab environment: {{', '.join(colab_environment)}}")
"""
    if inputs:
        setup += f"""

colab_inputs = {list(inputs)!r}
input_root = Path("/content/femora_inputs")
for repository_path in colab_inputs:
    relative_path = Path(repository_path).relative_to("examples/inputs")
    destination = input_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/GeotechUW/Femora/main/{{repository_path}}"
    urlretrieve(url, destination)

motion_directory = input_root / "motions"
if motion_directory.exists():
    os.environ["FEMORA_MOTIONS_DIR"] = str(motion_directory)
print(f"Downloaded {{len(colab_inputs)}} example input files")
"""
    if additional_sources:
        repository_paths = [path.relative_to(ROOT).as_posix() for path in additional_sources]
        setup += f"""

colab_sources = {repository_paths!r}
for repository_path in colab_sources:
    destination = Path("/content") / repository_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = "https://raw.githubusercontent.com/GeotechUW/Femora/main/" + repository_path
    urlretrieve(url, destination)
print(f"Downloaded {{len(colab_sources)}} companion source files")
"""
    return setup


def _postprocess_cells(source: Path) -> list:
    """Build final result cells backed by a declared companion module."""
    companion = _postprocess_source(source)
    if companion is None:
        return []

    module = companion.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
    return [
        nbformat.v4.new_markdown_cell(
            """## Post-process the results

Open the recorded response through Femora's results API, generate the example's
standard plots, and display them directly in the notebook.
""",
            metadata={"tags": ["post-processing"]},
        ),
        nbformat.v4.new_code_cell(
            f"""from IPython.display import Image, display
from {module} import generate_results

result_files = generate_results()
for result_file in result_files:
    display(Image(filename=str(result_file)))
""",
            metadata={"tags": ["post-processing"]},
        ),
        nbformat.v4.new_markdown_cell(
            """## Optional response animation

Movie rendering is intentionally opt-in because it can take substantially
longer than the analysis and static result plots.
""",
            metadata={"tags": ["post-processing", "optional-animation"]},
        ),
        nbformat.v4.new_code_cell(
            f"""from IPython.display import Video, display
from {module} import generate_animations

GENERATE_RESPONSE_ANIMATION = False
if GENERATE_RESPONSE_ANIMATION:
    animation_files = generate_animations()
    for animation_file in animation_files:
        display(Video(filename=str(animation_file), embed=True))
else:
    print("Set GENERATE_RESPONSE_ANIMATION = True to render the movie.")
""",
            metadata={"tags": ["post-processing", "optional-animation"]},
        ),
    ]


def _render_notebook(source: Path) -> str:
    notebook = jupytext.read(source, fmt="py:percent")
    if (
        notebook.cells
        and notebook.cells[0].cell_type == "code"
        and notebook.cells[0].source.startswith("# ===")
    ):
        notebook.cells.pop(0)
    insert_at = 1 if notebook.cells and notebook.cells[0].cell_type == "markdown" else 0
    notebook.cells[insert_at:insert_at] = [
        nbformat.v4.new_markdown_cell(
            COLAB_SETUP_MARKDOWN,
            metadata={"tags": ["colab-bootstrap"]},
        ),
        nbformat.v4.new_code_cell(
            _colab_setup_code(source),
            metadata={"tags": ["colab-bootstrap"]},
        ),
    ]
    notebook.cells.extend(_postprocess_cells(source))
    notebook.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook.metadata["language_info"] = {"name": "python"}
    notebook.metadata["femora"] = {
        "copyright": "Copyright 2026 Amin Pakzad and Pedro Arduino",
        "developed_at": "UW Geotechnical Lab",
        "license": "Apache-2.0",
    }
    notebook.metadata.pop("jupytext", None)
    for index, cell in enumerate(notebook.cells):
        identity = f"{index}\0{cell.cell_type}\0{cell.source}".encode("utf-8")
        cell.id = hashlib.sha256(identity).hexdigest()[:12]
        if cell.cell_type == "code":
            cell.execution_count = None
            cell.outputs = []
    return nbformat.writes(notebook, version=4)


def sync(check: bool) -> int:
    stale: list[Path] = []
    sources = _discover_sources()
    if not sources:
        print("No documentation notebook sources found", file=sys.stderr)
        return 1

    for source in sources:
        destination = source.with_suffix(".ipynb")
        rendered = _render_notebook(source)
        current = destination.read_text(encoding="utf-8") if destination.exists() else None
        if current == rendered:
            continue
        if check:
            stale.append(destination)
        else:
            with destination.open("w", encoding="utf-8", newline="\n") as output:
                output.write(rendered)
            print(f"Generated {destination.relative_to(ROOT)}")

    if stale:
        print("Documentation notebooks are out of date:", file=sys.stderr)
        for path in stale:
            print(f"  {path.relative_to(ROOT)}", file=sys.stderr)
        print(
            "Run: python scripts/sync_documentation_notebooks.py",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when a committed notebook differs from its Python source.",
    )
    return sync(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
