---
title: Tags, Sources, Regions, and Groups
icon: material/tag-multiple-outline
---

# Tags, Sources, Regions, and Groups

Femora provides distinct layers of organization to identify, partition, and query portions of the compiled finite element mesh.

---

## Mental Model

As finite element models scale, you need to select subsets of nodes and elements to apply physical properties (such as damping) or position outputs (such as displacement recorders). 

Femora implements four distinct layers of organization:
1. **Tags (Solver Level)**: Unique integer identifiers assigned to nodes, elements, materials, and sections. These are directly mapped to the numerical solver.
2. **Sources (Metadata Level)**: The original high-level object (e.g. a specific `MeshPart` or `Interface`) that generated a portion of the compiled mesh.
3. **Regions (Physical Level)**: Formal spatial or material zones recognized by the solver (e.g., a region to which you apply Rayleigh damping).
4. **Groups (Query Level)**: Arbitrary collections of nodes or elements grouped in Python for easy reference, coordinate filtering, or recorder mapping.

---

## Where It Fits

These organization layers are populated during assembly and queried during the load, recorder, and analysis phases:

```text
Run Assembly
   ├─ Build metadata registry (preserve Sources)
   ├─ Generate solver tags (manage Tags automatically)
   └─ Query and organize compiled grid:
        ├─ model.region.create() (assign damping zones)
        └─ model.group.nodes_by_bounds() (select recorder nodes)
```

---

## Minimal Example

Creating a physical region and selecting ground surface nodes using a spatial boundary group:

```python
from femora.core.model import Model

model = Model()

# (Configure and compile assembly here...)

# 1. Create a physical Region for a soil subdomain
soil_domain = model.region.create(
    name="soil_domain",
    box=[-10.0, 10.0, -10.0, 10.0, -20.0, 0.0]
)

# 2. Create a query Group to select surface nodes (at Z = 0)
ground_surface = model.group.nodes_by_bounds(
    name="ground_surface",
    bounds=[None, None, None, None, 0.0, 0.0] # All X, All Y, Z=0
)
```

For query parameters, refer to the [Region Manager API Reference](../reference/core/region_manager.md) and [Group Manager API Reference](../reference/core/group.md).

---

## What Femora Stores

For organization, Femora tracks:
- **Tags**: Integer tracking lists managed by retagging policies.
- **Sources**: Metadata links mapping VTK cells to their generating component.
- **Regions**: Name, target element/node lists, material links, and damping properties.
- **Groups**: Name, node index arrays, and element index arrays.

---

## Common Mistakes

???+ warning "Confusing Regions with Groups"
    A **Region** has physical significance in the solver backend (e.g., a `region` command in OpenSees used to assign damping or recorders). A **Group** is a flexible Python-side helper container used for coordinate queries and constraint mappings; it does not write a `region` command to the solver. Do not pass a Group where a Region is expected.

---

## Related Concepts

* [Building Blocks](building-blocks.md): Understand how reusable pre-assembly objects are defined and referenced.
* [Damping, Recorders, and Outputs](damping-recorders-and-outputs.md): See how regions and groups are used to set outputs and damping.
