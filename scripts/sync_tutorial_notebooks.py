# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Generate committed tutorial notebooks from canonical percent-format scripts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import jupytext
import nbformat


ROOT = Path(__file__).resolve().parents[1]
TUTORIALS = (
    ROOT / "examples" / "tutorials" / "elastic_cantilever.py",
)


def _render_notebook(source: Path) -> str:
    notebook = jupytext.read(source, fmt="py:percent")
    if (
        notebook.cells
        and notebook.cells[0].cell_type == "code"
        and notebook.cells[0].source.startswith("# ===")
    ):
        notebook.cells.pop(0)
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
    for source in TUTORIALS:
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
        print("Tutorial notebooks are out of date:", file=sys.stderr)
        for path in stale:
            print(f"  {path.relative_to(ROOT)}", file=sys.stderr)
        print(
            "Run: python scripts/sync_tutorial_notebooks.py",
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
