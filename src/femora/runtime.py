# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Use an external OpenSees executable to run an exported Tcl model.

The runtime API connects a Python session to a solver. First resolve and validate
the executable with [setup()][femora.runtime.setup], then invoke an existing Tcl
file with [run()][femora.runtime.run]. It neither builds the model nor submits a
remote job. Use [Jobs](../jobs/index.md) when you need staged tasks, scheduling,
or remote submission rather than a direct solver invocation.

## Configure A Solver And Run One Model

Assume the model has already been exported to ``example_outputs/case/model.tcl``
and a compatible OpenSees build is installed. Replace the executable placeholder
with the actual file on your machine:

```python
from pathlib import Path
from femora import runtime

info = runtime.setup("local", executable=Path("path/to/OpenSees"))
print(info.executable)
print(info.version)

script = Path("example_outputs/case/model.tcl").resolve()
completed = runtime.run(script, executable=info.executable, show_output=True)
print(completed.returncode)
```

``setup()`` starts a short validation script, not your model. It returns a
[RuntimeInfo][femora.runtime.RuntimeInfo] describing the resolved executable.
It also sets ``FEMORA_OPENSEES`` in this Python process so later runtime calls
can reuse that choice; it does not permanently configure another terminal.

``run()`` starts the actual solver and waits until it exits. It returns a
``subprocess.CompletedProcess`` on success. This does not validate numerical
accuracy or guarantee every possible Tcl failure was detected.

## Where Output Goes

By default, the solver's working directory is the Tcl file's parent directory.
Relative recorder paths and Tcl file operations are interpreted by the solver
from that working directory. Use ``cwd=...`` deliberately when the model expects
another layout; runtime does not create that directory for you.

The runtime creates no stage/task folders, ``manifest.json``, or ``stdout.log``.
Those belong to other execution layers or your own program. Successful calls
retain combined stdout/stderr in ``completed.stdout``. You can save it explicitly:

```python
log = script.parent / "solver_output.log"
log.write_text(completed.stdout, encoding="utf-8")
```

That log is written by this example after success, not automatically during
execution. Captured output is held in memory; consider its size for long runs.
Recorder files are separate numerical output and remain where the Tcl model
writes them. Read those using [Results & Postprocessing](../results/index.md).

## Progress And Failure

Femora-managed ``FEMORA_PROGRESS`` records become progress bars. Warning/error
diagnostics are displayed even with the default ``show_output=False``; ordinary
solver lines are also displayed when ``show_output=True``. Displaying a warning
does not itself turn the call into a failure.

To handle a failed model invocation, replace the direct ``run()`` call above
with this guarded call rather than running the model a second time:

```python
try:
    completed = runtime.run(script, executable=info.executable)
except runtime.RuntimeExecutionError as error:
    print(str(error))
```

A nonzero exit status or a managed analysis error record raises
[RuntimeExecutionError][femora.runtime.RuntimeExecutionError]. Its message gives
the failure summary and, when available, the last 20 captured output lines.
There is no returned completed process on that path, no partial Jobs ``RunResult``,
and no automatic retry or rollback of recorder files already written.

If configuration fails before execution, inspect
[RuntimeSetupError][femora.runtime.RuntimeSetupError] instead. A missing Tcl file
raises ``FileNotFoundError``. See the error pages for the distinctions and the
expanded function documentation below for complete parameters.

??? example "Use executable discovery instead of an explicit path"
    For local setup, an explicit executable file takes precedence over
    ``FEMORA_OPENSEES``; otherwise OpenSees is discovered on ``PATH``. If a
    selected explicit/environment path is invalid, setup reports the problem
    rather than silently choosing a different executable.

    ```python
    info = runtime.setup("local")
    print(info.executable)
    ```

    ``run()`` can resolve the same choices, but does not perform setup's validation
    probe. Pass ``info.executable`` when you want the choice to be explicit.

