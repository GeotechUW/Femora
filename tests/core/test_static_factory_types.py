"""Optional Pyright gate for editor-visible Core API contracts."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def test_core_factory_static_types():
    root = Path(__file__).resolve().parents[2]
    entrypoint = os.environ.get("FEMORA_PYRIGHT_JS")
    if entrypoint:
        node = shutil.which("node")
        if not node:
            pytest.skip("Node is required with FEMORA_PYRIGHT_JS")
        command = [node, entrypoint]
    else:
        executable = shutil.which("pyright")
        if not executable:
            pytest.skip("Install Pyright or set FEMORA_PYRIGHT_JS to its index.js")
        command = [executable]
    result = subprocess.run(
        command
        + [
            "--project",
            str(root / "tests/typing/pyrightconfig.json"),
            "--pythonpath",
            sys.executable,
            "--outputjson",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    errors = [item for item in report["generalDiagnostics"] if item["severity"] == "error"]
    assert len(errors) == 6, errors
    assert all(Path(item["file"]).name == "core_factories_invalid.py" for item in errors), errors
    assert {item["range"]["start"]["line"] for item in errors} == set(range(6, 12)), errors
    assert not any(item["severity"] == "warning" for item in report["generalDiagnostics"])
