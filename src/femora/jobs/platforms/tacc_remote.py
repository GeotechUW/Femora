"""Tapis transport for remote TACC workflow bundles, with injected authentication."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
from uuid import uuid4
import hashlib
import json
import re
import warnings
from zipfile import ZipFile, is_zipfile

from .base import JobStatus, JobSummary
from .tacc import TACCSettings, TACCSubmitter, TACCValidator, SubmissionValidationError, _get


def _job_status(job):
    native = _get(job, "status", "UNKNOWN")
    states = {"FINISHED": "succeeded", "FAILED": "failed", "CANCELLED": "cancelled",
              "RUNNING": "running", "ARCHIVING": "running"}
    pending = {"PENDING", "PROCESSING_INPUTS", "STAGING_INPUTS", "STAGING_JOB",
               "SUBMITTING_JOB", "QUEUED", "BLOCKED", "PAUSED"}
    return JobStatus(states.get(native, "pending" if native in pending else "unknown"),
                     native, _get(job, "lastMessage", "") or "")


class RemoteSubmissionError(RuntimeError):
    """Submission may have reached Tapis. Inspect jobs before retrying.

    Attributes:
        job_name (str): Name to look for in remote discovery.
        bundle_url (str): Retained staged-input location for investigation.

    Warning:
        Retrying blindly may create a duplicate job and consume resources twice.
    """

    __doc_controls__ = {"members": []}

    def __init__(self, name, bundle_url):
        self.job_name = name
        self.bundle_url = bundle_url
        super().__init__(f"Submission outcome unknown for {name}. Check Tapis before retrying; "
                         f"staged input retained at {bundle_url}.")


@dataclass(frozen=True)
class JobCleanupPlan:
    """Validated remote output locations reviewed before destructive cleanup.

    Attributes:
        job_id (str): Provider UUID.
        scratch (tuple[str, str] | None): Scratch system ID and absolute directory.
        archive (tuple[str, str] | None): Archive system ID and absolute directory.

    Note:
        Obtain this from cleanup_plan(); do not invent paths. Merely creating or
        inspecting a plan deletes nothing. cleanup() revalidates it before deletion.
    """

    __doc_controls__ = {"members": []}
    job_id: str
    scratch: tuple[str, str] | None
    archive: tuple[str, str] | None


def _path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or path == PurePosixPath(".") or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("Input directory must be relative to the storage system root")
    return path


def _exists(client, system, path):
    try:
        client.files.listFiles(systemId=system, path=str(path), limit=1)
        return True
    except Exception as error:
        if getattr(getattr(error, "response", None), "status_code", None) == 404:
            return False
        raise


def _cleanup_directory(value, expected_parts):
    if not value:
        return None
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("Unsafe job output directory")
    path = PurePosixPath(value)
    if path.as_posix() != value or path.parts != tuple(expected_parts):
        raise ValueError("Job output directory is outside its expected per-job location")
    return value


def _check_bundle(path):
    """Verify archive integrity without executing its trusted Python source."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate bundle members")
        meta = json.loads(archive.read("bundle.json"))
        if meta.get("format_version") != 1 or not meta.get("entrypoint", "").isidentifier():
            raise ValueError("Unsupported workflow bundle")
        if not isinstance(json.loads(archive.read("inputs.json")), dict):
            raise ValueError("Bundle inputs must be an object")
        expected = {"workflow.py": meta["source_sha256"]}
        for name, digest in meta["files"].items():
            expected["data/" + _path(name).as_posix()] = digest
        if set(names) != {"bundle.json", "inputs.json", *expected}:
            raise ValueError("Unexpected bundle members")
        for name, digest in expected.items():
            actual = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    actual.update(chunk)
            if actual.hexdigest() != digest:
                raise ValueError(f"Bundle checksum mismatch: {name}")


