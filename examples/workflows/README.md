# Workflow execution

Start with the [step-by-step workflow guide](../../website/docs/concepts/workflows.md)
for task context, workspace folders, return values, and remote submission.
Its small runnable example is `workflow_basics.py`; it needs no solver.

Stages run in order. A parallel stage starts its tasks concurrently and waits
for all of them before continuing. A failed stage prevents subsequent stages;
the other already-running tasks are allowed to finish. Logs and the manifest
remain available after failure.

## Local execution

`tiny_opensees.py` builds two serial Femora cantilevers and compares their
displacements. `local_parallel_stages.py` demonstrates Python callbacks.
Local execution remains the default; it does not launch MPI ranks.

## TACC execution inside an allocation

The TACC backend runs within an existing Slurm compute allocation. It does not
authenticate, submit a Tapis job, allocate nodes, install packages, or download
results. Machine/queue/allocation selection stays outside the workflow.

```python
fm.execute(workflow, workspace="results", backend=fm.jobs.backends.TACC())
```

Or replay a trusted bundle:

```bash
femora jobs replay workflow.zip --workspace results --backend tacc
```

The backend uses `SLURM_NTASKS` as its rank-slot budget (not the machine's CPU
count). `--cores` can reduce that budget but cannot enlarge it. Each external
task launches as `ibrun -n RANKS -o OFFSET task_affinity PROGRAM ...`.
Parallel stages assign contiguous, non-overlapping hostlist offsets; subsequent
stages reuse slots only after the preceding stage completes. This follows
[TACC's concurrent MPI guidance](https://docs.tacc.utexas.edu/hpc/3stampede/launching/).

An OpenSees task declares `ranks=N`. A generic MPI program, including a Python
script using mpi4py, uses:

```python
fm.tasks.Command("mpi-python", ["python", "/shared/path/program.py"],
                 cores=3, ranks=3)
```

Relative command arguments resolve from the task's output directory, not the
workflow source directory. All nodes must see the workspace and software.

Initial limits:

- One CPU per rank; hybrid/threaded task layouts are rejected. External tasks
  receive single-thread settings for OpenMP, MKL, and OpenBLAS.
- Python callbacks run on the coordinator, in sequential stages with `cores=1`.
  Parallel callbacks and mixed callback/MPI parallel stages are rejected.
- Capacity covers CPU rank slots, not memory. The caller must request enough RAM.
- TACC defaults to `OpenSeesMP`, including for one rank; local execution defaults
  to `OpenSees`. A task's `executable`, then `FEMORA_OPENSEES`, override the default.
  There is no fallback to a serial binary if `OpenSeesMP` is missing.
- A workflow may mix the module-loaded default with a custom OpenSees build. Set
  `executable` only on the tasks that need it. A remote custom path must exist and
  be executable on every compute node; each task records the resolved path as
  `FEMORA_JOB|OPENSEES|...` in its `stdout.log`.
- OpenSees tasks source the original Tcl file through a generated error-catching
  driver. Tcl errors emit `FEMORA_JOB|ERROR|` and request a nonzero exit; the runner
  checks that marker even if the launcher returns zero. TACC also checks `getNP`
  before sourcing the model. Failed stages block later stages once running tasks
  finish; this is not MPI-wide immediate cancellation or deadlock recovery.
- An unchecked nonzero return from Tcl `analyze` is not a Tcl exception. Models
  must check it and raise `error` (Femora's analysis exporter does this).
- Bundles contain executable Python: run only trusted inputs under the submitting
  user's permissions, never a privileged shared service account.

## Stampede3 smoke test

Request an allocation from the login node (add `-A YOUR_ALLOCATION` if needed):

```bash
idev -p skx -N 1 -n 5 -m 20
```

On the compute node:

```bash
module load python/3.12.11
module use /work2/08189/amnp95/modules
module load femora opensees/3.8.0
export FEMORA_OPENSEES="$(command -v OpenSeesMP)"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
RUN_DIR=$(mktemp -d "$SCRATCH/femora-mpi.XXXXXX")
cd "$RUN_DIR"
python /work2/08189/amnp95/stampede3/femora-tapis/Femora/examples/workflows/tacc_mpi_smoke.py --bundle mpi.zip
femora jobs replay mpi.zip --workspace results --backend tacc --cores 5
cat results/compare/summary/comparison.txt
```

Expected: `single`, `pair_a`, and `pair_b` report 2, 2, and 3 ranks respectively,
each with displacement `0.001`. The parallel pair uses offsets 0 and 2.
This deliberately tiny test solves an independent spring on each rank. It
validates MPI launching and result collection, not a coupled partitioned Femora
model or parallel solver. A coupled-model test is still required before using
this for large distributed simulations.

The opt-in integration test (requires pytest) runs inside the same allocation:

```bash
FEMORA_TEST_TACC_MPI=1 python -m pytest /path/to/Femora/tests/jobs/test_tacc.py \
    -k real_tacc_bundle --basetemp "$RUN_DIR/pytest-tmp"
```

Use a new `--basetemp` directory: pytest clears it. Unit tests mock the TACC
launcher and are not evidence of a successful cluster run.

## Submit from the same file

With an already registered Femora Tapis app, the MPI example now supports the
public API directly from your local terminal:

```powershell
python examples/workflows/tacc_mpi_smoke.py --submit --app-id amnp95-femora-workflow-stampede3 --allocation DesignSafe-SimCenter
```

These identifiers are for the current pilot; other users must select their own
allocation and an accessible app. The command asks for confirmation and a private
DesignSafe login, validates the `skx-dev` request, packages its own top-level
`build_workflow` function, uploads to a unique user input directory, and submits
one job. No manual ZIP creation or job JSON is needed. Default resources are the
explicit SKX pilot settings (one node, 48 cores, 20 minutes), not a universal TACC
default. Use `--queue` and `--cores-per-node` to select another exposed queue.

Record the UUID. Existing `deploy/tapis/manage.py status` and `download` commands
can monitor this job, or authenticate again and use `TACCPlatform.job(uuid)`.
Do not rerun `--submit` just to check progress. The `--bundle` mode remains available.
See `src/femora/jobs/platforms/README.md` for the platform-independent interface,
factory packaging restrictions, and job-handle methods.

## Check public job handles

Use an existing job UUID to exercise `TACCJob.status()` and `download()` directly:

```powershell
python examples/workflows/tacc_job_handle.py check YOUR_JOB_UUID --output example_outputs/job-handle-output.zip
```

Omit `--output` for status only. The helper prompts privately, never submits a
job, refuses to overwrite downloads, and does not extract the output archive.
No app or allocation settings are required to reconnect to an existing job.

Only for a separate disposable job, cancellation can be tested explicitly:

```powershell
python examples/workflows/tacc_job_handle.py cancel DISPOSABLE_JOB_UUID
python examples/workflows/tacc_job_handle.py check DISPOSABLE_JOB_UUID
```

Cancellation requires typing the full UUID. Terminal jobs are not cancelled.
An accepted cancellation request is not proof of cancellation: check for the
terminal `cancelled` state afterward. The helper does not create the disposable
job automatically. Do not use a valuable simulation for this test.

Create a separate disposable job with:

```powershell
python examples/workflows/tacc_cancel_smoke.py --submit --app-id amnp95-femora-workflow-stampede3 --allocation DesignSafe-SimCenter
```

This explicitly requests one SKX development node (48 cores, ten-minute wall
limit). Two OpenSeesMP ranks wait for five minutes, emitting heartbeats; a later
stage writes `not-cancelled.txt` if allowed to finish. It reserves a whole node,
so cancel promptly. The command requires confirmation and private login, and
prints check/cancel commands containing the new UUID. Do not resubmit to monitor.
For an offline bundle only, use `--bundle example_outputs/tapis-cancel.zip`.

Cancelling while queued tests scheduler cancellation. To test stopping active
work, first check for `running` (Tapis `RUNNING`), then cancel and check again
until `cancelled` (Tapis `CANCELLED`). If it finishes first, that is not a passed
cancellation test. Output archiving may be incomplete after cancellation;
the terminal scheduler/Tapis state is the primary check, not a missing marker.

## Tracking Submitted Jobs

The installed `femora jobs` command uses the same implementation as
`python -m femora.jobs`, which remains supported. After updating an editable
checkout, refresh the command entry point once with `python -m pip install -e .`.
On a cluster, load the Femora environment module before using the command.

The tracker can discover remote Femora jobs after login, even on a computer
with no submission history. Local records are an offline cache, not the only
way to find a job. Successful `fm.submit()` calls also record jobs immediately.
Records contain IDs, account/tenant, resource settings, and cached status, never
passwords or tokens. Each computer has its own cache; override its path with
`FEMORA_JOBS_DB` if needed.

```bash
femora jobs list
femora jobs list --json
femora jobs list --remote
femora jobs track
```

The interactive tracker works in an SSH terminal without a graphical desktop.
Use Up/Down to navigate and Enter for details. L logs in and discovers jobs;
it works even with an empty list. With a selected job it reconnects to that
account. R discovers jobs and refreshes connected accounts, D prompts for a ZIP download path,
C requires the full job UUID before requesting cancellation, Esc returns, and
Q exits. Login tokens stay in memory for this session only. Connected accounts
are polled every 30 seconds; timestamps distinguish cached values from freshly
fetched status. Network operations run in background workers. A cancellation
request is not confirmation; refresh until the provider reports cancellation.

The TACC adapter lists jobs owned by the authenticated account, with pagination.
It identifies Femora by standard `[owner-]femora-workflow-SYSTEM` app IDs, not by
the user-editable job name. For a deployment with a different app ID, specify
it explicitly; app versions do not restrict discovery:

```bash
femora jobs track --app-id my-custom-femora-app
femora jobs list --remote --app-id my-custom-femora-app
```

`--tenant` selects a different Tapis tenant. Discovery does not list arbitrary
Slurm jobs submitted outside Tapis, or jobs belonging to other accounts.
Network failures leave cached records available; a job absent from a remote
listing is not automatically removed or treated as cancelled.

Use `list` or `list --json` in noninteractive/batch sessions instead of `track`.
Older jobs from recognized Femora apps are discovered automatically. You can
also import a known UUID without any remote operation:

```bash
femora jobs add JOB_UUID --name my-study --username MY_USERNAME
femora jobs status JOB_UUID
```

The same tracking functions are available in Python:

```python
fm.jobs.list()                         # Local cached records, no authentication
fm.jobs.list(platform=adapter)         # Discover remote jobs using an authenticated adapter
fm.jobs.sync(adapter)                  # Explicit discovery and cache update (same operation)
job = fm.jobs.connect("JOB_UUID")      # Interactive authentication when needed
job.status()                          # Fetch and cache current status
job.details()                         # Selected remote job details and paths
job.wait(poll_interval=30)             # Wait without submitting another job
job.download("results.zip")
```

Here `adapter` is an authenticated platform created using `TACCPlatform.login(...)`.
Provider adapters implement the
optional `JobDiscovery` contract and return normalized `JobSummary` objects.
Tapis pagination, owner filtering, and app identification stay in the TACC
adapter; the registry and terminal interface do not parse Tapis responses.

Pass `platform=authenticated_adapter` to `connect()` to reuse an existing
connection. Registry errors after submission issue a warning rather than
reporting the remote submission as failed: keep the returned UUID and do not
resubmit. No remote writes occur when simply listing, importing, or opening
the tracker. Download and cancellation happen only on explicit user actions.

## Workflow Composition

A workflow can create inputs, build models, run programs, and postprocess their
results in successive stages. Postprocessing is an ordinary task: users choose
their own functions or programs for plots, movies, summaries, or other outputs.
The workflow runner does not require a particular renderer or postprocessor.

The `files` mapping declares which local files are packaged and where they
appear relative to the remote workspace. It does not automatically include
imported dependencies or install packages. The execution environment must
provide the software used by each task. Never package credentials.

Use `workflow.outputs(...)` to select files for collection using paths or glob
patterns relative to the workspace. This selects existing files; it does not
create them, disable recorders, or delete unselected results. Remote files remain
subject to the execution platform's storage-retention policy.

Keep `fm.submit(...)` under an `if __name__ == "__main__":` guard so importing
the source on the remote machine does not submit another job.
For a complete scientific example, see
[the dynamic-pile workflow](../soil_structure_interaction/dynamic_pile_soil_interaction.py).

### Task Arguments

Python tasks can reuse one function with different keyword arguments:

```python
def build_model(context, boundary):
    drm_file = context.result("input", "drm")
    output_dir = context.output_dir
    # Build the selected case, export model.tcl into output_dir, and return its path.

workflow.add("build", tasks=[
    fm.tasks.Python("fixed", build_model, kwargs={"boundary": "Fixed"}),
    fm.tasks.Python("rayleigh", build_model, kwargs={"boundary": "Rayleigh"}),
    fm.tasks.Python("pml", build_model, kwargs={"boundary": "PML"}),
])
```

The runner calls `build_model(context, boundary="Fixed")` for the first task.
`kwargs` belongs to that task, whereas `context.inputs` contains the inputs
submitted for the whole workflow. Use importable functions and pickleable
argument values; this does not add support for lambdas or closures. Existing
Python tasks without `kwargs` behave as before.

The pile tutorial now writes DRM into `input/drm/drmload.h5drm` and returns that
path to subsequent tasks. Models export into their own `build/<case>` task
folders and return their Tcl paths. Solver tasks explicitly use
`build/<case>/model.tcl`; they do not automatically resolve Python task results.
Recorders write under `build/<case>/results`, and postprocessing reads that layout.
Update the remote Femora installation before submitting workflows using `kwargs`.
