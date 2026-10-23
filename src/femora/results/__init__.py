# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""---
title: Results & Postprocessing
icon: material/chart-line
---

The ``femora.results`` package provides functions and classes for reading
recorded analysis output, extracting response histories, calculating derived
quantities, and visualizing results. It works with saved recorder files;
you do not need to rebuild the model or run OpenSees again.

This reference is organized by responsibility, rather than by file format or
model type. Start with general results access, then use a specialized
postprocessing or visualization interface when you need it.

## How The Package Fits Together

```text
Recorder files
    |
File reader                 Understands the output format
    |
ResultSet                   Provides general mesh and response queries
    |-- Specialized tools   Interpret responses for a particular model type
    |-- Visualization      Turn recorded fields into visual outputs
```

**File readers** handle the details of a particular output format. The current
built-in reader is [VTKHDFResultReader][femora.results.readers.vtkhdf.VTKHDFResultReader],
which supports serial and partitioned VTKHDF recorder output.
[open_results()][femora.results.result_set.open_results] selects a registered
reader and returns a [ResultSet][femora.results.result_set.ResultSet], so ordinary
queries do not require working directly with a reader.

**General results access** is independent of building-specific concepts.
``ResultSet`` lets you inspect recorded fields, access meshes, select points,
and extract point or cell histories. A
[PointSelection][femora.results.result_set.PointSelection] identifies a selected
point within a partition.

**Specialized postprocessing** adds meaning to those recorded values.
[BuildingResults][femora.results.building.BuildingResults] is the current
building-focused interface: it combines results with structural metadata to
identify floors and members, calculate engineering responses, and export tables.
It is not required for general soil, pile, or whole-model response queries.

**Visualization** uses recorded meshes and fields to create visual outputs.
[DeformationRenderer][femora.results.visualization.deformation.DeformationRenderer]
currently provides deformation movies with configurable coloring and views.
It does not require building metadata.

## Choose Your Starting Point

| Reference area | What you can do | Start with |
| --- | --- | --- |
| Reading Results | Open files, inspect available fields, select points, and extract histories | [open_results()][femora.results.result_set.open_results] and [ResultSet][femora.results.result_set.ResultSet] |
| Building Responses | Calculate floor responses, drift, member forces, structural resultants, and summary tables | [BuildingResults][femora.results.building.BuildingResults] |
| Visualization | Animate recorded deformation and configure field coloring and camera settings | [DeformationRenderer][femora.results.visualization.deformation.DeformationRenderer] |
| Advanced | Understand file readers, register another format, or handle result errors | [ResultReader][femora.results.base.ResultReader], [register_reader()][femora.results.register_reader], and [ResultError][femora.results.exceptions.ResultError] |

The examples below illustrate these entry points. Follow the linked class or
function pages for parameter details, available methods, and more examples.

## Current Scope And Extension

These areas describe the package structure, not a closed list of capabilities.
Additional file formats can be supported through the reader interface and
registry. Other model-specific postprocessing classes and visualization tools
can be added as the package develops; ``BuildingResults`` and deformation
rendering are the currently provided examples of those responsibilities.

Most users can use the existing high-level interfaces without implementing a
reader. See [ResultReaderRegistry][femora.results.registry.ResultReaderRegistry]
and [register_reader()][femora.results.register_reader] when adding a format.

## Before You Start

You need recorder output containing the fields you want to inspect. A
postprocessor cannot recover responses that were not recorded. Building-aware
calculations additionally need structural metadata exported during model setup.
The examples assume your files are available at the shown paths; replace those
paths and point coordinates with your own.

Wait until the solver closes its output files before reading them. Coordinates,
tolerances, and responses retain the original model's units; no automatic unit
conversion is performed.

## Open Files And Read A History

Use a path for a serial recorder or a glob for partitions from **one recorder
and one analysis**. Do not combine building, pile, and whole-model recorders
in the same result set.

```python
from femora.results import open_results

with open_results("results/earthquake_response*.vtkhdf") as results:
    print(results.number_of_steps)
    print(results.available_point_responses)

    point = results.nearest_point((0.0, 0.0, 0.0), tolerance=0.01)
    displacement_x = results.point_history("displacement", point, component="x")
    time = results.times
```

The context manager closes the underlying HDF5 files when the block ends.
Use ``available_cell_responses`` to inspect element fields and ``cell_history()``
to extract them. See [ResultSet][femora.results.result_set.ResultSet] for those
operations and [PointSelection][femora.results.result_set.PointSelection] for
the meaning of a point selection.

## Use Specialized Building Postprocessing

When your questions concern stories or physical members rather than individual
mesh points and cells, use ``BuildingResults``. For example, it can calculate
interstory drift and export response tables without manually grouping nodes
and elements.

