---
title: Workflows
icon: material/source-branch
---

# Workflows

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

One operation, such as writing a file or starting a solver, is a **task**.
A **stage** groups tasks at one point in the procedure: for example, build all
models before starting their analyses. A **workflow** is the ordered collection
of those stages. Each box above represents a stage and can contain several tasks.

Stages run in the order you add them. Tasks within a stage can run one after
another or in parallel. The next stage waits until the current stage finishes.

A task can represent work done in Python, a model solved by OpenSees, or an
external program started with a command. These are examples of operations,
not different levels of the workflow. Browse the **tasks** group in the
[API reference](../reference/jobs/index.md) for available task definitions and
their options. We will introduce the task objects as the example needs them.

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

Think of the workflow as a **container for an ordered procedure**. It starts
empty; we will add stages and their tasks to it as we work through the example.
The name `"workflow-basics"` identifies the procedure, not its output directory.
Nothing runs until we execute the workflow. See
[Workflow](../reference/jobs/Workflow/index.md) for its complete interface.

Our small example will do three things:

1. Write the number `4` to a file.
2. Calculate twice and three times that number.
3. Write both answers into a summary.

## 2. Understand The Workspace And Context

The **workspace** is the root folder for one workflow run. It is not a Femora
`Model` object and is not necessarily the folder where you opened your terminal.
Locally, you choose it when calling `fm.execute`. For a remote job, the app
chooses a workspace inside that job's execution directory.

Our first stage will be called `prepare` because it prepares the shared data.
Its task will be called `write_base_value` because it writes the value used by
the calculations. These are names we choose, not reserved Femora keywords.
For a run whose root is represented below as `workspace/`, their folders are:

<section class="workspace-view" aria-label="How task folder paths are constructed">
  <header class="workspace-heading"><span class="workspace-kicker">Read the path from outside to inside</span><strong>Workspace / stage / task</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code><span class="workspace-tag">workspace</span>
      <ul><li><code>prepare/</code><span class="workspace-tag">stage</span>
        <ul><li><code>write_base_value/</code><span class="workspace-tag">task</span></li></ul>
      </li></ul>
    </div>
    <div class="workspace-context"><strong>One shared root, one folder per task</strong><p><code>context.workspace</code><br>workspace/</p><p><code>context.output_dir</code><br>workspace/prepare/write_base_value/</p></div>
  </div>
</section>

This shows the naming rule, not folders created by defining the workflow.
The task folder appears when the runner starts that task.

When a Python task starts, Femora creates a **context object** and passes it as
the first argument to your function. The object tells your function where it is
working and what earlier tasks returned.

The runner supplies a [TaskContext](../reference/jobs/TaskContext/index.md).
We do not construct it when defining the callback. Its role is to connect the
function to this particular execution:

| Expression | Meaning | Example for this task |
| --- | --- | --- |
| `context.workspace` | Shared root folder for this run | `workspace/` |
| `context.output_dir` | This task's own folder | `workspace/prepare/write_base_value/` |
| `context.inputs` | Values passed to the workflow run | `{"base_value": 4}` |
| `context.results` | Available task return values, grouped by stage and task | Initially no completed task results |
| `context.result("prepare", "write_base_value")` | Look up what that named task returned | A file path, available to later work after preparation completes |

`context.inputs["base_value"]` is **configuration supplied for the run**.
`context.result("prepare", "write_base_value")` is **output returned by completed
work**. They are not two ways of asking for the same thing. In this example,
the configuration is the number `4`; the preparation task turns it into a file
and returns that file's path.

Every task receives a separate context object. They share the same workspace
path and input values, but each has a different `output_dir`. Inputs are copied
into task contexts: changing them inside one task is not a way to send values
to another task. Use return values or files instead.

!!! tip "Use explicit paths"
    Python callbacks should use `context.workspace` and `context.output_dir`,
    not assume their current working directory is the task folder. The runner
    does create `output_dir` before calling your function. External `Command`
    and `OpenSees` programs run with that folder as their working directory.

## 3. Add A Preparation Stage And Its Task

Define a normal Python function at the top level of your file:

```python
--8<-- "examples/workflows/workflow_basics.py:input"
```

Read it line by line:

1. `context.output_dir` locates this task's own directory, so it writes
   `base_value.txt` without conflicting with other tasks.
2. `context.inputs["base_value"]` reads the run configuration. We will supply
   `inputs={"base_value": 4}` at execution time.
3. `write_text(...)` stores that value in the file.
4. `return path` makes the file path available to later work through
   `context.result(...)`.

Now add it to the workflow:

```python
workflow.add("prepare", tasks=[fm.tasks.Python("write_base_value", write_base_value)])
```

| Part | Meaning |
| --- | --- |
| `"prepare"` | Stage name; also the stage folder name |
| `tasks=[...]` | The list of tasks belonging to this stage |
| `fm.tasks.Python(...)` | A task that calls a Python function |
| `"write_base_value"` | Task name; also its folder name within the stage |
| `write_base_value` | The function to call later |

Notice `write_base_value` has **no parentheses** here. We are handing the function
to Femora, not calling it while defining the workflow. Later, the runner calls
`write_base_value(context)`.

This line also introduces the first **stage boundary**. The stage is named
`prepare`, and its task is named `write_base_value`. Everything in a later stage waits for
this stage to finish. There is no separate stage object to construct here;
`workflow.add()` records the named group of tasks.

<section class="workspace-view" aria-label="Workspace after preparation">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 1 / Preparation finished</span><strong>One task creates the shared data file</strong><small>Highlighted entries were created in this step.</small></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li class="workspace-new"><code>prepare/</code>
        <ul><li class="workspace-new"><code>write_base_value/</code>
          <ul><li class="workspace-new"><code>base_value.txt</code><span class="workspace-tag">4</span></li></ul>
        </li></ul>
      </li><li><code>manifest.json</code><span class="workspace-tag">runner status</span></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside write_base_value(context)</strong><p>Write to<br><code>context.output_dir / "base_value.txt"</code></p><strong>What the next stage receives</strong><p><code>context.result("prepare", "write_base_value")</code><br>returns the path to <code>prepare/write_base_value/base_value.txt</code>, not the number itself.</p></div>
  </div>
</section>

The runner also writes <code>manifest.json</code> after the stage finishes.
The input function creates only <code>base_value.txt</code>.

There is no fixed list of stage folders created in advance. Names you give
stages and tasks determine these directories, and they appear as tasks start.

## 4. Reuse A Function For Two Tasks

```python
--8<-- "examples/workflows/workflow_basics.py:calculate"
```

`context.result("prepare", "write_base_value")` retrieves the **return value** of the earlier
task. In this example, that value is a `Path` pointing to `base_value.txt`. Femora
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
      <ul><li><code>prepare/</code><ul><li><code>write_base_value/</code><ul><li><code>base_value.txt</code><span class="workspace-tag">4 / read here</span></li></ul></li></ul></li>
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
      <ul><li><code>prepare/</code><ul><li><code>write_base_value/</code><ul><li><code>base_value.txt</code><span class="workspace-tag">4 / read here</span></li></ul></li></ul></li>
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
workflow.add("report", tasks=[fm.tasks.Python("write_summary", write_report)])
```

<section class="workspace-view" aria-label="Workspace after the report stage">
  <header class="workspace-heading"><span class="workspace-kicker">Snapshot 4 / Report finished</span><strong>The report joins the two returned answers</strong></header>
  <div class="workspace-body">
    <div class="workspace-tree"><code>workspace/</code>
      <ul><li><code>prepare/</code><ul><li><code>write_base_value/</code><ul><li><code>base_value.txt</code></li></ul></li></ul></li>
      <li><code>calculate/</code><ul><li><code>double/</code><ul><li><code>value.txt</code></li></ul></li><li><code>triple/</code><ul><li><code>value.txt</code></li></ul></li></ul></li>
      <li class="workspace-new"><code>report/</code><ul><li class="workspace-new"><code>write_summary/</code><ul><li class="workspace-new"><code>summary.txt</code><span class="workspace-tag">new</span></li></ul></li></ul></li>
      <li><code>manifest.json</code></li></ul>
    </div>
    <div class="workspace-context"><strong>Inside write_report(context)</strong><p><code>context.output_dir</code><br>is <code>workspace/report/write_summary</code>.</p><p><code>context.result("calculate", "double")</code><br>gives <code>8.0</code>.</p><p><code>context.result("calculate", "triple")</code><br>gives <code>12.0</code>.</p><p>It uses these return values directly; it does not need to read the two <code>value.txt</code> files.</p></div>
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
workflow.outputs("report/write_summary/summary.txt", "calculate/*/value.txt")
```

These are **paths relative to the workspace**, not your local checkout. This
line selects the summary and both calculation files for the result package.

| Pattern | Selects |
| --- | --- |
| `report/write_summary/summary.txt` | One exact file |
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

The main guard is important: process workers import the module to find the
callbacks. It prevents that import from starting another execution. Keep the
callbacks and `build_workflow()` at module scope, outside the guard.