??? example "Prepare the bundled Google Colab runtime"
    In a supported Colab environment with Femora already installed:

    ```python
    info = runtime.setup("colab")
    print(info.executable, info.tcl_library, info.installed)
    ```

    Colab setup can download and install a bundled runtime, verifies its published
    checksum, checks the Tcl library, and probes the launcher. A valid existing
    launcher is reused unless ``force=True``. Use a dedicated ``install_dir``:
    installation/reinstallation can replace that directory and its contents.
    Network, filesystem, and archive errors can propagate in addition to the
    runtime-specific validation errors. This is not a generic cloud deployment API.

## Where To Go Next

- [RuntimeInfo][femora.runtime.RuntimeInfo]: resolved paths and configuration fields.
- [RuntimeSetupError][femora.runtime.RuntimeSetupError]: executable preparation and validation failures.
- [RuntimeExecutionError][femora.runtime.RuntimeExecutionError]: launch, process, and managed-analysis failures.
- [Jobs](../jobs/index.md): ordered tasks, execution manifests, and remote job management.
"""

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

from tqdm.auto import tqdm


DEFAULT_COLAB_RELEASE_URL = (
    "https://github.com/amnp95/OpenSees/releases/download/opensees-colab-latest"
)
DEFAULT_COLAB_ARCHIVE = "OpenSees-Colab-linux-x86_64.tar.gz"
_RUNTIME_MARKER = "FEMORA_OPENSEES_RUNTIME_OK"


class RuntimeSetupError(RuntimeError):
    """The solver could not be resolved, prepared, or validated.

    Examples include a missing executable, an unsuccessful validation probe,
    checksum mismatch, or an invalid bundled runtime layout. Unsupported
    environment names raise ValueError instead. Network/archive/filesystem
    operations can also raise their underlying exceptions rather than this type.

    Example:
        ```python
        from femora import runtime
        try:
            info = runtime.setup("local")
        except runtime.RuntimeSetupError as error:
            print("Check the executable configuration:", str(error))
        ```

    Note:
        Inspect the selected file, environment variable, PATH, and message before
        retrying. setup() validates startup, not your model's required features or
        numerical behavior. run() can raise this type when it cannot locate a
        solver, but reports a launch failure as RuntimeExecutionError.
    """

    __doc_controls__ = {"members": []}


class RuntimeExecutionError(RuntimeError):
    """The solver could not start or reported a detected execution failure.

    run() raises this type for a launch OSError, nonzero exit code, or managed
    FEMORA_PROGRESS error record, including a managed error with exit code zero.
    The message contains a summary and, after a completed failed process, up to
    the last 20 captured output lines. A launch error can have an underlying
    operating-system exception in __cause__.

    Example:
        With an exported model and resolved executable:

        ```python
        from femora import runtime
        def run_model(script, executable):
            try:
                return runtime.run(script, executable=executable)
            except runtime.RuntimeExecutionError as error:
                print(str(error))
                raise
        ```

    Note:
        The exception has no Jobs-style run attribute or attached completed
        process. Missing model files raise FileNotFoundError before launch.
        Warning text alone is not a failure signal, and a zero exit code without
        managed error records does not certify a correct or converged analysis.
        Files already written by the model are not rolled back.
    """

    __doc_controls__ = {"members": []}


@dataclass(frozen=True)
class RuntimeInfo:
    """Configuration returned by setup(), not a running solver or saved settings file.

    Attributes:
        environment (str): Normalized environment name, either ``"colab"`` or
            ``"local"``.
        executable (Path): Absolute path to the OpenSees launcher or executable.
        version (str | None): Version parsed from the startup banner, or None
            if the probe succeeded without a recognizable version string.
        tcl_library (Path | None): Bundled Tcl library path for the Colab runtime, otherwise
            ``None``.
        installed (bool): Whether this call installed/replaced the bundled runtime,
            not whether any compatible executable already exists. False for local setup.

    Example:
        ```python
        from femora import runtime
        info = runtime.setup("local")
        print(info.environment, info.executable, info.version)
        ```

    Note:
        Ordinary callers obtain this frozen record from setup(). It does not
        keep a solver process alive, configure an MPI allocation, or persist
        settings between sessions. Passing info.executable to run() selects that
        file explicitly; recorded response units remain the model's responsibility.
    """

    __doc_controls__ = {"members": []}

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
    """Resolve or prepare a solver and validate startup with a short Tcl probe.

    This does not run the model, install arbitrary Python dependencies, or
    request remote resources. On success FEMORA_OPENSEES is set for the current
    Python process and inherited by subsequently started child processes.

    Args:
        environment (str): ``"auto"``, ``"local"``, ``"colab"``, or
            ``"google_colab"``. Automatic mode detects Google Colab and
            otherwise resolves a local executable.
        executable (str | Path | None): Executable file path, not a shell command.
            Local resolution uses this value, then FEMORA_OPENSEES, then PATH
            discovery of OpenSees/OpenSees.exe. An invalid selected path is not
            silently replaced by a PATH candidate.
        install_dir (str | Path | None): Dedicated Colab installation directory;
            defaults to /content/opensees. Ignored in local mode.
        release_url (str): Colab bundle release directory containing the archive
            and published SHA-256 checksum. Ignored in local mode.
        force (bool): Reinstall the Colab bundle even if its launcher exists;
            ignored in local mode.
        timeout (float): Per-download timeout in seconds, not a model execution
            limit. The separate startup probe has a 30-second timeout.

    Returns:
        info (RuntimeInfo): Validated configuration. Version can be None even
            when the probe succeeds.

    Raises:
        RuntimeSetupError: Executable resolution, validation, checksum, or
            bundled layout checks fail.
        ValueError: The environment name is unsupported.
        OSError: Filesystem/download operations fail; other network or archive
            exceptions can also propagate without runtime-specific wrapping.

    Example:
        ```python
        from femora import runtime
        info = runtime.setup("local", executable="path/to/OpenSees")
        print(info.executable, info.version)
        ```

    Warning:
        Use a dedicated Colab installation directory. Installation or
        reinstallation can replace that directory and all its contents. The
        checksum checks consistency with the published bundle, not the trust
        of an arbitrary release source. Femora must already be installed before
        this helper can be imported.
    """

    normalized = _normalize_environment(environment)
    if normalized == "local":
        return _setup_local(executable)
    return _setup_colab(executable, install_dir, release_url, force, timeout)


def run(
    tcl_file: Union[str, Path],
    *,
    executable: Optional[Union[str, Path]] = None,
    cwd: Optional[Union[str, Path]] = None,
    show_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke one exported Tcl model and wait for the solver to finish.

    Femora progress records are rendered as ``tqdm`` bars. OpenSees warnings,
    errors, and failed-step diagnostics are printed immediately. Set
    ``show_output=True`` to also display ordinary solver output.

    Args:
        tcl_file (str | Path): Existing exported Tcl file, resolved relative to
            the caller's current directory, independently of cwd.
        executable (str | Path | None): Solver file path. When omitted, uses
            FEMORA_OPENSEES, then PATH discovery. No startup probe is performed.
        cwd (str | Path | None): Existing solver working directory, resolved
            relative to the caller's directory. Defaults to the script's parent.
            Does not change how tcl_file itself is resolved or create a folder.
        show_output (bool): Display ordinary solver lines as well as diagnostics.
            Managed progress records are handled as progress bars.

    Returns:
        completed (subprocess.CompletedProcess[str]): Successful command, return
            code, and combined stdout/stderr text in stdout. stderr is None.

    Raises:
        FileNotFoundError: The resolved Tcl file does not exist.
        RuntimeSetupError: No executable file can be resolved.
        RuntimeExecutionError: The process cannot start, exits nonzero, or emits
            a managed FEMORA_PROGRESS error record.

    Example:
        After setup() and model export:

        ```python
        from femora import runtime
        def execute_exported_model(script, executable):
            completed = runtime.run(script, executable=executable, show_output=True)
            return completed.stdout
        ```

    Note:
        No task workspace, manifest, or log file is created automatically. Relative
        Tcl file operations use the solver's working directory. All captured
        output remains in memory on success; write completed.stdout to a file
        explicitly if needed. On failure the exception message includes a summary
        and up to 20 trailing lines, not an attached CompletedProcess or RunResult.

        Diagnostic text alone does not cause failure. A zero exit code without
        managed error records cannot detect every possible Tcl or numerical
        failure. Inspect convergence and response data independently. This helper
        does not construct an MPI launch command, submit a job, retry, or roll back
        files; use Jobs for allocation-aware task launching.
    """
    script = Path(tcl_file).expanduser().resolve()
    if not script.is_file():
        raise FileNotFoundError(f"Tcl model was not found: '{script}'")

    configured = executable or os.environ.get("FEMORA_OPENSEES")
    solver = Path(configured).expanduser() if configured else None
    if solver is None:
        discovered = shutil.which("OpenSees") or shutil.which("OpenSees.exe")
        solver = Path(discovered) if discovered else None
    if solver is None or not solver.is_file():
        raise RuntimeSetupError(
            "OpenSees was not found. Pass executable=..., set FEMORA_OPENSEES, "
            "or add OpenSees to PATH."
        )
    solver = solver.resolve()

    working_directory = Path(cwd).expanduser().resolve() if cwd else script.parent
    command = [str(solver), str(script)]
    progress_bar = None
    output_lines: list[str] = []
    analysis_error: Optional[str] = None
    diagnostic_pattern = re.compile(
        r"\b(warning|error|failed|failure|singular|invalid)\b", re.IGNORECASE
    )

    try:
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )
    except OSError as exc:
        raise RuntimeExecutionError(
            f"Unable to start OpenSees at '{solver}'"
        ) from exc

    assert process.stdout is not None
    for raw_line in process.stdout:
        output_lines.append(raw_line)
        line = raw_line.rstrip("\r\n")
        fields = line.split("|")

        if len(fields) >= 4 and fields[0] == "FEMORA_PROGRESS":
            event, name = fields[1], fields[2]
            if event == "START":
                if progress_bar is not None:
                    progress_bar.close()
                unit = fields[4] if len(fields) > 4 else "step"
                parse_value = float if unit == "s" else int
                initial = parse_value(fields[5]) if len(fields) > 5 else 0
                progress_bar = tqdm(
                    total=parse_value(fields[3]),
                    initial=initial,
                    desc=name,
                    unit=unit,
                    dynamic_ncols=True,
                )
            elif event == "UPDATE" and progress_bar is not None:
                unit = fields[5] if len(fields) > 5 else "step"
                current = float(fields[3]) if unit == "s" else int(fields[3])
                progress_bar.update(max(0, current - progress_bar.n))
            elif event == "ERROR":
                analysis_error = (
                    f"Analysis '{name}' failed at step {fields[3]} "
                    f"with OpenSees code {fields[4] if len(fields) > 4 else 'unknown'}"
                )
                tqdm.write(analysis_error)
            continue

        if show_output or diagnostic_pattern.search(line):
            tqdm.write(line)

    return_code = process.wait()
    if progress_bar is not None:
        progress_bar.close()

    output = "".join(output_lines)
    completed = subprocess.CompletedProcess(command, return_code, output, None)
    if return_code != 0 or analysis_error is not None:
        summary = analysis_error or f"OpenSees exited with code {return_code}"
        tail = "\n".join(output.splitlines()[-20:])
        raise RuntimeExecutionError(f"{summary}\n{tail}" if tail else summary)
    return completed


__all__ = [
    "DEFAULT_COLAB_RELEASE_URL",
    "RuntimeInfo",
    "RuntimeExecutionError",
    "RuntimeSetupError",
    "run",
    "setup",
]