Export structural metadata explicitly when building the model with
``building.export_metadata(model, "building.structure.h5", ...)``. That file
identifies members and floors; geometry alone does not reliably identify a
beam or brace. Then, after the analysis:

```python
from femora.results import BuildingResults

with BuildingResults.open(
    "results/building_response*.vtkhdf",
    metadata="building.structure.h5",
) as building:
    drift = building.interstory_drift(direction="x")
    floor_motion = building.floor_displacement(direction="x", relative_to_base=True)
    building.export_csv(
        "processed",
        responses=["floor_displacement", "interstory_drift", "base_shear"],
        direction="x",
    )
    building.summary(direction="x").to_csv("processed/summary_x.csv", index=False)
```

These queries require the corresponding recorded fields: displacement for
drift, acceleration for acceleration histories, and ``force3D`` for base shear.
Missing fields cannot be recovered by postprocessing. Tables require pandas;
their ``attrs`` carry units and response basis, which ordinary CSV does not retain.

!!! note "Soil-structure interaction"
    Relative-to-base displacement subtracts mean base translation only; it
    does not remove foundation rocking. Interstory drift is a mean-floor
    translation difference, not a rocking-corrected structural deformation.
    Acceleration basis is explicit metadata: DRM results already declared
    absolute must not have ground acceleration added a second time.

## Visualize Recorded Results

Visualization is a separate operation on a result set. You can render any
supported recorded mesh with the required displacement field, not just buildings.
This example uses a building recorder for a compact movie:

```python
from femora.results import open_results

with open_results("results/building_response*.vtkhdf") as results:
    movie = results.deformation_renderer()
    movie.deform_by("displacement", scale=20)
    movie.style_mesh(color="steelblue", line_width=4)
    movie.set_view(background="white")
    movie.write("building_response.mp4", stride=2, frame_rate=25)
```

The deformation scale changes the picture, not the numerical values. Rendering
requires a working VTK/OpenGL off-screen backend and an imageio/FFmpeg movie
writer; CSV queries do not. Rendering every second sample changes playback
speed unless the chosen frame rate compensates for that sampling interval.

Continue with [DeformationRenderer][femora.results.visualization.deformation.DeformationRenderer]
for field coloring, rendering options, and movie-output requirements.

## Where To Go Next

Choose the area that matches your task. These are the same groups used in the
sidebar; the links take you to their starting reference pages.

- **[reading results](open-results/index.md)**: start by opening recorder files,
  then explore ``ResultSet`` and ``PointSelection`` for general response queries.
- **[building responses](BuildingResults/index.md)**: use ``BuildingResults``
  for floor and member calculations, structural resultants, and table export.
- **[visualization](visualization/index.md)**: explore deformation rendering,
  field coloring, and movie output.
- **[advanced](readers/index.md)**: start with file readers, then use the sidebar's
  reader extensions and errors sections when extending or integrating the API.
"""

from .base import (
    CELL_FRAME,
    CELL_HISTORY,
    MESH,
    POINT_FRAME,
    POINT_HISTORY,
    ResultReader,
)
from .exceptions import ResultError, ResultFormatError, UnsupportedResultOperation
from .readers import VTKHDFResultReader
from .registry import reader_registry
from .result_set import PointSelection, ResultSet, open_results
from .visualization import DeformationRenderer
from .building import BuildingResults


reader_registry.register(
    "vtkhdf",
    VTKHDFResultReader,
    suffixes=".vtkhdf",
    replace=True,
)


def register_reader(name, reader, *, suffixes=(), replace=False):
    """Register an additional format in the shared result-reader registry.

    Args:
        name (str): Case-insensitive format name for ``open_results(format=...)``.
        reader (Callable): Factory accepting a path and returning a ResultReader.
        suffixes (str | Iterable[str]): One suffix or iterable, e.g. ``[".custom"]``.
        replace (bool): Allow replacing existing names or suffix mappings.

    Raises:
        ValueError: A name or suffix is already registered and replace is False.

    Note:
        This only registers a factory; it does not open or convert any files.
        Most users do not need it because VTKHDF is registered on import.
    """
    reader_registry.register(
        name,
        reader,
        suffixes=suffixes,
        replace=replace,
    )


open = open_results

__all__ = [
    "BuildingResults",
    "CELL_FRAME",
    "CELL_HISTORY",
    "DeformationRenderer",
    "MESH",
    "POINT_FRAME",
    "POINT_HISTORY",
    "PointSelection",
    "ResultError",
    "ResultFormatError",
    "ResultReader",
    "ResultSet",
    "UnsupportedResultOperation",
    "VTKHDFResultReader",
    "open",
    "open_results",
    "register_reader",
    "reader_registry",
]
