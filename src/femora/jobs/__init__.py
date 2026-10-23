"""---
title: Jobs & Workflows
icon: material/sitemap-outline
---

``femora.jobs`` organizes model construction, solver runs, and postprocessing
as named tasks in ordered stages. Defining a workflow does not run it. You can
execute it locally or package it for remote submission, then track the remote
job and retrieve its outputs.

## How The Parts Fit Together

```text
Tasks                       Describe individual operations
    |
Workflow                    Organize tasks into ordered stages
    |-- execute()               Run locally or inside an existing allocation
    |-- submit()                Package and submit to a remote platform
            |-- job handle      Check status, cancel, or download outputs
            |-- local registry  Remember jobs for later reconnection
```

A **task** describes one operation, such as building a model or running its
Tcl file. A **stage** groups tasks at one step of the procedure. A **workflow**
arranges those stages in order: for example, build models, run analyses, then
compare results. Each stage finishes before the next begins; tasks within it
run sequentially unless the stage requests parallel execution.

Start with [Workflows](../../concepts/workflows.md) and
[Jobs](../../concepts/jobs.md) for the mental model and worked example.
This reference provides exact
interfaces after those ideas are familiar.

## Choose Your Starting Point

| Area | Purpose | Entry point |
| --- | --- | --- |
| tasks | Describe one Python callback, command, or solver operation | [Python][femora.jobs.tasks.Python], [Command][femora.jobs.tasks.Command], [OpenSees][femora.jobs.tasks.OpenSees], and [TaskContext][femora.jobs.tasks.TaskContext] |
| workflows | Organize tasks into stages and select output artifacts | [Workflow][femora.jobs.workflow.Workflow] |
| execute workflows | Run tasks and inspect their return values and logs | [execute()][femora.jobs.runner.execute] and [RunResult][femora.jobs.runner.RunResult] |
| submit remotely | Authenticate, select resources, validate, and submit | [submit()][femora.jobs.submission.submit] and [TACCPlatform][femora.jobs.platforms.tacc_remote.TACCPlatform] |
| track jobs | Discover jobs, reconnect, inspect status, and download outputs | [list_jobs()][femora.jobs.tracking.list_jobs] and [TrackedJob][femora.jobs.tracking.TrackedJob] |
| bundles and replay | Package declared source/data files and replay trusted archives | [bundle()][femora.jobs.bundle.bundle] and [replay()][femora.jobs.bundle.replay] |
| command line | List jobs and open the interactive terminal tracker | [terminal commands](command-line/index.md) |
| advanced | Extend platform contracts or manage the local registry | [Platform][femora.jobs.platforms.base.Platform] and [JobRegistry][femora.jobs.tracking.JobRegistry] |

## Start With A Task

A task describes one operation; creating it does not execute anything.
``Python`` wraps a callback, ``Command`` describes an executable and arguments,
and ``OpenSees`` describes a Tcl solver run. The runner supplies ``TaskContext``
to Python callbacks so they can access inputs, output paths, and earlier results.

```python
from femora.jobs.tasks import Command
import sys

check = Command("check", [sys.executable, "-c", "print('ready')"])
```

This task can then be placed in a ``Workflow`` stage. See the **tasks** sidebar
group for each task type's inputs and execution requirements.

## Organize Tasks Into A Workflow

Put callbacks and workflow factories at module scope in a Python file. The
main guard prevents process workers or remote imports from running the entry
point again. This example needs no solver and submits no remote work:

```python
from femora import jobs

def write_value(context, value):
    path = context.output_dir / "value.txt"
    path.write_text(str(value), encoding="utf-8")
    return value

def build_workflow():
    workflow = jobs.Workflow("small-example")
    workflow.add("prepare", tasks=[
        jobs.tasks.Python("value", write_value, kwargs={"value": 4}),
    ])
    workflow.outputs("prepare/value/*.txt")
    return workflow

if __name__ == "__main__":
    run = jobs.execute(build_workflow(), workspace="work", cores=1)
    print(run.result("prepare", "value"))
    print(run.manifest)
```

``Python`` runs a callback; ``Command`` runs an executable without a shell;
``OpenSees`` runs an existing workspace-relative Tcl file. A Python task can
build and export that Tcl file in an earlier stage. ``outputs()`` selects files
as artifacts; it does not create them or make unselected remote files available
on your computer.

## Execute Is Not Submit

[backends.TACC][femora.jobs.backends.TACC] launches tasks using an **existing**
Linux Slurm allocation. It does not request nodes or submit a scheduler job.
The local runner supports serial solver execution and concurrent Python tasks;
MPI command/solver tasks require the allocation backend. On TACC, Python
callbacks are restricted to sequential stages with one reserved core.

[TACCPlatform][femora.jobs.platforms.tacc_remote.TACCPlatform] handles remote
staging and submission through an installed Tapis application. Resource settings
belong to [TACCSettings][femora.jobs.platforms.tacc.TACCSettings], not to the
workflow definition. TACC is the current built-in platform; the provider
interfaces allow future adapters without imposing TACC's launcher assumptions.

## Packages, Environments, And Validation

A bundle contains one workflow source file, JSON inputs, and explicitly declared
data files. It does **not** install Python dependencies, copy an entire project,
or provide OpenSees. The execution environment must already supply compatible
software and access to any external input paths. Replay executes Python source;
only use trusted bundles. Keep credentials out of settings, inputs, and bundles.

Preflight checks report known errors and unverified conditions. A valid report
does not guarantee scheduler acceptance, sufficient memory, readable inputs,
or a successful analysis. Submission is not automatic retry: after an uncertain
submission outcome, inspect remote jobs before trying again.

## Track Without Submitting Again

```python
from femora import jobs

# Reads the local cache only; no login or remote refresh.
for record in jobs.list_jobs():
    print(record.id, record.state, record.checked_at)
```

Use ``connect(job_id)`` to reconnect to a cached record and fetch live status;
this may prompt for login. Cancellation requests do not immediately confirm
cancellation. Downloads create a ZIP file rather than extracting it. Remote
cleanup deletes outputs and is separate from hiding a local registry entry.

## Where To Go Next

- **[tasks](Python/index.md)**: start with Python callbacks, then explore command and solver tasks.
- **[workflows](Workflow/index.md)**: organize tasks into stages and select output artifacts.
- **[execute workflows](execute/index.md)**: execution settings, task results, and failure manifests.
- **[submit remotely](submit/index.md)**: packaging, authentication, resources, and remote side effects.
- **[track jobs](tracking/index.md)**: cached records, discovery, and reconnection.
- **[bundles and replay](bundle/index.md)**: portable inputs and trusted-source replay.
- **[command line](command-line/index.md)**: terminal commands and the interactive tracker.
- **[advanced](platforms/index.md)**: platform contracts, validation, and extension points.

For a gradual introduction, read [Workflows](../../concepts/workflows.md), then
[Jobs](../../concepts/jobs.md).
"""

from . import backends, platforms, tasks
from .bundle import bundle, replay
from .runner import ProcessResult, RunResult, WorkflowExecutionError, execute
from .workflow import Workflow
from .submission import submit
from .tracking import JobRecord, JobRegistry, add, connect, list_jobs, sync

list = list_jobs

__all__ = [
    "ProcessResult", "RunResult", "Workflow", "WorkflowExecutionError",
    "backends", "platforms", "bundle", "execute", "replay", "tasks", "submit",
    "JobRecord", "JobRegistry", "add", "connect", "list", "list_jobs", "sync",
]