`fm.execute()` returns a [RunResult](../reference/jobs/RunResult/index.md).
`run.result("report", "write_summary")` is the reporting callback's return value,
which is a `Path` in this example. `run.manifest` identifies the execution
record, and `run.artifacts` lists files selected by `workflow.outputs(...)`.
Use a fresh workspace for another run; execute does not automatically clear
an existing directory or resume a previous execution.

???+ note "A failed execution still has diagnostics"
    A task failure stops later stages. The runner raises
    [WorkflowExecutionError](../reference/jobs/WorkflowExecutionError/index.md)
    with a partial run result in `error.run`; inspect its manifest and the task
    logs. Files already written are not rolled back or automatically retried.
    A successful process exit also does not certify numerical accuracy.

## 8. Inspect The Workspace And Diagnose A Failure

After a successful run, our example has this layout:

```text
example_outputs/workflow_basics/
    prepare/
        write_base_value/base_value.txt    configuration written as shared data
    calculate/
        double/value.txt                  first calculation's saved value
        triple/value.txt                  second calculation's saved value
    report/
        write_summary/summary.txt          report combining both answers
    manifest.json                         execution record written by the runner
```

The stage/task folders are created as tasks start; the callbacks create the
files inside them. There is no automatic `results/`, `logs/`, or `errors/`
directory. For a finite-element task, recorder files go where the model's
recorder configuration says, not necessarily in the solver task directory.

External `Command` and `OpenSees` tasks also get `stdout.log` in their task
directory, combining the program's stdout and stderr. An OpenSees task gets an
internal `.femora-driver.tcl` launcher there as well. Python callback tasks do
**not** automatically get a `stdout.log`; write any task-specific diagnostic
files explicitly. Their exceptions are captured in the execution record.

### What The Manifest Records

Open `run.manifest` as JSON. Its top-level entries are:

| Entry | Meaning |
| --- | --- |
| `workflow` | The workflow's descriptive name |
| `backend` | Execution strategy used for this run, such as `local` |
| `capacity` | Validated core-reservation budget used by the runner |
| `stages` | Records grouped by stage, then task name |
| `artifacts` | Workspace-relative file paths matching `workflow.outputs(...)` |

A task record has `status`, reserved `cores`, and an `offset` for allocation
launches (`null` locally). Failed tasks also have an `error` string. Status
values describe runner activity, not engineering accuracy. The manifest does
not contain callback return values, response histories, or a complete saved
Python exception/traceback.

The runner writes the manifest after a stage completes, or when its execution
validation rejects a stage. It is not a continuously updated scheduler log.
If the process is killed before a write, it may be absent or reflect only
earlier completed stages.

### Try A Controlled Failure

Keep the same functions and factory, but replace the execution block for a
separate test run with this one. The deliberately invalid value cannot be
converted to a number by `calculate()`:

```python
import json
from femora.jobs import WorkflowExecutionError

if __name__ == "__main__":
    try:
        fm.execute(
            build_workflow(), workspace="example_outputs/workflow_failure",
            inputs={"base_value": "invalid"}, cores=1,
        )
    except WorkflowExecutionError as error:
        print(str(error))
        print("Execution record:", error.run.manifest)
        record = json.loads(error.run.manifest.read_text(encoding="utf-8"))
        print(record["stages"]["calculate"]["double"])
```

The error message identifies the stage and task, followed by the callback's
message. In the manifest, the relevant part is:

```json
{
  "prepare": {
    "write_base_value": {"status": "finished", "cores": 1, "offset": null}
  },
  "calculate": {
    "double": {
      "status": "failed",
      "cores": 1,
      "offset": null,
      "error": "could not convert string to float: 'invalid'"
    }
  }
}
```

This is the `stages` section, not the entire file. Preparation succeeded and
its data file remains. The `double` task's directory exists, but its `value.txt`
was never written. Because this stage is sequential, `triple` was not started;
the report stage was not reached, so neither has a record or a new task folder.
Already-started siblings in a parallel stage would instead be allowed to finish.

`error.run` is a partial `RunResult`. It provides the workspace, manifest,
completed task return values, and any selected artifacts that already exist.
Looking up a failed or unstarted task's return value raises `KeyError`.

For an external program failure, the error also points to its `stdout.log`
and includes a tail of that log when available. Read the full log for context;
the manifest's error string is only a summary. Failures before a workflow task
starts, such as remote environment setup or source-import failure, may require
application/terminal logs instead of a task manifest.

## 9. Understand Cores, Ranks, And Parallel Stages

A **core reservation** is the amount of CPU capacity a task declares it needs.
An MPI **rank** is a participating process in a parallel program. These are
related but not interchangeable concepts: one describes resources, the other
describes how the program runs.

