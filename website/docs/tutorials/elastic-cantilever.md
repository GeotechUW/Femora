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

For a local run, configure the OpenSees executable and run the Python file:

```powershell
$env:FEMORA_OPENSEES = "D:\path\to\OpenSees.exe"
python examples/tutorials/elastic_cantilever.py
```

Without `FEMORA_OPENSEES`, the script still assembles and exports the model.
Set `PLOT_MODEL = True` in the configuration block to inspect the assembled
mesh interactively.

## Walk Through The Model

### 1. Configure The Example

The engineering properties and run options are collected at the top of the
script. These values are shared by the model definition and the analytical
check, so a controlled change only needs to be made once.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:configuration"
```

### 2. Create The Building Blocks

The section stores the member stiffness properties. The transformation defines the local axes, and the element combines both into an OpenSees beam formulation.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:building-blocks"
```

Femora's managers assign tags and retain the relationships among these objects. You provide the engineering properties; the managers handle their model ownership and solver references.

### 3. Mesh And Assemble The Member

The line mesh part creates four cells between the two end coordinates. The assembly section then compiles that part into a serial model.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:mesh-and-assembly"
```

`num_partitions=0` explicitly keeps this assembly section serial. After assembly, `model.assembled_mesh` is a PyVista `UnstructuredGrid` with five points and four line cells.

### 4. Constrain And Select The Assembled Nodes

The fixed condition is applied to the plane at `x=0`. The tip is selected from the assembled model by position, so the script does not depend on a manually predicted node tag.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:constraints-and-selection"
```

!!! tip "Prefer selections over hard-coded solver tags"
    Spatial masks keep downstream operations tied to the model geometry. This is safer when discretization, assembly order, or tag starts change.

### 5. Apply The Load And Record The Response

A linear time series ramps the plain pattern from zero to the full load. The node load and recorder both use the selected tip node.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:loading-and-recording"
```

### 6. Define The Analysis And Process

The analysis owns the numerical solution settings. The process determines when the load pattern, recorder, and analysis appear in the exported Tcl script.

```python
--8<-- "examples/tutorials/elastic_cantilever.py:analysis-and-process"
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
