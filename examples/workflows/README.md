# Workflow execution

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
python -m femora.jobs replay workflow.zip --workspace results --backend tacc
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
- Requires MPI-enabled OpenSees for multiple ranks. A serial binary is insufficient.
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
export FEMORA_OPENSEES="$(command -v OpenSees)"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
RUN_DIR=$(mktemp -d "$SCRATCH/femora-mpi.XXXXXX")
cd "$RUN_DIR"
python /work2/08189/amnp95/stampede3/femora-tapis/Femora/examples/workflows/tacc_mpi_smoke.py --bundle mpi.zip
python -m femora.jobs replay mpi.zip --workspace results --backend tacc --cores 5
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
