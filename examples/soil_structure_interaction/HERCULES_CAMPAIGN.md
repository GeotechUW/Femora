# Hercules Realization Campaign

The workflow file is self-contained. No helper scripts need to be staged.
Importing it or running it without `--submit` does not submit a job.

## Inputs and Scope

`--sourcefiles N` selects realization N, for N=1 through 10:

```text
/scratch/08189/amnp95/drm_inputs/Canonical_Mw7.0/sourcefilesN/h5drm/
    Hercules_V2_DRM_Box_0.h5drm ... Hercules_V2_DRM_Box_7.h5drm
```

With `--sourcefiles`, one submission runs one realization: 8 sites x 2 buildings x 2 foundations x
2 basin conditions = 64 cases. Ten separate submissions cover 640 cases.
Names and summaries include `sourcefilesN`; do not merge case folders while
discarding this identifier.

## Site-Wise Production

`--site S` selects one site (0-7) across all ten realizations. It runs 40 no-basin
models first, waits for all of them, then builds and runs 40 plastic models, and
finally postprocesses all 80 cases. Eight site jobs cover 640 distinct cases.
Each model uses 32 soil partitions, 54 METIS absorber partitions, one building
partition and one foundation/pile partition: 88 MPI ranks. Each basin phase runs
all 40 models concurrently (3,520 ranks) on 32 SPR nodes (3,584 cores).
The remote Femora installation must include absorber METIS support and pymetis.
All no-basin solves finish before plastic solves begin. This is a CPU capacity
calculation, not a guarantee of sufficient runtime memory or completion within
48 hours. No automatic restart exists. Validate the new partitioning with a pilot.

Validate configuration without submission:

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --site 0
```

Submit only the first site initially:

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --site 0 --submit
```

The configured request remains up to 2,880 minutes (48 hours), using the existing
application and allocation. No automatic continuation/restart is implemented.
Check completion, resource use, plastic outputs and package size before submitting
the remaining sites. `--site` cannot be combined with realization or pilot flags.

`MUMPS_ICNTL14=200` is shared by both gravity analyses and implicit dynamics, and
is included in each case JSON. Explicit dynamic integration remains unchanged.
The pilot succeeded with this setting, but larger runs still require monitoring.

## Pilot First

From the repository root, using an environment with Femora and its dependencies:

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --sourcefiles 1 --pilot
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --sourcefiles 1 --pilot --bundle example_outputs/hercules_pilot.zip
```

The pilot includes site 0, both buildings, both foundations and both basin
conditions (8 cases). With `--submit`, it requests 4 nodes; each solve phase
contains four 88-rank tasks. A single-realization 64-case run requests 26 nodes
and 32 tasks per solve phase. Site-wise production requests 32 nodes and 40 tasks.
Existing application/queue/allocation settings must still be appropriate
for the account. The existing 35 s duration and integration steps are unchanged.

Submission is explicit and requires approval of the intended resource use:

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --sourcefiles 1 --pilot --submit
```

After the remote pilot has passed, omit `--pilot` for a 64-case submission.
Do not submit all ten realizations before validating the pilot outputs.

For the fast four-case no-basin-only check, add `--no-basin-only`:

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --sourcefiles 1 --pilot --no-basin-only --submit
```

This runs both buildings and both foundations at site 0, then postprocesses and
archives them. It does not start plastic solves. Its storage projection uses
only no-basin data and cannot establish plastic-case compression or solver behavior.

To test four realizations together (sourcefiles1 through sourcefiles4):

```powershell
python examples/soil_structure_interaction/high_fidelity_ssi_basin_hercules.py --sourcefiles 1 --pilot --pilot-realizations 4 --no-basin-only --submit
```

This runs 16 simultaneous no-basin models at site 0 and requests 13 SPR nodes
(16 x 88 = 1,408 ranks). Omit `--submit` to validate configuration only. Pilot
node requests are calculated from the actual simultaneous solve-task count.

## Download Package

Only `postprocess/**/*` and `summary/**/*` are selected for return. Per case:

- Existing building CSVs plus base-relative floor displacement and structural-base
  displacement/acceleration in X/Y. Base response is the mean of building base nodes.
- `borehole_histories.h5`: complete raw motion at 12 centerline soil nodes and
  stress/strain components at 44 adjacent cells. Partition copies are checked.
- `foundation_histories.h5`: raw corner-patch translations, velocities and
  accelerations, plus a six-component small-angle rigid-motion least-squares fit.
  The fit origin and displacement residual RMS are retained; rotations are not
  direct rotational DOFs or exact finite rotations.
- `piles.vtkhdf` for pile cases: the full dedicated recorder containing all nine piles.
- `case.json`, `validation.json`, `building.structure.h5`, `assembled_model.vtu`
  and compressed `model.tcl.gz` for traceability and later interpretation.

Full building recorders remain remotely. Full-domain recording is disabled by
default (`RECORD_FULL_DOMAIN=False`). Solver logs are not selected for the download;
this does not suppress verbose solver output on remote scratch.

HDF5 compact arrays have axes `(time, entity, component)`, retain float64 values
and the initial recorded sample, and use gzip compression. Stress/strain component
ordering, shear conventions and recorder averaging still need verification.
No soil interpolation, averaging or DRM correction is silently applied.

The 48 m node and cells touching z=-48 m are flagged with
`exclude_from_soil_comparison`; raw data remain intact. This flag encodes the
known model-specific transition exclusion, not a general-purpose DRM classifier.
No bottom-node displacement reference is applied automatically.

## Acceptance Checks

Inspect every pilot case, not only one successful case:

1. Validation succeeds and histories cover 0-35 s without nonfinite values.
2. Foundation fit residuals and derived rocking are physically interpretable.
3. Base-relative displacement, drift and pile demands agree with independent checks.
4. Borehole data reproduce intended profiles with transition data excluded.
5. The archive includes the HDF5 files and full pile files, not just plots/summaries.
6. `summary/combined/storage_budget.json` projects the uncompressed package to 640
   cases and reports whether it fits the decimal 20 GB target. This estimate is
   based on measured pilot files; other realizations may compress differently.

The workflow does not enforce a hard archive-size cutoff or discard data to fit
the budget. Review size projections with margin before production. Finite values
and completed steps alone are not numerical/physical validation. Previously large
building demands remain a separate modeling review item.
