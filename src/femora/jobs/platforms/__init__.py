"""---
title: Platform Interfaces
icon: material/puzzle-outline
---

Submission platforms authenticate, validate requests, stage trusted bundles,
and return job handles. They are distinct from execution backends, which launch
tasks inside an existing allocation.

Most callers should use [submit()][femora.jobs.submission.submit]. The current
built-in adapter is [TACCPlatform][femora.jobs.platforms.tacc_remote.TACCPlatform];
[TACCSettings][femora.jobs.platforms.tacc.TACCSettings] describes its resources.
No AWS or Azure adapter is currently provided.

## Extension Contracts

- [Platform][femora.jobs.platforms.base.Platform]: read-only validation followed
  by validated remote submission. Authentication belongs to the adapter, not settings.
- [PlatformValidator][femora.jobs.platforms.base.PlatformValidator]: preflight
  without remote writes.
- [JobHandle][femora.jobs.platforms.base.JobHandle]: job identity, status,
  cancellation requests, and output retrieval.
- [JobDiscovery][femora.jobs.platforms.base.JobDiscovery]: optional discovery
  and safe reconnection metadata for the local registry.
- [ValidationReport][femora.jobs.platforms.base.ValidationReport]: blocking
  errors, warnings, and explicitly unverified conditions.

An adapter should not imply that a successful preflight guarantees execution.
Separate known rejection from uncertain submission outcomes, and never retry a
remote write blindly. Keep credentials out of bundles and persisted records.
"""

from .base import JobDiscovery, JobHandle, JobStatus, JobSummary, Platform, PlatformValidator, ValidationIssue, ValidationReport
from .tacc import QueueLimits, SubmissionValidationError, TACCSettings, TACCSubmitter, TACCValidator
from .tacc_remote import RemoteSubmissionError, TACCJob, TACCPlatform

__all__ = ["JobDiscovery", "JobHandle", "JobStatus", "JobSummary", "Platform", "PlatformValidator", "ValidationIssue",
           "ValidationReport", "QueueLimits", "TACCSettings", "TACCValidator",
           "TACCSubmitter", "SubmissionValidationError", "TACCPlatform", "TACCJob", "RemoteSubmissionError"]
