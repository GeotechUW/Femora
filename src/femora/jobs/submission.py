"""Submit a staged workflow without building or running its model locally.

Use submit() with a source file, top-level factory function, or trusted existing
bundle. Source packaging happens locally; the remote runner imports the factory
and executes the tasks in the configured environment. Keep submission under a
main guard so remote imports cannot submit recursively.

The call returns a job handle, not completed engineering results. Follow it
with status checks or use the tracking API to reconnect later. The TACC adapter
validates resource settings before remote writes, but software, input access,
memory, and actual staged task capacity can remain unverified until execution.
"""

from pathlib import Path
import inspect
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence, TypeVar

from .bundle import bundle as create_bundle
from .platforms.base import JobHandle, Platform
from .platforms.resolve import resolve_platform
from .tracking import record_submission

S = TypeVar("S")


def submit(*, platform: Platform[S] | str, settings: S | Mapping[str, Any], source: str | Path | None = None,
           bundle: str | Path | None = None, inputs: Mapping[str, Any] | None = None,
           files: Sequence[str | Path] | Mapping[str, str | Path] = (), entrypoint: str = "build_workflow",
           function=None) -> JobHandle:
    """Package an existing workflow file, or submit a trusted existing bundle.

    The source is not executed locally. Put calls to submit under a __main__
    guard so importing the bundled factory remotely does not submit recursively.
    All model construction, simulation, and postprocessing remain remote tasks.
    Use platform="tacc" with a settings dictionary for interactive login, or
    supply an authenticated Platform and its settings object. Provider adapters
    own validation, staging, and submission. Never store passwords in settings.

    Args:
        platform (Platform | str): Authenticated adapter, or "tacc" for interactive resolution.
        settings (Any): Provider settings object or dictionary accepted by the adapter resolver.
        source (str | Path | None): Workflow source file; mutually exclusive with bundle/function.
        bundle (str | Path | None): Trusted existing workflow ZIP.
        inputs (Mapping[str, Any] | None): JSON-serializable factory/task inputs for source packaging.
        files (Sequence | Mapping): Declared data paths or workspace-destination to source mapping.
        entrypoint (str): Factory name in source, default build_workflow.
        function (Callable | None): Top-level factory defined in a Python file, not a notebook or closure.

    Returns:
        job (JobHandle): Provider handle with id, status, cancel, and download operations.

    Raises:
        ValueError: Source selection or packaging options are inconsistent.
        FileNotFoundError: An existing bundle is missing.
        SubmissionValidationError: TACC preflight found known resource errors.
        RemoteSubmissionError: TACC submission outcome is uncertain; inspect before retrying.

    Example:
        In an existing workflow file, replace the local execute block with:

        ```python
        from femora import jobs
        if __name__ == "__main__":
            job = jobs.submit(
                source=__file__, platform="tacc",
                settings={"system": "stampede3", "queue": "YOUR_QUEUE",
                          "allocation": "YOUR_PROJECT", "nodes": 1,
                          "cores_per_node": 1, "minutes": 10,
                          "app_id": "YOUR_REGISTERED_FEMORA_APP"},
            )
            print(job.id)
        ```

    Warning:
        This call authenticates, stages files, and submits real remote work.
        Replace placeholders using your deployment. Bundles do not include
        installed dependencies or OpenSees. A submission handle does not mean
        the analysis succeeded. Do not automatically retry uncertain submissions.
    """
    if sum(value is not None for value in (source, bundle, function)) != 1:
        raise ValueError("Supply exactly one of source, bundle, or function")
    if function is not None:
        if not inspect.isfunction(function) or function.__qualname__ != function.__name__ or not function.__name__.isidentifier():
            raise ValueError("function must be a top-level workflow factory, not a closure or lambda")
        if entrypoint != "build_workflow":
            raise ValueError("function determines its own entrypoint")
        source = inspect.getsourcefile(function)
        if source is None or not Path(source).is_file():
            raise ValueError("function must be defined in a Python source file; notebook cells are not supported yet")
        entrypoint = function.__name__
    if bundle is not None:
        if inputs is not None or files or entrypoint != "build_workflow":
            raise ValueError("inputs/files/entrypoint apply only when packaging source")
        if not Path(bundle).is_file():
            raise FileNotFoundError(bundle)
        platform, settings = resolve_platform(platform, settings)
        handle = platform.submit(Path(bundle), settings)
        record_submission(platform, handle, settings, Path(bundle).stem)
        return handle
    with TemporaryDirectory(prefix="femora-submit-") as directory:
        archive = create_bundle(source=source, destination=Path(directory) / "workflow.zip",
                                inputs={} if inputs is None else inputs,
                                files=files, entrypoint=entrypoint)
        platform, settings = resolve_platform(platform, settings)
        handle = platform.submit(archive, settings)
        record_submission(platform, handle, settings, Path(source).stem)
        return handle
