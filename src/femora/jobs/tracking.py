"""Discover remote jobs and reconnect without submitting work again.

list_jobs() reads cached records unless an authenticated platform is supplied.
sync() performs remote discovery and updates the cache. add() records a known
UUID locally without verifying its existence. connect() wraps a cached record
in a live-capable TrackedJob; authentication can be requested at that point.

```python
from femora.jobs import list_jobs, connect

def inspect_cached_jobs():
    for record in list_jobs():
        print(record.id, record.state, record.checked_at)

def inspect_live_job(job_id):
    job = connect(job_id)  # Existing cached record; may prompt for login.
    return job.status()
```

Cached state is not necessarily current remote state. The registry saves safe
identity/resource metadata, not credentials. Cancellation, ZIP downloads,
remote cleanup, and local hiding are distinct operations; see TrackedJob and
JobRegistry before using them.
"""

from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import time
import warnings
from contextlib import contextmanager
from urllib.parse import urlsplit


def _now():
    return datetime.now(timezone.utc).isoformat()


def _resources(values):
    return {key: value for key, value in (values or {}).items()
            if key in {"system", "queue", "allocation", "nodes", "cores_per_node", "minutes"}}


@dataclass(frozen=True)
class JobRecord:
    """Cached job identity and last-known state, not a live remote connection.

    Attributes:
        key (str): Unique local key distinguishing provider/account/job identities.
        id (str): Provider job UUID.
        platform (str): Adapter name, currently tacc.
        name (str): Human-readable job name.
        submitted_at (str): Submission timestamp or local registration timestamp.
        connection (dict): Safe tenant/account/app metadata; no credentials.
        resources (dict): Selected scheduler resource fields.
        state (str): Last cached normalized state.
        native_state (str): Last cached provider state.
        checked_at (str | None): Last refresh timestamp, or None if not checked.
    """

    __doc_controls__ = {"members": []}
    key: str
    id: str
    platform: str
    name: str
    submitted_at: str
    connection: dict
    resources: dict
    state: str = "unknown"
    native_state: str = "UNKNOWN"
    checked_at: str | None = None


class JobRegistry:
    """Persist local job records in SQLite, without saving credentials.

    Args:
        path (str | Path | None): Database path. Defaults to FEMORA_JOBS_DB or
            the platform-specific Femora user-data directory's jobs.sqlite3.

    Note:
        Local records are not authoritative remote status. Hiding a record does
        not cancel a job or delete remote files. Separate processes can share
        this registry without replacing the entire cache.
    """

    __doc_controls__ = {"summary": True, "members": ["save", "hide", "is_hidden", "list", "get"]}

    def __init__(self, path=None):
        from platformdirs import user_data_path
        self.path = Path(path or os.environ.get("FEMORA_JOBS_DB") or
                         user_data_path("femora", appauthor=False) / "jobs.sqlite3")

    @contextmanager
    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, record TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS hidden_jobs (key TEXT PRIMARY KEY)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, record):
        """Insert or update a record unless its key is hidden.

        Args:
            record (JobRecord): Safe job metadata to persist.

        Returns:
            record (JobRecord): Supplied record, even when a hidden key prevents insertion.
        """
        with self._open() as db:
            db.execute("INSERT OR REPLACE INTO jobs SELECT ?, ? WHERE NOT EXISTS "
                       "(SELECT 1 FROM hidden_jobs WHERE key = ?)",
                       (record.key, json.dumps(asdict(record)), record.key))
        return record

    def hide(self, key):
        """Remove a cached job and keep remote discovery from restoring it.

        Args:
            key (str): Full registry key, not the provider UUID.

        Returns:
            hidden (bool): Whether an existing cached record was removed.

        Note:
            This changes only the local registry; no cancellation or remote deletion occurs.
        """
        with self._open() as db:
            deleted = db.execute("DELETE FROM jobs WHERE key = ?", (key,)).rowcount
            if deleted:
                db.execute("INSERT OR IGNORE INTO hidden_jobs VALUES (?)", (key,))
        return bool(deleted)

    def is_hidden(self, key):
        """Check the local discovery suppression list.

        Args:
            key (str): Full registry key.

        Returns:
            hidden (bool): Whether the key is locally hidden.
        """
        with self._open() as db:
            return db.execute("SELECT 1 FROM hidden_jobs WHERE key = ?", (key,)).fetchone() is not None

    def list(self):
        """List cached records without remote login or refresh.

        Returns:
            records (list[JobRecord]): Records sorted by submission timestamp, newest first.
        """
        with self._open() as db:
            return sorted((JobRecord(**json.loads(row[0])) for row in
                           db.execute("SELECT record FROM jobs")),
                          key=lambda record: record.submitted_at, reverse=True)

    def get(self, job_id):
        """Resolve one cached record by provider UUID or full local key.

        Args:
            job_id (str): Provider UUID or registry key.

        Returns:
            record (JobRecord): Matching cached job.

        Raises:
            ValueError: No match or multiple matches; use the full key to disambiguate.
        """
        matches = [record for record in self.list() if job_id in (record.id, record.key)]
        if len(matches) != 1:
            raise ValueError("Job not found or ambiguous; use its full registry key")
        return matches[0]