For example, `Python(..., cores=4)` reserves four cores but does not start four
Python workers or add threads to a serial callback. By contrast,
`OpenSees(..., ranks=8)` asks the MPI launcher to start eight solver processes;
its task core reservation equals its rank count. An MPI command explicitly
sets both `cores` and `ranks`, which must match for the current launcher model.

### Start Independent Work Together

Use `parallel=True` only when tasks in that stage can run independently.
For example, after building three Tcl models, a solver stage could run them
together. The following MPI example requires an existing compatible allocation
backend, unlike the small local Python calculation above:

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

Assume the execution environment has **48 allocated cores** and uses one CPU
core per MPI rank for this example. The three tasks need `8 + 16 + 16 = 40`
cores together, leaving eight unreserved during the solve stage. The 48-core
budget is not a property of a particular machine or provider.

Now change the request or one task's ranks and ask what happens:

| Execution budget | Solver ranks | Scheduling | What happens |
| --- | --- | --- | --- |
| 48 cores | 8, 16, 16 | Parallel | Needs 40; fits with 8 cores unreserved |
| 32 cores | 8, 16, 16 | Parallel | Needs 40; rejected before tasks start, rather than running a subset |
| 48 cores | 8, 16, 32 | Parallel | Needs 56; rejected despite each individual task fitting |
| 48 cores | 8, 16, 32 | Sequential | Needs at most 32 at once; the tasks run one after another |

Later stages reuse the available cores; you do not sum reservations across
the whole workflow. Core reservations are scheduling checks, not automatic
OS-level limits on arbitrary callback code. A program must still respect its
thread/process settings. MPI ranks also do not repartition an exported model.

### A Backend Connects The Workflow To Its Environment

The workflow describes the procedure; a backend determines how tasks launch
in the environment where that procedure executes. That environment could be a
local computer, an HPC allocation, or cloud compute resources with a suitable
adapter. Resource requests and launchers differ; the task/stage ideas do not.

Do not infer that every cloud provider is implemented. The supplied execution
routes are local execution and the TACC allocation backend. Other cloud/HPC
routes require appropriate implementations and environments. The
[backend reference](../reference/jobs/TACC/index.md) documents the concrete
allocation implementation and its restrictions. The **Jobs** page explains
the separate platform that requests remote resources.

An `OpenSees` task returns a `ProcessResult`, not the model's displacement:

```python
solve = context.result("solve", "fixed")
log_file = solve.log
solver_task_folder = solve.output_dir
```

### Use A Custom OpenSees Build For One Task

A task can override the executable selected by its execution environment.
For example, use a personalized build for one model without changing another:

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
            executable="/path/to/your/OpenSeesMP",
        ),
    ],
)
```

The task override takes precedence over `FEMORA_OPENSEES` and the environment's
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

For the small calculation example, a parallel calculation stage with two
one-core callbacks needs `cores=2`; the original sequential version needs only
`cores=1`. The local runner supports that concurrent Python execution.

Backend capabilities still matter: the supplied TACC allocation backend
requires Python callbacks in sequential stages with `cores=1`. For an MPI-aware
Python script using that allocation launcher, use a `Command` task:

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

With one CPU core per MPI rank, this reserves 13 cores for 13 processes.
The command runs from `workspace/mixed/python-analysis`,
so `../../scripts/mpi_analysis.py` reaches `workspace/scripts/mpi_analysis.py`.
That script must be staged or created earlier and actually support MPI, for
example using `mpi4py`. An ordinary Python script will otherwise run five copies.
MPI execution requires the TACC allocation backend, not the local runner.

## Apply This To A Real Model

The [dynamic pile-soil example](../examples/dynamic-pile-soil-interaction.md)
uses these same ideas: one task creates the DRM input, a sequential stage builds
three models, a parallel stage runs them with 8, 16, and 16 MPI ranks, and a final
task creates response plots and a comparison movie on the cluster.

The useful habit is to ask three questions for each task: **What does it need?
Where does it write? What does it return?** Once those are clear, the workflow
is simply the order in which that work should happen.

## API Details And Next Step

Use the [Workflow reference](../reference/jobs/Workflow/index.md) for stage and
artifact-selection options, [execute()](../reference/jobs/execute/index.md) for
execution settings, and the [TACC backend](../reference/jobs/TACC/index.md) for
allocation-launch requirements. These signatures are separate from the
concepts taught through this example.

To submit this same procedure remotely, continue to [Jobs](jobs.md). The
workflow still describes the work; a job is one submitted request to execute it.
