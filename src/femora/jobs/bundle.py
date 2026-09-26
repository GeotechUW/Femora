"""Package a workflow source and inputs for execution in another workspace."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zipfile import ZipFile

from .runner import RunResult, execute
from .workflow import Workflow


_FORMAT_VERSION = 1


def _safe_relative(value: str | Path) -> str:
    raw = str(value)
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not raw
        or path.is_absolute()
        or PureWindowsPath(raw).drive
        or ".." in path.parts
        or path == PurePosixPath(".")
    ):
        raise ValueError(f"bundle file path must stay relative to the source: {raw}")
    return path.as_posix()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle(
    *,
    source: str | Path,
    destination: str | Path,
    inputs: Mapping[str, Any],
    files: Sequence[str | Path] = (),
    entrypoint: str = "build_workflow",
    overwrite: bool = False,
) -> Path:
    """Write a zip containing one workflow Python file and declared data files.

    ``source`` must define an ``entrypoint`` returning a Workflow. It may take
    an ``inputs`` parameter to choose stages and tasks from the saved inputs.
    Inputs must be JSON-serializable. Data file paths are relative to the source
    file's directory and appear at the same relative paths in the run workspace.
    The bundle does not include Python packages or the OpenSees executable.
    """
    script = Path(source).expanduser().resolve()
    if not script.is_file() or script.suffix != ".py":
        raise ValueError(f"workflow source must be a Python file: {script}")
    if not isinstance(inputs, Mapping):
        raise TypeError("bundle inputs must be a mapping")
    if not entrypoint.isidentifier():
        raise ValueError("entrypoint must be a Python identifier")
    input_json = json.dumps(dict(inputs), indent=2, allow_nan=False) + "\n"

    root = script.parent
    data: dict[str, Path] = {}
    for value in files:
        relative = _safe_relative(value)
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"bundle data file was not found inside {root}: {value}")
        if relative in data:
            raise ValueError(f"duplicate bundle data file: {relative}")
        data[relative] = path

    metadata = {
        "format_version": _FORMAT_VERSION,
        "entrypoint": entrypoint,
        "source_sha256": _hash_file(script),
        "files": {name: _hash_file(path) for name, path in data.items()},
    }
    target = Path(destination).expanduser().resolve()
    if target == script:
        raise ValueError("bundle destination must differ from the workflow source")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(f"bundle already exists: {target}")
    with ZipFile(target, "w") as archive:
        archive.write(script, "workflow.py")
        archive.writestr("inputs.json", input_json)
        archive.writestr("bundle.json", json.dumps(metadata, indent=2) + "\n")
        for name, path in data.items():
            archive.write(path, f"data/{name}")
    return target


def replay(
    package: str | Path,
    *,
    workspace: str | Path,
    cores: int | None = None,
) -> RunResult:
    """Run a trusted bundle locally in a fresh workspace.

    Bundle source is executable Python. Do not replay bundles from untrusted
    origins. This operation does not install dependencies or configure OpenSees.
    """
    root = Path(workspace).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"replay workspace must be empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    with ZipFile(Path(package).expanduser().resolve()) as archive:
        metadata = json.loads(archive.read("bundle.json"))
        if metadata.get("format_version") != _FORMAT_VERSION:
            raise ValueError("unsupported workflow bundle format")
        entrypoint = metadata.get("entrypoint")
        if not isinstance(entrypoint, str) or not entrypoint.isidentifier():
            raise ValueError("invalid workflow entrypoint in bundle")
        inputs = json.loads(archive.read("inputs.json"))
        if not isinstance(inputs, dict):
            raise ValueError("bundle inputs must be a JSON object")
        files = metadata.get("files")
        if not isinstance(files, dict):
            raise ValueError("invalid bundle data file list")

        with TemporaryDirectory(prefix="femora_bundle_") as temporary:
            module_name = f"femora_workflow_{uuid4().hex}"
            script = Path(temporary) / f"{module_name}.py"
            with archive.open("workflow.py") as source_stream, script.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
            if _hash_file(script) != metadata.get("source_sha256"):
                raise ValueError("workflow source checksum does not match the bundle")

            for raw_name, checksum in files.items():
                name = _safe_relative(raw_name)
                if name != raw_name or not isinstance(checksum, str):
                    raise ValueError("invalid bundle data file entry")
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(f"data/{name}") as source_stream, target.open("xb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream)
                if _hash_file(target) != checksum:
                    raise ValueError(f"bundle data file checksum does not match: {name}")

            sys.path.insert(0, temporary)
            try:
                importlib.invalidate_caches()
                module = importlib.import_module(module_name)
                factory = getattr(module, entrypoint, None)
                if not callable(factory):
                    raise ValueError(f"bundle entrypoint is not callable: {entrypoint}")
                workflow = (
                    factory(inputs=inputs)
                    if "inputs" in inspect.signature(factory).parameters
                    else factory()
                )
                if not isinstance(workflow, Workflow):
                    raise TypeError("bundle entrypoint must return an fm.Workflow")
                return execute(workflow, workspace=root, inputs=inputs, cores=cores)
            finally:
                sys.modules.pop(module_name, None)
                sys.path.remove(temporary)


__all__ = ["bundle", "replay"]
