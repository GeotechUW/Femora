# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Configure external solver runtimes used by Femora."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Optional, Union
from urllib.request import urlopen


DEFAULT_COLAB_RELEASE_URL = (
    "https://github.com/amnp95/OpenSees/releases/download/opensees-colab-latest"
)
DEFAULT_COLAB_ARCHIVE = "OpenSees-Colab-linux-x86_64.tar.gz"
_RUNTIME_MARKER = "FEMORA_OPENSEES_RUNTIME_OK"


class RuntimeSetupError(RuntimeError):
    """Raised when Femora cannot configure or validate an OpenSees runtime."""


@dataclass(frozen=True)
class RuntimeInfo:
    """Resolved OpenSees runtime configuration.

    Attributes:
        environment: Normalized environment name, either ``"colab"`` or
            ``"local"``.
        executable: Absolute path to the OpenSees launcher or executable.
        version: Version parsed from the OpenSees startup banner, when present.
        tcl_library: Bundled Tcl library path for the Colab runtime, otherwise
            ``None``.
        installed: Whether this call downloaded and installed the runtime.
    """

    environment: str
    executable: Path
    version: Optional[str]
    tcl_library: Optional[Path]
    installed: bool


def _is_colab() -> bool:
    if "COLAB_RELEASE_TAG" in os.environ:
        return True
    try:
        return importlib.util.find_spec("google.colab") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _normalize_environment(environment: str) -> str:
    normalized = environment.strip().lower().replace("-", "_")
    if normalized == "auto":
        return "colab" if _is_colab() else "local"
    if normalized in {"colab", "google_colab"}:
        return "colab"
    if normalized == "local":
        return "local"
    raise ValueError(
        "environment must be 'auto', 'local', 'colab', or 'google_colab'"
    )


def _download(url: str, destination: Path, timeout: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with urlopen(url, timeout=timeout) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_archive_safely(archive: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise RuntimeSetupError(
                    f"Runtime archive contains an unsupported link: {member.name}"
                )
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination_root)
            except ValueError as exc:
                raise RuntimeSetupError(
                    f"Runtime archive contains an unsafe path: {member.name}"
                ) from exc
        package.extractall(destination, members=members)


def _probe_runtime(executable: Path) -> Optional[str]:
    with tempfile.TemporaryDirectory(prefix="femora-runtime-check-") as tmp_dir:
        script = Path(tmp_dir) / "check.tcl"
        script.write_text(f'puts "{_RUNTIME_MARKER}"\nexit\n', encoding="ascii")
        try:
            completed = subprocess.run(
                [str(executable), str(script)],
                cwd=tmp_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeSetupError(
                f"Unable to start the OpenSees runtime at '{executable}'"
            ) from exc

    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0 or _RUNTIME_MARKER not in output:
        details = "\n".join(line for line in output.splitlines() if line.strip())
        raise RuntimeSetupError(
            f"OpenSees runtime validation failed at '{executable}'.\n{details}"
        )

    match = re.search(r"\bVersion\s+([^\s]+)", output, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _setup_local(executable: Optional[Union[str, Path]]) -> RuntimeInfo:
    configured = executable or os.environ.get("FEMORA_OPENSEES")
    resolved = Path(configured).expanduser() if configured else None
    if resolved is None:
        discovered = shutil.which("OpenSees") or shutil.which("OpenSees.exe")
        resolved = Path(discovered) if discovered else None
    if resolved is None or not resolved.is_file():
        raise RuntimeSetupError(
            "OpenSees was not found. Pass executable=..., set FEMORA_OPENSEES, "
            "or add OpenSees to PATH."
        )

    resolved = resolved.resolve()
    version = _probe_runtime(resolved)
    os.environ["FEMORA_OPENSEES"] = str(resolved)
    return RuntimeInfo("local", resolved, version, None, False)


def _setup_colab(
    executable: Optional[Union[str, Path]],
    install_dir: Optional[Union[str, Path]],
    release_url: str,
    force: bool,
    timeout: float,
) -> RuntimeInfo:
    root = Path(install_dir or "/content/opensees").expanduser().resolve()
    launcher = Path(executable).expanduser().resolve() if executable else root / "OpenSees"
    installed = False

    if force or not launcher.is_file():
        cache = root.parent / ".cache" / "femora"
        archive = cache / DEFAULT_COLAB_ARCHIVE
        checksum = cache / f"{DEFAULT_COLAB_ARCHIVE}.sha256"
        base_url = release_url.rstrip("/")

        _download(f"{base_url}/{checksum.name}", checksum, timeout)
        expected = checksum.read_text(encoding="ascii").split()[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeSetupError("The published OpenSees checksum is invalid")

        if force or not archive.is_file() or _sha256(archive) != expected:
            _download(f"{base_url}/{archive.name}", archive, timeout)
        actual = _sha256(archive)
        if actual != expected:
            archive.unlink(missing_ok=True)
            raise RuntimeSetupError(
                f"OpenSees checksum mismatch: expected {expected}, received {actual}"
            )

        root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".femora-opensees-", dir=root.parent
        ) as temporary:
            extracted = Path(temporary)
            _extract_archive_safely(archive, extracted)
            extracted_launcher = extracted / "OpenSees"
            if not extracted_launcher.is_file():
                raise RuntimeSetupError(
                    "The OpenSees runtime archive does not contain its launcher"
                )
            if root.exists():
                shutil.rmtree(root)
            shutil.move(str(extracted), str(root))
        launcher = root / "OpenSees"
        installed = True

    launcher.chmod(launcher.stat().st_mode | 0o111)
    tcl_library = root / "lib" / "tcl8.6"
    if not tcl_library.is_dir():
        raise RuntimeSetupError(
            f"The bundled Tcl library was not found at '{tcl_library}'"
        )

    version = _probe_runtime(launcher)
    os.environ["FEMORA_OPENSEES"] = str(launcher)
    return RuntimeInfo("colab", launcher, version, tcl_library, installed)


def setup(
    environment: str = "auto",
    *,
    executable: Optional[Union[str, Path]] = None,
    install_dir: Optional[Union[str, Path]] = None,
    release_url: str = DEFAULT_COLAB_RELEASE_URL,
    force: bool = False,
    timeout: float = 120.0,
) -> RuntimeInfo:
    """Configure and validate the OpenSees runtime for an environment.

    Args:
        environment: ``"auto"``, ``"local"``, ``"colab"``, or
            ``"google_colab"``. Automatic mode detects Google Colab and
            otherwise resolves a local executable.
        executable: Existing OpenSees executable to configure. Local mode also
            checks ``FEMORA_OPENSEES`` and ``PATH`` when omitted.
        install_dir: Colab runtime destination. Defaults to
            ``/content/opensees``.
        release_url: GitHub release directory containing the runtime archive
            and its ``.sha256`` file.
        force: Download and reinstall the Colab runtime even if it exists.
        timeout: Download timeout in seconds.

    Returns:
        Validated runtime paths and version information.

    Raises:
        RuntimeSetupError: If download, verification, extraction, or startup
            validation fails.
        ValueError: If ``environment`` is unsupported.

    !!! note "Colab bootstrap"
        Femora must be installed before this function can be imported. A Colab
        notebook therefore installs Femora in its first cell and then calls
        ``fm.runtime.setup("colab")``.
    """

    normalized = _normalize_environment(environment)
    if normalized == "local":
        return _setup_local(executable)
    return _setup_colab(executable, install_dir, release_url, force, timeout)


__all__ = [
    "DEFAULT_COLAB_RELEASE_URL",
    "RuntimeInfo",
    "RuntimeSetupError",
    "setup",
]
