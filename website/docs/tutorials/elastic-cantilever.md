---
title: Elastic Cantilever
icon: material/bridge
---

# Elastic Cantilever

This tutorial builds a four-element 3D cantilever, applies a transverse tip load, runs a linear static analysis in OpenSees, and checks the computed displacement against the Euler-Bernoulli solution.

<div class="tutorial-actions" markdown>
[:simple-googlecolab: Open in Colab](https://colab.research.google.com/github/GeotechUW/Femora/blob/main/examples/tutorials/elastic_cantilever.ipynb){ .tutorial-action .tutorial-action--colab target="_blank" rel="noopener" }
[:material-code-braces: View source](https://github.com/GeotechUW/Femora/blob/main/examples/tutorials/elastic_cantilever.py){ .tutorial-action .tutorial-action--source target="_blank" rel="noopener" }
</div>

| | |
|---|---|
| **Format** | Tutorial |
| **Level** | Beginner |
| **Analysis** | Linear static |
| **Execution** | Serial |
| **Model size** | 5 nodes, 4 elements |

## What You Will Build

<div class="femora-embed femora-embed--cantilever">
  <iframe
    src="../../assets/tutorials/elastic-cantilever/index.html"
    title="Interactive four-element elastic cantilever model"
    loading="lazy"
  ></iframe>
</div>

The dashed line is the four-element model, while the solid curve shows its exaggerated displaced shape. The fixed support restrains all six degrees of freedom at node N1, and the load acts in the negative global z direction at node N5.

## Run The Demo

Use **Open in Colab** above for a browser-based run. The first code cell installs
Femora from GitHub, and `fm.runtime.setup("colab")` downloads and validates the
portable OpenSees runtime automatically.

For a local run, pass the OpenSees executable directly:

```powershell
python examples/tutorials/elastic_cantilever.py `
    --opensees D:\path\to\OpenSees.exe
```

Alternatively, configure the executable once and omit `--opensees`:

```powershell
$env:FEMORA_OPENSEES = "D:\path\to\OpenSees.exe"
python examples/tutorials/elastic_cantilever.py
```

Without an OpenSees executable, the script still assembles and exports the model. Add `--plot` to inspect the assembled mesh interactively.

## Walk Through The Model

### 1. Create The Building Blocks

The section stores the member stiffness properties. The transformation defines the local axes, and the element combines both into an OpenSees beam formulation.

```python
model = Model(model_name="elastic_cantilever", model_path=str(output_dir))

section = model.section.beam.elastic(
    user_name="cantilever_section",
    E=200.0e9,
    A=0.04,
    Iz=1.333333333e-4,
    Iy=1.333333333e-4,
    G=76.923e9,
    J=2.25e-4,
)
transformation = model.transformation.transformation3d(
    transf_type="Linear",
    vecxz_x=0.0,
    vecxz_y=0.0,
    vecxz_z=1.0,
)
beam_element = model.element.beam.elastic(
    ndof=6,
    section=section,
    transformation=transformation,
)
```

Femora's managers assign tags and retain the relationships among these objects. You provide the engineering properties; the managers handle their model ownership and solver references.

### 2. Mesh And Assemble The Member

The line mesh part creates four cells between the two end coordinates. The assembly section then compiles that part into a serial model.

```python
model.meshpart.line.single_line(
    user_name="cantilever",
    element=beam_element,
    x0=0.0,
    y0=0.0,
    z0=0.0,
    x1=4.0,
    y1=0.0,
    z1=0.0,
    number_of_lines=4,
)
model.assembler.create_section(
    ["cantilever"],
    num_partitions=0,
    merge_points=True,
)
model.assembler.assemble(merge_points=True)
```

`num_partitions=0` explicitly keeps this assembly section serial. After assembly, `model.assembled_mesh` is a PyVista `UnstructuredGrid` with five points and four line cells.

### 3. Constrain And Select The Assembled Nodes

The fixed condition is applied to the plane at `x=0`. The tip is selected from the assembled model by position, so the script does not depend on a manually predicted node tag.

```python
model.constraint.sp.fix_x(
    xCoordinate=0.0,
    dofs=[1, 1, 1, 1, 1, 1],
    tol=1.0e-9,
)

tip_nodes = model.mask.nodes.near_point(
    point=(4.0, 0.0, 0.0),
    radius=1.0e-9,
)
```

!!! tip "Prefer selections over hard-coded solver tags"
    Spatial masks keep downstream operations tied to the model geometry. This is safer when discretization, assembly order, or tag starts change.

### 4. Apply The Load And Record The Response

A linear time series ramps the plain pattern from zero to the full load. The node load and recorder both use the selected tip node.

```python
load_history = model.time_series.linear(factor=1.0)
lateral_load = model.pattern.plain(time_series=load_history)
lateral_load.add_load.node(
    node_mask=tip_nodes,
    values=[0.0, 0.0, -1_000.0, 0.0, 0.0, 0.0],
)

tip_recorder = model.recorder.node(
    file_name=displacement_file.as_posix(),
    nodes=tip_nodes.to_tags(),
    dofs=[3],
    resp_type="disp",
    time=True,
)
```

### 5. Define The Analysis And Process

The analysis owns the numerical solution settings. The process determines when the load pattern, recorder, and analysis appear in the exported Tcl script.

```python
static_analysis = model.analysis.static(
    name="tip_load",
    constraint_handler=model.analysis.constraint.transformation(),
    numberer=model.analysis.numberer.rcm(),
    system=model.analysis.system.bandgeneral(),
    algorithm=model.analysis.algorithm.linear(),
    test=model.analysis.test.normunbalance(tol=1.0e-10, max_iter=10),
    integrator=model.analysis.integrator.loadcontrol(incr=0.1),
    num_steps=10,
)

model.process.add_step(lateral_load, "Apply the cantilever tip load")
model.process.add_step(tip_recorder, "Record the tip displacement")
model.process.add_step(static_analysis, "Run the linear static analysis")
```

The ten load-control steps each add `0.1` to the load factor, so the final step reaches the full `-1,000 N` load.

## Expected Result

A verified run prints the model size and the final comparison:

```text
Elastic cantilever model
  Nodes:       5
  Elements:    4
  Tcl model:   .../example_outputs/elastic_cantilever/elastic_cantilever.tcl
  Tip disp.:   -8.000000e-04 m
  Analytical:  -8.000000e-04 m
  Rel. error:  0.000e+00
  Verification: passed
```

For a prismatic Euler-Bernoulli cantilever with a transverse tip force,

\[
u_{tip} = \frac{P L^3}{3 E I}
        = \frac{(-1000)(4)^3}{3(200\times10^9)(1.333333333\times10^{-4})}
        = -8.0\times10^{-4}\ \text{m}.
\]

The numerical and analytical values should agree to floating-point precision for this linear elastic model.

## Generated Files

The default `example_outputs/elastic_cantilever/` directory contains:

| File | Purpose |
|---|---|
| `elastic_cantilever.tcl` | Complete OpenSees input model |
| `elastic_cantilever.vtk` | Assembled mesh for external visualization |
| `elastic_cantilever_info.json` | Femora part metadata associated with the VTK export |
| `tip_displacement.out` | OpenSees time and tip-displacement history |

??? example "Complete source"
    ```python
    --8<-- "examples/tutorials/elastic_cantilever.py"
    ```

## Try A Controlled Change

Double `LENGTH` from `4.0` to `8.0` and run the model again. Because tip displacement scales with \(L^3\), the magnitude should increase by a factor of eight while the model remains linear.

For the architecture behind each stage, return to [Building Blocks](../concepts/building-blocks.md), [Assembly](../concepts/assembly.md), [Loading](../concepts/loading.md), [Analysis](../concepts/analysis.md), and [Process](../concepts/process.md).
