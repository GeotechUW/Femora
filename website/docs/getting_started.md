# Getting Started

Femora stands for **Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis**.
It is a Python-first workflow for building large **3D OpenSees models** from reusable modules instead of one monolithic script.

This guide is meant to give you the right mental model first:

- Femora is **code-driven**
- Femora is **module-driven**
- Femora is built for **assembly, inspection, and export**
- Femora is designed for **research-scale workflows**, not just one-off meshes

## What Femora Changes

In many OpenSees projects, the soil, structure, interfaces, wave input, recorders, and partitioning decisions are all mixed into one script.
That becomes difficult to debug, reuse, or scale.

Femora changes that workflow by letting you:

- build reusable mesh and modeling modules independently
- assemble them into one coherent 3D model
- inspect intermediate and final geometry while coding
- keep control over partition-aware assembly for larger studies
- attach recorders and postprocessing to the regions that matter

## Installation

If you are using the package directly:

```bash
pip install femora
```

If you are working from the Femora source repository:

```bash
git clone https://github.com/GeotechUW/Femora.git
cd Femora
pip install -e .
```

For a more detailed environment setup, see the [Installation](installation.md) page.

## The Core Idea

Femora is typically used through an explicit `Model` instance:

```python
from femora.core.model import Model

model = Model()
```

From there, you work through managers on the model:

- `model.material`
- `model.element`
- `model.meshpart`
- `model.time_series`
- `model.pattern`
- `model.interface`
- `model.recorder`
- `model.assembler`

Each manager owns one part of the modeling workflow.
That structure is what makes large assembled models easier to understand, extend, and automate.

## A Typical First Workflow

The first useful pattern is not “run a GUI.”
It is:

1. create a model container
2. create reusable components through managers
3. assemble the global model
4. inspect the assembled geometry
5. continue to export, record, or analyze

```python
from femora.core.model import Model

model = Model()

# Create materials, sections, mesh parts, interfaces,
# loading patterns, and other reusable model components
# through the managers attached to `model`.

model.assembler.assemble(merge_points=True)
model.assembler.plot(show_edges=True)
```

This is the important shift:
Femora is not asking you to build everything in one flat file.
It is asking you to assemble a model from well-scoped pieces.

## Inspect While You Build

Femora supports interactive inspection directly from Python.
That means you can look at mesh parts and assemblies during the coding workflow itself.

```python
from femora.core.model import Model

model = Model()

# Example: inspect an individual part while developing it
mesh_part.plot()

# Example: inspect the assembled model
model.assembler.plot(show_edges=True)
```

This is especially useful when you are:

- debugging geometry and interfaces
- checking partition-aware assembly
- validating embedded components
- preparing screenshots or notebook outputs

## Recommended Learning Path

If you are new to Femora, the best order is:

1. understand the modular assembly idea
2. read one example close to your problem
3. use the API reference when you need exact behavior
4. return to examples as your model grows

## Where To Go Next

<div class="grid cards" markdown>

-   :material-download-outline: **Installation**

    Set up your environment and local tooling in more detail.

    [Open installation](installation.md)

-   :material-school-outline: **Tutorials**

    Follow complete models that explain each decision in sequence.

    [Open tutorial gallery](tutorials/index.md)

-   :material-api: **API Reference**

    Browse managers, public classes, and generated API documentation.

    [Open API reference](reference/)

-   :material-home-outline: **Documentation Home**

    Return to the main documentation landing page and concept overview.

    [Open docs home](index.md)

</div>

## What To Expect Next

As you move beyond the first steps, Femora becomes most valuable when you start combining:

- reusable soil and structural modules
- embedded or interface-based coupling strategies
- partition-aware assembly
- recorder and postprocessing logic
- wave-input workflows such as DRM where needed

That is where the modular approach starts paying off.
