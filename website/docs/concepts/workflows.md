---
title: Workflows and Remote Jobs
icon: material/server-network
---

# Workflows and Remote Jobs

A model describes **what you want to simulate**. A workflow describes **the work
needed to create, run, and process it**. You can use the same workflow idea for
OpenSees, Python calculations, or other programs.

Think about the work in order:

<ol class="workflow-route" aria-label="Workflow stages in execution order">
  <li><span>01 / Input</span><strong>Create inputs</strong><small>Generate the data shared by the models.</small></li>
  <li><span>02 / Build</span><strong>Build models</strong><small>Create and export each simulation.</small></li>
  <li><span>03 / Solve</span><strong>Run simulations</strong><small>Run independent cases together.</small></li>
  <li><span>04 / Compare</span><strong>Process results</strong><small>Produce plots, tables, and movies.</small></li>
</ol>

Each group is a **stage**. Each piece of work inside a stage is a **task**.
Stages run in the order you add them. Tasks within a stage can run one after
another or in parallel. The next stage waits until the current stage finishes.

This guide starts with a tiny calculation so you can understand the folders and
return values without building a finite element model. The complete runnable
example is
[workflow_basics.py](https://github.com/GeotechUW/Femora/blob/main/examples/workflows/workflow_basics.py).

<aside class="workflow-distinction" markdown>
**Two different scales:** [model.process](process.md) orders analysis commands
inside one model. A **workflow** organizes the work around your models: build,
solve, then postprocess.
</aside>

## 1. Start With A Workflow

```python
import femora as fm

workflow = fm.Workflow("workflow-basics")
```

`"workflow-basics"` is a descriptive name. It does **not** choose a folder and
does not start any work. We will add the tasks first and execute them later.

Our small example will do three things:

1. Write the number `4` to a file.
2. Calculate twice and three times that number.
3. Write both answers into a summary.

## 2. Understand The Workspace And Context

The **workspace** is the root folder for one workflow run. It is not a Femora
`Model` object and is not necessarily the folder where you opened your terminal.
Locally, you choose it when calling `fm.execute`. For a remote job, the app
chooses a workspace inside that job's execution directory.

To make paths concrete, imagine the workspace is `/scratch/my-run/results`.
Femora gives each task a folder inside it:

<section class="workspace-view" aria-label="How task folder paths are constructed">
  <header class="workspace-heading"><span class="workspace-kicker">Read the path from outside to inside</span><strong>Workspace / stage / task</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>/scratch/my-run/results/</code><span class="workspace-tag">workspace</span>
      <ul><li><code>input/</code><span class="workspace-tag">stage</span>
        <ul><li><code>number/</code><span class="workspace-tag">task</span></li></ul>
      </li></ul>
    </div>
    <div class="workspace-context"><strong>One shared root, one folder per task</strong><p><code>context.workspace</code><br>/scratch/my-run/results</p><p><code>context.output_dir</code><br>/scratch/my-run/results/input/number</p></div>
  </div>
</section>

This shows the naming rule, not folders created by defining the workflow.
The task folder appears when the runner starts that task.

When a Python task starts, Femora creates a **context object** and passes it as
the first argument to your function. The object tells your function where it is
working and what earlier tasks returned.

```python
def create_input(context):
    ...
```

`context` is just the parameter name we chose. You could name it `ctx` instead:

```python
def create_input(ctx):
    ...
```

Neither `ctx` nor `context` is a special Python keyword. You do not create this
object yourself or import a variable called `ctx`. **The runner supplies it.**

| Expression | Meaning | Example for this task |
| --- | --- | --- |
| `context.workspace` | Shared root folder for this run | `/scratch/my-run/results` |
| `context.output_dir` | This task's own folder | `/scratch/my-run/results/input/number` |
| `context.inputs` | Values passed to the workflow run | `{"number": 4}` |
| `context.results` | Available task return values, grouped by stage and task | Initially no completed task results |
| `context.result("input", "number")` | Look up what that named task returned | Available after the input task completes |

Every task receives a separate context object. They share the same workspace
path and input values, but each has a different `output_dir`. Inputs are copied
into task contexts: changing them inside one task is not a way to send values
to another task. Use return values or files instead.

!!! tip "Use explicit paths"
    Python callbacks should use `context.workspace` and `context.output_dir`,
    not assume their current working directory is the task folder. The runner
    does create `output_dir` before calling your function. External `Command`
    and `OpenSees` programs run with that folder as their working directory.

## 3. Create The Input Task

Define a normal Python function at the top level of your file:

```python
--8<-- "examples/workflows/workflow_basics.py:input"
```

Read it line by line:

1. `context.output_dir / "number.txt"` means a file named `number.txt` inside
   this task's folder. Here `/` joins paths; it is not division.
2. `context.inputs["number"]` gets the value under the dictionary key `"number"`.
   We will pass `{"number": 4}` when running or submitting the workflow.
3. `write_text(...)` creates the file.
4. `return path` gives the path back to Femora so another task can find it.

Now add it to the workflow:

```python
workflow.add("input", tasks=[fm.tasks.Python("number", create_input)])
```

| Part | Meaning |
| --- | --- |
| `"input"` | Stage name; also the stage folder name |
| `tasks=[...]` | The list of tasks belonging to this stage |
| `fm.tasks.Python(...)` | A task that calls a Python function |
| `"number"` | Task name; also its folder name within the stage |
| `create_input` | The function to call later |

Notice `create_input` has **no parentheses** here. We are handing the function
to Femora, not calling it while defining the workflow. Later, the runner calls
`create_input(context)`.

<section class="workspace-view" aria-label="Workspace after the input stage">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 1 / Input finished</span><strong>One task creates one input file</strong><small>Highlighted entries were created in this step.</small></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li class="workspace-new"><code>input/</code>
        <ul><li class="workspace-new"><code>number/</code>
          <ul><li class="workspace-new"><code>number.txt</code><span class="workspace-tag">4</span></li></ul>
        </li></ul>
      </li><li><code>manifest.json</code><span class="workspace-tag">runner status</span></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside create_input(context)</strong><p>Write to<br><code>context.output_dir / "number.txt"</code></p><strong>What the next stage receives</strong><p><code>context.result("input", "number")</code><br>returns the path to <code>input/number/number.txt</code>, not the number itself.</p></div>
  </div>
</section>

The runner also writes <code>manifest.json</code> after the stage finishes.
The input function creates only <code>number.txt</code>.

There is no automatically created `input/drm` directory. If the task were named
`drm`, its folder would be `input/drm`. Names you give stages and tasks determine
these folders.

## 4. Reuse A Function For Two Tasks

```python
--8<-- "examples/workflows/workflow_basics.py:calculate"
```

`context.result("input", "number")` retrieves the **return value** of the earlier
task. In this example, that value is a `Path` pointing to `number.txt`. Femora
does not copy the file into the new task's folder; both tasks can read it from
the shared workspace.

Add two tasks that use this same function:

```python
workflow.add(
    "calculate",
    tasks=[
        fm.tasks.Python("double", calculate, kwargs={"factor": 2}),
        fm.tasks.Python("triple", calculate, kwargs={"factor": 3}),
    ],
)
```

`kwargs={"factor": 2}` tells Femora to call `calculate(context, factor=2)` for
the `double` task. The other task calls it with `factor=3`.

**Use `inputs` for values common to the run, and `kwargs` for values specific to
one task.** This lets you reuse a model-building function with different
boundaries, material properties, or partition counts without creating wrapper
functions for every case.

These tasks run sequentially because `parallel` defaults to `False`. Watch
the workspace grow as each task runs; the input file stays in its original folder.

<section class="workspace-view" aria-label="Workspace after the double task">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 2 / First calculation finished</span><strong>double reads the input and writes its answer</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li><code>input/</code><ul><li><code>number/</code><ul><li><code>number.txt</code><span class="workspace-tag">4 / read here</span></li></ul></li></ul></li>
      <li class="workspace-new"><code>calculate/</code><ul><li class="workspace-new"><code>double/</code><ul><li class="workspace-new"><code>value.txt</code><span class="workspace-tag">8.0 / new</span></li></ul></li></ul></li>
      <li><code>manifest.json</code></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside calculate(context, factor=2)</strong><p><code>context.workspace</code><br>still points to the same root.</p><p><code>context.output_dir</code><br>now points to <code>workspace/calculate/double</code>.</p><p>The function reads <code>4</code>, writes <code>8.0</code>, and returns the number <code>8.0</code>.</p></div>
  </div>
</section>

<section class="workspace-view" aria-label="Workspace after the triple task">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 3 / Second calculation finished</span><strong>triple gets a different task folder</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li><code>input/</code><ul><li><code>number/</code><ul><li><code>number.txt</code><span class="workspace-tag">4 / read here</span></li></ul></li></ul></li>
      <li><code>calculate/</code><ul><li><code>double/</code><ul><li><code>value.txt</code><span class="workspace-tag">8.0 / kept</span></li></ul></li>
      <li class="workspace-new"><code>triple/</code><ul><li class="workspace-new"><code>value.txt</code><span class="workspace-tag">12.0 / new</span></li></ul></li></ul></li>
      <li><code>manifest.json</code></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside calculate(context, factor=3)</strong><p><code>context.output_dir</code><br>is <code>workspace/calculate/triple</code>.</p><p>It reads the same input file, writes its own <code>value.txt</code>, and returns <code>12.0</code>.</p><p>The two files have the same name but different parent folders, so they do not overwrite each other.</p></div>
  </div>
</section>

Each calculation also returns a number. There are now two separate ways to
access its output: read `value.txt`, or retrieve the returned number.

!!! note "Return values are not folders"
    `context.result(...)` does not list files or automatically return
    `output_dir`. It returns exactly what your function returned. If your
    function has no `return`, its result is `None`, even if it wrote many files.
    Return values and arguments must be serializable by Python's pickle
    machinery. Return a file path rather than a large in-memory model or array.

## 5. Write A Report After Both Calculations

```python
--8<-- "examples/workflows/workflow_basics.py:report"
```

This time `context.result(...)` retrieves numbers, not file paths, because
`calculate` returns `value`.

```python
workflow.add("report", tasks=[fm.tasks.Python("summary", write_report)])
```

<section class="workspace-view" aria-label="Workspace after the report stage">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 4 / Report finished</span><strong>The report joins the two returned answers</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li><code>input/</code><ul><li><code>number/</code><ul><li><code>number.txt</code></li></ul></li></ul></li>
      <li><code>calculate/</code><ul><li><code>double/</code><ul><li><code>value.txt</code></li></ul></li><li><code>triple/</code><ul><li><code>value.txt</code></li></ul></li></ul></li>
      <li class="workspace-new"><code>report/</code><ul><li class="workspace-new"><code>summary/</code><ul><li class="workspace-new"><code>summary.txt</code><span class="workspace-tag">new</span></li></ul></li></ul></li>
      <li><code>manifest.json</code></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside write_report(context)</strong><p><code>context.output_dir</code><br>is <code>workspace/report/summary</code>.</p><p><code>context.result("calculate", "double")</code><br>gives <code>8.0</code>.</p><p><code>context.result("calculate", "triple")</code><br>gives <code>12.0</code>.</p><p>It uses these return values directly; it does not need to read the two <code>value.txt</code> files.</p></div>
  </div>
</section>

`summary.txt` contains:

```text
double: 8.0
triple: 12.0
```

The runner writes `manifest.json` with execution status, resource reservations,
errors if any, and the selected output file paths. It is not a replacement for
your task return values or simulation recorder files.

## 6. Select The Files To Return

```python
workflow.outputs("report/summary/summary.txt", "calculate/*/value.txt")
```

These are **paths relative to the workspace**, not your local checkout. This
line selects the summary and both calculation files for the result package.

| Pattern | Selects |
| --- | --- |
| `report/summary/summary.txt` | One exact file |
| `calculate/*/value.txt` | `value.txt` in each task folder under `calculate` |
| `**/stdout.log` | External-program logs at any depth in the workspace |
| `build/*/results/**/*` | Files recursively inside each case's raw results folder |

`*` matches within one path component. `**` matches recursively through folders.
`outputs(...)` does not create files and does not delete unselected files. It
selects existing files; remote retention and archiving are separate concerns.
For large simulations, select plots, movies, tables, and logs instead of all
raw recorder data unless you need to download it.

## 7. Put The Workflow Together

Keep the functions above and this factory in **the same Python file**:

```python
--8<-- "examples/workflows/workflow_basics.py:workflow"
```

Calling `build_workflow()` only describes the work. It does not call the task
functions. To try the small example on your own machine, the file ends with:

```python
--8<-- "examples/workflows/workflow_basics.py:execute"
```

Run it from your Femora checkout:

```bash
python examples/workflows/workflow_basics.py
```

Here `workspace="example_outputs/workflow_basics"` chooses a folder relative to
your terminal's current directory. Femora resolves it to an absolute path
before passing it to tasks. The example performs tiny Python calculations;
it requires no solver or remote login.

## 8. Run Independent Tasks In Parallel

Use `parallel=True` only when tasks in that stage can run independently.
For example, after building three Tcl models:

```python
workflow.add(
    "solve",
    parallel=True,
    tasks=[
        fm.tasks.OpenSees("fixed", "build/fixed/model.tcl", ranks=8),
        fm.tasks.OpenSees("rayleigh", "build/rayleigh/model.tcl", ranks=16),
        fm.tasks.OpenSees("pml", "build/pml/model.tcl", ranks=16),
    ],
)
```

All three start in that stage, and the following stage waits for all three.
The Tcl paths point into the shared workspace. The models must already have
been exported with partitioning appropriate for their requested rank counts;
`ranks=16` does not repartition a model.

This stage needs `8 + 16 + 16 = 40` rank slots simultaneously. In the current
TACC backend each MPI rank uses one CPU slot. With a 48-slot allocation, eight
slots remain unused during this stage. The backend assigns non-overlapping
`ibrun` offsets and reuses the allocation for subsequent stages.

An `OpenSees` task returns a `ProcessResult`, not the model's displacement:

```python
solve = context.result("solve", "fixed")
log_file = solve.log
solver_task_folder = solve.output_dir
```

### Use A Custom OpenSees Build For One Task

The Stampede3 app loads its tested OpenSees module as the default. Override it
only for a model that requires a personalized build:

```python
workflow.add(
    "solve",
    parallel=True,
    tasks=[
        fm.tasks.OpenSees(
            "standard",
            "build/standard/model.tcl",
            ranks=16,
        ),
        fm.tasks.OpenSees(
            "custom",
            "build/custom/model.tcl",
            ranks=16,
            executable="/work2/YOUR_PROJECT/YOUR_USER/opensees/bin/OpenSeesMP",
        ),
    ],
)
```

The task override takes precedence over `FEMORA_OPENSEES` and the module-loaded
`OpenSeesMP`; other tasks keep using the default. The custom executable must be
visible and executable on every allocated node and must support the requested
MPI launch. The resolved path is written to that task's `stdout.log` as
`FEMORA_JOB|OPENSEES|...`.

Your postprocessor still reads the recorder files at the locations chosen when
you built the model. Those locations need not be inside the solver task folder.

!!! warning "Do not depend on a sibling parallel task"
    Parallel tasks do not see each other's return values while running. Put
    work that needs both answers in a later stage. In a sequential stage, a
    later task can access earlier completed tasks in that same stage.

### Python Parallelism And Other Programs

`Python(..., cores=5)` reserves resources; it does **not** automatically make
your function run five times or use five CPUs. Your Python code must implement
its own parallelism.

The local runner supports parallel Python callbacks. The current TACC backend
requires callbacks to use sequential stages and `cores=1`. For an MPI-aware
Python script on TACC, use a `Command` task:

```python
workflow.add(
    "mixed",
    parallel=True,
    tasks=[
        fm.tasks.OpenSees("model", "build/model/model.tcl", ranks=8),
        fm.tasks.Command(
            "python-analysis",
            ["python", "../../scripts/mpi_analysis.py"],
            cores=5,
            ranks=5,
        ),
    ],
)
```

This reserves 13 slots. The command runs from `workspace/mixed/python-analysis`,
so `../../scripts/mpi_analysis.py` reaches `workspace/scripts/mpi_analysis.py`.
That script must be staged or created earlier and actually support MPI, for
example using `mpi4py`. An ordinary Python script will otherwise run five copies.
MPI execution requires the TACC allocation backend, not the local runner.

## 9. Submit The Same Workflow To TACC

Replace the small example's final `fm.execute(...)` block with:

```python
if __name__ == "__main__":
    job = fm.submit(
        function=build_workflow,
        platform="tacc",
        settings={
            "app_id": "YOUR_REGISTERED_FEMORA_APP_ID",
            "system": "stampede3",
            "queue": "skx-dev",
            "allocation": "YOUR_ALLOCATION",
            "nodes": 1,
            "cores_per_node": 48,
            "minutes": 20,
        },
        inputs={"number": 4},
    )
    print(f"Job UUID: {job.id}")
```

Use a Femora Tapis app you can access and your own allocation. These settings
belong to the **TACC adapter**, not the workflow. Other platforms can provide
their own adapters and settings without changing how you define the tasks;
currently the named remote provider is `"tacc"`.

Here is what happens:

1. Your computer packages the Python source file and `inputs` into a bundle.
   It does not run `build_workflow` or build large models first.
2. Femora prompts for your DesignSafe login, uploads the bundle, and submits
   the job through Tapis.
3. Once the scheduler starts the job, the app loads the remote environment and
   replays the bundle. It calls `build_workflow` there.
4. The remote runner executes the stages. The example creates `number.txt`,
   `value.txt`, and `summary.txt` **on the cluster**.
5. The app packages the selected outputs for download.

Keep `fm.submit` inside `if __name__ == "__main__":`. That guard prevents the
remote import of your source from submitting another job. Keep task functions
and the factory at the top level, outside the guard. Use named functions and
`kwargs`, not lambdas or nested functions.

!!! note "Environments are separate from input files"
    Bundling source does not install Python packages or include OpenSees. The
    remote environment must already provide the required dependencies. Do not
    put passwords or tokens into source, input dictionaries, or uploaded files.

### Sending An Existing File

The tiny example creates its input remotely, so it needs no uploaded data file.
When your workflow needs a file that already exists on your computer, add a
`files` mapping to `fm.submit`:

```python
from pathlib import Path

files={
    "motions/input.acc": Path(__file__).with_name("input.acc"),
}
```

This is a dictionary entry, written as **destination: source**:

| Side | Meaning |
| --- | --- |
| `"motions/input.acc"` | Destination relative to the remote workspace |
| `Path(__file__).with_name("input.acc")` | Existing local file next to your workflow Python file |

`__file__` refers to your Python source file. `with_name(...)` replaces its
filename while keeping its directory. This avoids relying on the folder where
you opened the terminal.

<section class="workspace-view" aria-label="Workspace after staging an uploaded file">
  <header class="workspace-heading"><span class="workspace-kicker">Before the first task / Optional uploaded input</span><strong>The app places your file in the shared workspace</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code><ul><li class="workspace-new"><code>motions/</code><ul><li class="workspace-new"><code>input.acc</code><span class="workspace-tag">uploaded</span></li></ul></li></ul></div>
    <div class="workspace-context"><strong>Any task can read this file</strong><p><code>context.workspace / "motions/input.acc"</code></p><p>This is not a task folder. It comes from the destination you chose in <code>files</code>.</p></div>
  </div>
</section>

Your remote function reads it using `context.workspace / "motions/input.acc"`.
It does not use the original Windows path. Explicitly include additional
scripts or data files your workflow needs; imports are not automatically
collected into the bundle. Only replay bundles from sources you trust: they
execute Python code.

## 10. Track And Download The Job

Submission returns a job handle immediately; it does not wait for the run to
finish. To reconnect later, even from another computer, open:

```bash
femora jobs track
```

Press **L** to log in and discover your Femora Tapis jobs, use the arrow keys to
select a job, and press **Enter** for details. Press **R** to refresh its status
or **D** to download completed outputs. Downloaded archives are not automatically
extracted. Do not resubmit the workflow merely to check progress.

For a non-interactive listing:

```bash
femora jobs list --remote
```

Without `--remote`, the list uses your local tracking cache. In Python,
`fm.jobs.list()` reads that cache; supplying an authenticated platform to
`fm.jobs.list(platform=platform)` discovers remote jobs.

If a stage fails, later stages do not run. Already-running tasks in a parallel
stage are allowed to finish. Check the manifest and program logs; fixing the
source does not change an already submitted job.

## Apply This To A Real Model

The [dynamic pile-soil example](../examples/dynamic-pile-soil-interaction.md)
uses these same ideas: one task creates the DRM input, a sequential stage builds
three models, a parallel stage runs them with 8, 16, and 16 MPI ranks, and a final
task creates response plots and a comparison movie on the cluster.

The useful habit is to ask three questions for each task: **What does it need?
Where does it write? What does it return?** Once those are clear, the workflow
is simply the order in which that work should happen.
