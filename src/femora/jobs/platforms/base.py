"""Provider-neutral contracts; no scheduler or authentication assumptions."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Protocol, TypeVar

from ..workflow import Workflow

Settings = TypeVar("Settings", contravariant=True)


@dataclass(frozen=True)
class ValidationIssue:
    """One preflight finding, safe to show without exposing SDK request details.

    Attributes:
        severity (str): error blocks submission; warning advises; unverified marks an unchecked condition.
        field (str): Resource or configuration field concerned.
        message (str): Human-readable explanation.
    """

    __doc_controls__ = {"members": []}
    severity: Literal["error", "warning", "unverified"]
    field: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """Preflight findings; valid does not mean every condition was verified.

    Attributes:
        issues (tuple[ValidationIssue, ...]): Errors, warnings, and unverified checks.
    """

    __doc_controls__ = {"summary": True, "members": ["errors", "valid", "raise_for_errors"]}
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self):
        """Blocking findings only, as a tuple of ValidationIssue objects."""
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def valid(self) -> bool:
        """No known errors; unverified checks can still remain."""
        return not self.errors

    def raise_for_errors(self) -> None:
        """Raise ValueError containing blocking field/message pairs, if any.

        Raises:
            ValueError: At least one issue has error severity.
        """
        if self.errors:
            raise ValueError("\n".join(f"{i.field}: {i.message}" for i in self.errors))


@dataclass(frozen=True)
class JobStatus:
    """Provider-neutral status plus the original provider state.

    Attributes:
        state (str): pending, running, succeeded, failed, cancelled, or unknown.
        native_state (str): Unmodified provider status name.
        message (str): Optional provider explanation.

    Note:
        A cached JobRecord is not a live JobStatus query. Terminal failure or
        cancellation is an outcome, not an exception from wait().
    """

    __doc_controls__ = {"members": []}
    state: Literal["pending", "running", "succeeded", "failed", "cancelled", "unknown"]
    native_state: str
    message: str = ""


class JobHandle(Protocol):
    """Minimum interface returned by a submission platform.

    Implementations own authentication and remote operations. Use concrete
    handles returned by submit() rather than constructing this protocol.
    """

    __doc_controls__ = {"summary": True, "members": ["id", "status", "cancel", "download"]}
    @property
    def id(self) -> str:
        """Provider-assigned job identifier."""
        ...

    def status(self) -> JobStatus:
        """Fetch current normalized and native remote states."""
        ...

    def cancel(self) -> None:
        """Request remote cancellation; query status to confirm the outcome."""
        ...

    def download(self, destination: Path) -> Path:
        """Download outputs to destination using the provider's archive convention.

        Args:
            destination (Path): Local output path; TACC expects a new ZIP filename.

        Returns:
            saved (Path): Local archive path.
        """
        ...


@dataclass(frozen=True)
class JobSummary:
    """Safe provider-neutral discovery data, not a raw SDK response.

    Attributes:
        id (str): Provider job identifier.
        name (str): Job display name.
        submitted_at (str): Provider submission timestamp.
        status (JobStatus): Normalized and native states.
        connection (dict): Safe tenant/account/app metadata without credentials.
        resources (dict): Normalized scheduler resource fields.
    """

    __doc_controls__ = {"members": []}

    id: str
    name: str
    submitted_at: str
    status: JobStatus
    connection: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)


class JobDiscovery(Protocol):
    """Optional adapter capability; discovery is read-only."""

    __doc_controls__ = {"summary": True, "members": ["list_jobs", "tracking_metadata"]}

    def list_jobs(self) -> Iterable[JobSummary]:
        """Yield safe summaries of jobs visible to the authenticated user."""
        ...

    def tracking_metadata(self) -> dict:
        """Return platform and safe connection metadata for local reconnection."""
        ...


class PlatformValidator(Protocol[Settings]):
    """Read-only preflight interface for a concrete workflow and provider settings."""

    __doc_controls__ = {"summary": True, "members": ["validate"]}

    def validate(self, workflow: Workflow, settings: Settings) -> ValidationReport:
        """Inspect the workflow and resources without staging or submitting.

        Args:
            workflow (Workflow): Actual staged task definitions.
            settings (Settings): Provider-specific resource request.

        Returns:
            report (ValidationReport): Findings including unchecked conditions.
        """
        ...


class Platform(PlatformValidator[Settings], Protocol[Settings]):
    """Future submission implementations must validate before remote writes.

    Bundle is a trusted workflow archive. Credentials belong to the provider
    instance, never settings or the bundle. This is not an execution backend.

    Implement the inherited [validate()][femora.jobs.platforms.base.PlatformValidator.validate]
    contract as well as submit().
    """

    __doc_controls__ = {"summary": True, "members": ["submit"]}

    def submit(self, bundle: Path, settings: Settings) -> JobHandle:
        """Validate and stage a trusted bundle, then submit remote work.

        Args:
            bundle (Path): Existing trusted workflow archive.
            settings (Settings): Provider-specific resources.

        Returns:
            job (JobHandle): Handle for subsequent monitoring and retrieval.

        Warning:
            This operation writes remote files and submits a real job. Adapters
            should distinguish validation failures from uncertain submission outcomes.
        """
        ...