@dataclass(frozen=True)
class TACCJob:
    """Live Tapis job handle returned by TACCPlatform.submit() or job().

    Attributes:
        id (str): Provider job UUID.

    Note:
        Authentication stays with the platform's in-memory client. Use
        jobs.connect() instead when you also want cached status updates.
    """

    __doc_controls__ = {"summary": True, "members": ["status", "details", "cancel", "download", "cleanup_plan", "cleanup"]}
    id: str
    _client: object = field(repr=False, compare=False)

    def status(self) -> JobStatus:
        """Fetch normalized and native states from Tapis without updating the local cache."""
        job = self._client.jobs.getJob(jobUuid=self.id)
        return _job_status(job)

    def cancel(self) -> None:
        """Request cancellation of this remote job; use status() to confirm completion."""
        self._client.jobs.cancelJob(jobUuid=self.id)

    def details(self):
        """Fetch selected scheduler, archive, and execution-directory details.

        Returns:
            details (dict): Provider fields; unavailable values may be None.
        """
        job = self._client.jobs.getJob(jobUuid=self.id)
        return {key: _get(job, key) for key in (
            "name", "status", "remoteJobId", "execSystemId", "execSystemLogicalQueue",
            "nodeCount", "coresPerNode", "maxMinutes", "execSystemExecDir",
            "execSystemOutputDir", "archiveSystemId", "archiveSystemDir", "lastMessage",
        )}

    def cleanup_plan(self) -> JobCleanupPlan:
        """Inspect this owner's terminated job and exact supported output folders.

        Returns:
            plan (JobCleanupPlan): Verified per-job scratch/archive paths; deletes nothing.

        Raises:
            ValueError: Owner, terminal state, UUID, system, or path cannot be verified.

        Note:
            Scratch cleanup supports Stampede3; archive cleanup supports
            DesignSafe My Data's recognized per-job layout only.
        """
        job = self._client.jobs.getJob(jobUuid=self.id)
        owner = self._client.username
        if _get(job, "owner") != owner:
            raise ValueError("Only the job owner may clean up its outputs")
        if _job_status(job).state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("Wait for the job to finish before cleaning up outputs")
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}-[0-9]{3}", self.id):
            raise ValueError("Invalid Tapis job UUID")

        scratch_dir = _get(job, "execSystemExecDir")
        scratch = None
        if scratch_dir:
            if _get(job, "execSystemId") != "stampede3":
                raise ValueError("Only Stampede3 scratch cleanup is supported")
            parts = PurePosixPath(scratch_dir).parts
            if len(parts) != 6 or not parts[2].isdigit():
                raise ValueError("Unexpected Stampede3 scratch directory")
            path = _cleanup_directory(scratch_dir, ("/", "scratch", parts[2], owner, "tapis", self.id))
            scratch = ("stampede3", path)

        archive_dir = _get(job, "archiveSystemDir")
        archive = None
        if archive_dir:
            if _get(job, "archiveSystemId") != "designsafe.storage.default":
                raise ValueError("Only DesignSafe My Data archive cleanup is supported")
            parts = PurePosixPath(archive_dir).parts
            if len(parts) != 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}Z", parts[3]):
                raise ValueError("Unexpected My Data archive directory")
            path = _cleanup_directory(archive_dir, ("/", owner, "tapis-jobs-archive", parts[3], self.id))
            archive = ("designsafe.storage.default", path)
        return JobCleanupPlan(self.id, scratch, archive)

    def cleanup(self, expected: JobCleanupPlan) -> tuple[str, ...]:
        """Delete validated output folders, then hide the job in Tapis.

        Args:
            expected (JobCleanupPlan): Previously inspected plan.

        Returns:
            removed (tuple[str, ...]): Remote directories actually deleted.

        Raises:
            ValueError: Safe checks fail or the reviewed plan has changed.

        Warning:
            Permanently deletes supported remote scratch/archive folders. Download
            needed files first. Partial deletion is possible if a later API call fails.
        """
        plan = self.cleanup_plan()
        if plan != expected:
            raise ValueError("Job output locations changed; review them again")
        removed = []
        for location in (plan.scratch, plan.archive):
            if location is None:
                continue
            system, path = location
            if _exists(self._client, system, path):
                self._client.files.delete(systemId=system, path=path)
                removed.append(path)
        self._client.jobs.hideJob(jobUuid=self.id)
        return tuple(removed)

    def download(self, destination: Path, progress=None) -> Path:
        """Stream terminated-job output to a new local ZIP without extracting it.

        Args:
            destination (Path): New local archive filename, not a directory.
            progress (Callable | None): Callback with phase, byte count, total;
                total can be None during receiving.

        Returns:
            archive (Path): Saved archive after ZIP-format validation.

        Raises:
            ValueError: Job is active, URL is invalid, or downloaded output is not a ZIP.
            FileExistsError: Destination or its .part file already exists.

        Note:
            A failed transfer can leave a .part file. No extraction, remote
            deletion, or automatic retry is performed.
        """
        import requests
        import time

        if self.status().state not in ("succeeded", "failed", "cancelled"):
            raise ValueError("Wait for the job to terminate before downloading")
        destination = Path(destination)
        partial = destination.with_name(destination.name + ".part")
        if destination.exists() or partial.exists():
            raise FileExistsError("Download destination or partial file already exists")
        base = self._client.base_url.rstrip("/")
        url = urlsplit(base)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Authenticated client must use an HTTPS tenant URL")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(base + "/v3/jobs/" + quote(self.id, safe="") + "/output/download/",
                          headers={"X-Tapis-Token": self._client.access_token.access_token},
                          stream=True, timeout=(30, 120), allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected download response; redirects not followed")
            length = response.headers.get("Content-Length")
            total = int(length) if length and str(length).isdigit() and not response.headers.get("Content-Encoding") else None
            received, last_report = 0, 0.0
            if progress:
                progress("receiving", received, total)
            with partial.open("xb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
                        received += len(chunk)
                        now = time.monotonic()
                        if progress and now - last_report >= 0.25:
                            progress("receiving", received, total)
                            last_report = now
            if progress:
                progress("receiving", received, total)
                progress("validating", received, received)
        if not is_zipfile(partial):
            raise ValueError("Invalid output ZIP; partial file retained")
        saved = 0
        if progress:
            progress("saving", saved, received)
        with destination.open("xb") as stream, partial.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                stream.write(chunk)
                saved += len(chunk)
                now = time.monotonic()
                if progress and now - last_report >= 0.25:
                    progress("saving", saved, received)
                    last_report = now
        if progress:
            progress("saving", saved, received)
        partial.unlink()
        return destination


class TACCPlatform:
    """Complete Platform implementation using an existing registered Femora app.

    input_directory is storage-root-relative. Each submission gets a UUID child.
    Supply an authenticated client, or explicitly call login() for an interactive
    connection. Credentials are never saved. Resources remain in TACCSettings.

    Args:
        client (object): Authenticated Tapis client.
        app_id (str): Existing registered Femora application ID.
        app_version (str): Application version.
        storage_system (str): Input staging storage-system ID.
        input_directory (str): Staging parent relative to storage-system root.
        archive_directory (str): Tapis output archive directory template.
        on_validation (Callable | None): Observer receiving preflight reports.

    Note:
        This uses a deployed application; it does not provision a cluster,
        register an app, install dependencies, or provide OpenSees.
    """

    __doc_controls__ = {"summary": True, "members": ["login", "validate", "submit", "job", "list_jobs", "tracking_metadata"]}

    def __init__(self, client, *, app_id, app_version, storage_system, input_directory,
                 archive_directory="${EffectiveUserId}/tapis-jobs-archive/${JobCreateDate}",
                 on_validation=None):
        self._client = client
        self.app_id, self.app_version = app_id, app_version
        self.storage_system = storage_system
        self.input_directory = _path(input_directory)
        if not archive_directory:
            raise ValueError("archive_directory must not be empty")
        self.archive_directory = archive_directory
        self.on_validation = on_validation

    def validate(self, workflow, settings):
        """Run read-only checks against the actual workflow and resource settings.

        Args:
            workflow (Workflow): Concrete stage/task definitions.
            settings (TACCSettings): Resource request.

        Returns:
            report (ValidationReport): Errors and explicitly unverified conditions.
        """
        return TACCValidator(self._client).validate(workflow, settings)

    @classmethod
    def login(cls, *, app_id, app_version="0.1.0",
              base_url="https://designsafe.tapis.io",
              storage_system="designsafe.storage.default", input_directory=None):
        """Prompt privately for a connection; no upload or submission occurs here.

        Args:
            app_id (str): Registered application ID, or discovery filter ID.
            app_version (str): Registered application version.
            base_url (str): HTTPS Tapis tenant URL without embedded credentials.
            storage_system (str): Input staging storage system.
            input_directory (str | None): Storage-relative staging directory;
                defaults to the authenticated user's Femora submissions folder.

        Returns:
            platform (TACCPlatform): Adapter holding an authenticated in-memory client.

        Raises:
            ValueError: URL is invalid or no interactive terminal is available.
            RuntimeError: Authentication fails; private error details are omitted.

        Example:
            ```python
            from femora.jobs.platforms import TACCPlatform
            def login_for_jobs():
                return TACCPlatform.login(app_id="YOUR_REGISTERED_FEMORA_APP")
            ```

        Note:
            Prompts for username/password. Credentials are not stored in bundles
            or the job registry. For noninteractive use, inject an authenticated
            client through the constructor instead.
        """
        import getpass
        import sys
        from tapipy.tapis import Tapis

        url = urlsplit(base_url)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Login requires an HTTPS tenant URL")
        if not sys.stdin.isatty():
            raise ValueError("Interactive login requires a terminal; otherwise pass an authenticated client")
        print(f"Login: {base_url} (credentials are not saved)")
        username = input("Username: ").strip()
        password = None
        client = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Password (hidden): ")
            if not username or not password:
                raise ValueError("Username and password are required")
            directory = input_directory if input_directory is not None else f"{username}/femora-workflows/submissions"
            _path(directory)
            client = Tapis(base_url=base_url, username=username, password=password)
            client.get_tokens()
            return cls(client, app_id=app_id, app_version=app_version,
                       storage_system=storage_system, input_directory=directory)
        except Exception as error:
            if client is not None:
                client.access_token = client.refresh_token = None
            raise RuntimeError(f"Login failed ({type(error).__name__}); private details omitted") from None
        finally:
            password = None
            if client is not None:
                client.password = None

    def job(self, job_id):
        """Create a live handle for an existing UUID without submitting again.

        Args:
            job_id (str): Provider job UUID.

        Returns:
            job (TACCJob): Handle using this platform's authenticated client.
        """
        return TACCJob(job_id, self._client)

    def tracking_metadata(self):
        """Return provider and safe connection metadata for local tracking.

        Returns:
            metadata (dict): Platform name and tenant/account/app identity, without tokens.
        """
        return {"platform": "tacc", "connection": {
            "base_url": self._client.base_url, "username": self._client.username,
            "app_id": self.app_id, "app_version": self.app_version,
        }}

    def list_jobs(self, *, page_size=100):
        """Discover owned Femora jobs, including jobs submitted on other machines.

        An exact configured app ID supports custom deployments. Standard
        [owner-]femora-workflow-SYSTEM IDs also recognize older deployments.
        Job names are deliberately not used as identification.

        Args:
            page_size (int): Requested page size from 1 to 1000.

        Yields:
            summary (JobSummary): Safe metadata for jobs owned by the authenticated account.

        Raises:
            ValueError: Requested page size is outside the supported range.

        Note:
            Contacts Tapis but does not itself update the local registry; use
            jobs.sync() or jobs.list_jobs(platform=adapter) to cache discoveries.
        """
        if not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        offset, seen = 0, set()
        while True:
            page = self._client.jobs.getJobList(
                listType="MY_JOBS", limit=page_size, skip=offset,
                orderBy="created(desc),uuid(asc)")
            if not page:
                return
            new_ids = set()
            for job in page:
                identifier = _get(job, "uuid")
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError("Invalid job discovery response")
                if identifier in seen or identifier in new_ids:
                    continue
                new_ids.add(identifier)
                app_id = _get(job, "appId", "")
                if _get(job, "owner") != self._client.username:
                    continue
                if not isinstance(app_id, str) or not (
                    (self.app_id != "job-tracking" and app_id == self.app_id)
                    or re.fullmatch(r"(?:.+-)?femora-workflow-[A-Za-z0-9_-]+", app_id)
                ):
                    continue
                yield JobSummary(
                    id=identifier, name=_get(job, "name") or identifier,
                    submitted_at=_get(job, "created") or "", status=_job_status(job),
                    connection={"app_id": app_id, "app_version": _get(job, "appVersion") or "0.1.0"},
                    resources={"system": _get(job, "execSystemId")} if _get(job, "execSystemId") else {},
                )
            if not new_ids:
                raise RuntimeError("Job listing pagination did not advance")
            seen.update(new_ids)
            # Keep going until an empty page: a service may cap page size.
            offset += len(page)

    def submit(self, bundle: Path, settings: TACCSettings) -> TACCJob:
        """Validate, upload, and submit a trusted existing workflow bundle.

        Args:
            bundle (Path): Local workflow ZIP created by jobs.bundle().
            settings (TACCSettings): Logical queue, allocation, node/CPU counts, and minutes.

        Returns:
            job (TACCJob): Remote handle; analysis may still be queued or fail later.

        Raises:
            SubmissionValidationError: Known preflight errors block submission.
            FileExistsError: The generated staging directory already exists.
            RemoteSubmissionError: Submission outcome is uncertain after staging.

        Warning:
            Writes remote files and submits real work. Workflow task capacity
            remains unverified until remote replay constructs the workflow.
            Prefer jobs.submit() to package source and automatically record the
            returned job in the local registry.
        """
        bundle = Path(bundle)
        _check_bundle(bundle)
        unique = uuid4().hex
        folder = self.input_directory / unique
        remote = folder / "workflow.zip"
        url = f"tapis://{self.storage_system}/{remote}"
        request = dict(
            name=f"femora-{unique}", appId=self.app_id, appVersion=self.app_version,
            execSystemId=settings.system, execSystemLogicalQueue=settings.queue,
            nodeCount=settings.nodes, coresPerNode=settings.cores_per_node, maxMinutes=settings.minutes,
            archiveSystemId=self.storage_system,
            archiveSystemDir=self.archive_directory.rstrip("/") + "/${JobUUID}",
            fileInputs=[dict(name="workflow", sourceUrl=url, targetPath="workflow.zip")],
            parameterSet={"schedulerOptions": [dict(name="allocation", arg=f"-A {settings.allocation}")]},
        )
        adapter = TACCSubmitter(self._client)
        _, report = adapter.preflight(request)
        if self.on_validation:
            self.on_validation(report)
        if not report.valid:
            raise SubmissionValidationError(report)
        if report.issues and self.on_validation is None:
            warnings.warn("; ".join(f"{i.severity}: {i.field}: {i.message}" for i in report.issues),
                          UserWarning, stacklevel=2)
        for parent in reversed(folder.parents):
            if parent != PurePosixPath(".") and not _exists(self._client, self.storage_system, parent):
                self._client.files.mkdir(systemId=self.storage_system, path=str(parent))
        if _exists(self._client, self.storage_system, folder):
            raise FileExistsError("Submission input directory already exists")
        self._client.files.mkdir(systemId=self.storage_system, path=str(folder))
        with bundle.open("rb") as stream:
            self._client.files.insert(systemId=self.storage_system, path=str(remote), file=stream)
        try:
            result = adapter.submit_request(request)
        except SubmissionValidationError:
            raise
        except Exception:
            raise RemoteSubmissionError(request["name"], url) from None
        identifier = _get(result, "uuid")
        if not isinstance(identifier, str) or not identifier:
            raise RemoteSubmissionError(request["name"], url)
        return self.job(identifier)