def add(job_id, *, platform="tacc", name=None, connection=None, resources=None, registry=None):
    """Register an existing job without submitting or contacting the provider.

    Args:
        job_id (str): Existing provider UUID.
        platform (str): Tracking adapter name, currently tacc.
        name (str | None): Display name; defaults to job_id.
        connection (dict | None): Safe base_url, username, app_id, and app_version fields.
        resources (dict | None): Resource metadata; only approved fields are saved.
        registry (JobRegistry | None): Local cache or default registry.

    Returns:
        record (JobRecord): Existing or newly cached record.

    Raises:
        ValueError: Identity, connection, or platform is invalid, or the key is hidden.

    Note:
        Registration does not verify that the job exists. Never supply passwords
        or access tokens in connection fields.
    """
    if platform not in _CONNECTORS:
        raise ValueError(f"Unsupported tracking platform: {platform}")
    connection = dict(connection or {})
    allowed = {"base_url", "username", "app_id", "app_version"}
    if set(connection) - allowed:
        raise ValueError("Connection records allow only tenant, username, app ID and version; no credentials")
    if any(not isinstance(value, str) or not value.strip() for value in connection.values()):
        raise ValueError("Connection fields must be nonempty strings")
    if platform == "tacc":
        connection.setdefault("base_url", "https://designsafe.tapis.io")
        url = urlsplit(connection["base_url"])
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Tenant must be an HTTPS URL without credentials, query, or fragment")
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("A nonempty job ID is required")
    # Only persist resource fields, never arbitrary settings or workflow inputs.
    resources = _resources(resources)
    key = _job_key(job_id, platform, connection)
    store = registry or JobRegistry()
    if store.is_hidden(key):
        raise ValueError("Job is hidden from this tracker")
    existing = next((r for r in store.list() if r.key == key), None)
    return existing or store.save(JobRecord(key, job_id, platform, name or job_id,
                                           _now(), connection, resources))


def sync(platform, *, registry=None):
    """Discover remote jobs through an authenticated adapter and cache them.

    Remote discovery never deletes cached jobs that a provider no longer lists.
    Only normalized summaries and safe connection fields are persisted.

    Args:
        platform (JobDiscovery): Authenticated adapter supporting discovery.
        registry (JobRegistry | None): Destination cache, or the default registry.

    Returns:
        records (list[JobRecord]): Refreshed records discovered during this call.

    Note:
        This contacts the provider and writes the local cache, but does not submit jobs.
    """
    store = registry or JobRegistry()
    metadata = platform.tracking_metadata()
    records = []
    for summary in platform.list_jobs():
        connection = {**metadata["connection"], **summary.connection}
        if store.is_hidden(_job_key(summary.id, metadata["platform"], connection)):
            continue
        record = add(summary.id, platform=metadata["platform"], name=summary.name,
                     connection=connection,
                     resources=summary.resources, registry=store)
        record = replace(record, name=summary.name,
                         submitted_at=summary.submitted_at or record.submitted_at,
                         connection={**record.connection, **summary.connection},
                         resources={**record.resources, **_resources(summary.resources)},
                         state=summary.status.state, native_state=summary.status.native_state,
                         checked_at=_now())
        records.append(store.save(record))
    return records


def _job_key(job_id, platform, connection):
    return hashlib.sha256(json.dumps([platform, connection.get("base_url"),
                                      connection.get("username"), job_id]).encode()).hexdigest()


def list_jobs(*, platform=None, registry=None):
    """List cached jobs, or discover remote jobs when given an authenticated adapter.

    Args:
        platform (JobDiscovery | None): Adapter for live discovery; None reads only the cache.
        registry (JobRegistry | None): Cache to use, or the default registry.

    Returns:
        records (list[JobRecord]): Cached records, or newly discovered/refreshed records.

    Example:
        ```python
        from femora.jobs import list_jobs
        for record in list_jobs():
            print(record.id, record.state, record.checked_at)
        ```

    Note:
        jobs.list is an alias for this function. Cached states can be stale;
        passing a platform performs remote discovery and updates the cache.
    """
    if platform is not None:
        return sync(platform, registry=registry)
    return (registry or JobRegistry()).list()


def _tacc_connect(record):
    from .platforms.tacc_remote import TACCPlatform
    target = TACCPlatform.login(app_id=record.connection.get("app_id", "job-tracking"),
                                app_version=record.connection.get("app_version", "0.1.0"),
                                base_url=record.connection.get("base_url", "https://designsafe.tapis.io"))
    expected = record.connection.get("username")
    if expected and target._client.username != expected:
        raise ValueError("Authenticated account does not match the job record")
    return target


_CONNECTORS = {"tacc": _tacc_connect}


