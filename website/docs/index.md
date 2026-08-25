# Femora Documentation

Femora stands for **Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis**.
It is an open-source Python platform for building modular 3D OpenSees workflows from reusable model parts.

## The Problem

Large OpenSees models are often difficult to build, maintain, and extend.
In real research workflows, the soil, structure, interfaces, loading, partitioning, and recording logic are usually developed by different people and then stitched together manually.
That makes it hard to:

- reuse model components across studies
- inspect intermediate assemblies while coding
- control domain decomposition for large parallel runs
- attach recorders and postprocessing to the right parts of the model
- scale from a simple model to a full soil-structure interaction workflow

## How Femora Solves It

Femora treats the model as a collection of reusable modules instead of one monolithic script.
Geotechnical components, structural components, interfaces, loading patterns, and recorder strategies can be implemented separately and assembled into one coherent 3D OpenSees model.

With Femora you can:

- build headlessly in Python for reproducible and HPC-ready workflows
- inspect mesh parts, assembly sections, and the final assembled mesh during coding
- combine soil, topography, foundation, pile, and structural systems in one workflow
- use embedding and interface strategies such as embedded nodes, beams, and piles
- control partition-aware assembly for research-scale runs
- generate or consume DRM-related workflows when the analysis requires them

## Start Here

<div class="grid cards" markdown>

-   :material-rocket-launch-outline: **Getting Started**

    Begin with installation, setup, and the first Femora workflow.

    [Open guide](getting_started.md)

-   :material-school-outline: **Tutorials**

    Follow complete, guided modeling workflows in a deliberate learning sequence.

    [Open tutorial gallery](tutorials/index.md)

-   :material-api: **API Reference**

    Browse the generated reference for managers, classes, and methods.

    [Open API reference](reference/)

-   :material-cog-outline: **Installation**

    Set up the environment, dependencies, and local documentation workflow.

    [Open installation](installation.md)

</div>

## Suggested Workflow

1. Read the getting started guide.
2. Complete a tutorial, then explore a model close to your use case in the example gallery.
3. Use the API reference when you need exact class and method behavior.
4. Return to the website for the broader product overview and modeling tools.