class TrackedJob:
    """Reconnectable job handle that refreshes its cached status.

    Obtain this from connect(); ordinary callers need not construct it directly.

    Attributes:
        id (str): Provider job UUID.
        record (JobRecord): Cached record, updated by status().

    Example:
        ```python
        from femora.jobs import connect
        job = connect("YOUR_CACHED_JOB_UUID")  # May prompt for login.
        print(job.status().state)
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["status", "details", "wait", "cancel", "download", "cleanup_plan", "cleanup"]}
    def __init__(self, record, handle, registry):
        self.record, self._handle, self._registry = record, handle, registry
        self.id = record.id

    def status(self):
        """Fetch live remote status and update the local record.

        Returns:
            status (JobStatus): Normalized and provider-native states.

        Note:
            This contacts the provider; network and authorization errors propagate.
        """
        from dataclasses import replace
        status = self._handle.status()
        self.record = replace(self.record, state=status.state, native_state=status.native_state,
                              checked_at=_now())
        self._registry.save(self.record)
        return status

    def details(self):
        """Refresh status and fetch provider-specific job details.

        Returns:
            details (dict): Adapter details, or an empty dict if unavailable.
        """
        self.status()
        method = getattr(self._handle, "details", None)
        return method() if callable(method) else {}

    def cancel(self):
        """Request remote cancellation; poll status() to confirm its outcome.

        Warning:
            This affects a real remote job. It does not remove downloaded files
            or confirm immediate cancellation.
        """
        # Request only; cancellation is not confirmed until a subsequent status.
        self._handle.cancel()

    def download(self, destination, progress=None):
        """Download a terminated job's outputs without extracting them.

        Args:
            destination (str | Path): New ZIP file path, not an extraction directory.
            progress (Callable | None): Optional callback receiving phase, count, total;
                total may be None while receiving.

        Returns:
            archive (Path): Downloaded archive path.

        Raises:
            ValueError: TACC job is still active or the response archive is invalid.
            FileExistsError: Destination or its .part file already exists.

        Note:
            Failed downloads can leave a .part file for inspection. This does
            not delete remote output or retry automatically.
        """
        if progress is None:
            return self._handle.download(Path(destination))
        return self._handle.download(Path(destination), progress=progress)

    def cleanup_plan(self):
        """Inspect validated remote output locations without deleting them.

        Returns:
            plan (JobCleanupPlan): Exact job-owned paths for supported TACC cleanup.

        Raises:
            ValueError: Ownership, finished state, or supported paths cannot be verified.
        """
        return self._handle.cleanup_plan()

    def cleanup(self, expected):
        """Delete remote outputs after revalidating an inspected cleanup plan.

        Args:
            expected (JobCleanupPlan): Previously reviewed cleanup_plan() result.

        Returns:
            removed (tuple[str, ...]): Deleted remote directory paths.

        Raises:
            ValueError: The plan changed or safe ownership/path checks fail.

        Warning:
            Permanently deletes supported scratch/archive folders and hides the
            remote job. Download needed outputs first. This is not local hiding.
        """
        return self._handle.cleanup(expected)

    def wait(self, poll_interval=30, timeout=None):
        """Poll until succeeded, failed, or cancelled; do not resubmit the job.

        Args:
            poll_interval (float): Seconds between queries; at least one.
            timeout (float | None): Maximum elapsed seconds, or None for no limit.

        Returns:
            status (JobStatus): Terminal status, including failure or cancellation.

        Raises:
            ValueError: Polling interval or timeout is invalid.
            TimeoutError: Timeout elapsed; the remote job is left unchanged.
        """
        if poll_interval < 1 or (timeout is not None and timeout < 0):
            raise ValueError("Polling interval must be >=1 and timeout nonnegative")
        started = time.monotonic()
        while True:
            status = self.status()
            if status.state in {"succeeded", "failed", "cancelled"}:
                return status
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError("Job is still active; no remote action was taken")
            time.sleep(poll_interval)


def connect(job_id, *, platform=None, registry=None):
    """Reconnect to a recorded job; optionally reuse an authenticated adapter.

    Args:
        job_id (str): Cached provider UUID or full registry key.
        platform (Platform | None): Authenticated adapter; None prompts via the stored provider.
        registry (JobRegistry | None): Local registry to search.

    Returns:
        job (TrackedJob): Live-capable handle wrapping the cached record.

    Raises:
        ValueError: Record is missing/ambiguous or authenticated account does not match.

    Note:
        This does not submit a job. Register an uncached existing UUID with add()
        first, or discover it using list_jobs(platform=authenticated_adapter).
    """
    store = registry or JobRegistry()
    record = store.get(job_id)
    target = platform if platform is not None else _CONNECTORS[record.platform](record)
    return TrackedJob(record, target.job(record.id), store)


def record_submission(target, handle, settings, name):
    """Tracking failure must never turn a successful submit into a retry."""
    from collections.abc import Mapping
    method = getattr(target, "tracking_metadata", None)
    if not callable(method):
        return
    try:
        metadata = method()
        if not isinstance(metadata, Mapping):
            return
        resources = asdict(settings) if hasattr(settings, "__dataclass_fields__") else settings
        add(handle.id, platform=metadata["platform"], name=name,
            connection=metadata["connection"], resources=resources)
    except Exception:
        warnings.warn(f"Job {handle.id} was submitted but could not be recorded locally. "
                      "Keep its ID; do not resubmit.", UserWarning, stacklevel=2)
