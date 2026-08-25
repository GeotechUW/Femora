---
title: Mesh Data Schema
icon: material/table-large
---

# Mesh Data Schema

This reference defines the arrays Femora stores on meshes, including their names, associations, dtypes, and intended use. See [The Assembled Model](../concepts/assembled-model.md) for the lifecycle that creates these arrays.

Femora uses PyVista `UnstructuredGrid` objects. An array belongs to one of three scopes:

| Scope | Association | Meaning |
| --- | --- | --- |
| Point data | One value or vector per mesh point | Node-level information. |
| Cell data | One value per mesh cell | Element-level information. |
| Field data | Global arrays for the whole mesh | Export lookup metadata. |

## Status Labels

| Status | Contract |
| --- | --- |
| Public metadata | Supported model data for inspection, plotting, selection, and export. |
| Provenance | Identifies the Femora source that produced a point or cell. |
| Internal assembly data | Used to implement assembly. Do not make model logic depend on it. |
| Export-only field data | Added to the VTK export mesh copy; not guaranteed on the in-memory assembled mesh. |

## Assembly-Section Point Data

These arrays are created or normalized on `section.mesh`. They remain available on the assembled mesh unless a later operation changes their values through point merging.

| Array | Dtype created by Femora | Shape | Status | Meaning |
| --- | --- | --- | --- | --- |
| `ndf` | `uint16` | `(n_points,)` | Public metadata | Degrees of freedom at each point. Used for merge compatibility and node export. |
| `Mass` | `float32` | `(n_points, 6)` | Public metadata | Six-component nodal mass vector. Missing mass is initialized to zero. |
| `MeshPartTag_pointdata` | `uint16` | `(n_points,)` | Provenance | Source mesh-part tag before later merging. |

## Assembly-Section Cell Data

These arrays are created or normalized on `section.mesh`. A composite mesh can provide its own `ElementTag`, `MaterialTag`, or `SectionTag`; Femora preserves an existing array and therefore its source dtype.

| Array | Dtype created by Femora | Shape | Status | Meaning |
| --- | --- | --- | --- | --- |
| `ElementTag` | `uint16` | `(n_cells,)` | Public metadata | Element template or composite element tag. |
| `MaterialTag` | `uint16` | `(n_cells,)` | Public metadata | Material tag for the cell. |
| `SectionTag` | `uint16` | `(n_cells,)` | Public metadata | Section tag for the cell when its formulation uses one. |
| `Region` | `uint16` | `(n_cells,)` | Public metadata | Region assigned by the mesh part. |
| `MeshPartTag_celldata` | `uint16` | `(n_cells,)` | Provenance | Source mesh-part tag for ordinary mesh-part cells. |
| `FemoraPartTag` | `int32` | `(n_cells,)` | Provenance | Consecutive identifier for visualization and exported provenance. |
| `FemoraPartKind` | `int16` | `(n_cells,)` | Provenance | Numeric source kind: mesh part, interface, absorber, or generated. |
| `Core` | platform integer | `(n_cells,)` | Public metadata | Local partition label. It is `0` unless the section is divided. |

## Final-Assembly Point Data

The final assembly pass adds or uses the following arrays on `model.assembled_mesh`.

| Array | Dtype | Shape | Status | Meaning |
| --- | --- | --- | --- | --- |
| `MergeInFinal` | `uint8` | `(n_points,)` | Public metadata | `1` when the point's source section permits final merging; `0` otherwise. |
| `FinalMergeKey` | integer | `(n_points,)` | Internal assembly data | Merge key built from `ndf` and `MergeInFinal`. It is present only when final point merging runs. |

`ndf`, `Mass`, and `MeshPartTag_pointdata` also remain point data after final assembly. Merging can change their values. With `mass_merging="sum"`, Femora rebuilds `Mass` by summing all source mass vectors at the retained point.

`PointMergeMap` is temporary field data created by PyVista while a merge runs. Femora removes it before assembly completes; it is not a supported schema entry.

## Final-Assembly Cell Data

The assembled mesh retains the section cell-data arrays. Interfaces, absorbers, and other event-driven components may append cells and add workflow-specific arrays.

| Array | Status | Meaning |
| --- | --- | --- |
| `ElementTag`, `MaterialTag`, `SectionTag`, `Region` | Public metadata | Element formulation and region metadata carried from the source section. |
| `MeshPartTag_celldata` | Provenance | Original mesh-part source tag. Generated cells can use `0` when no mesh part owns them. |
| `Core` | Public metadata | Global partition label after Femora offsets later sections. |
| `FemoraPartTag`, `FemoraPartKind` | Provenance | Source information for ordinary and generated cells. |

## VTK Export Field Data

When Femora exports VTK, it adds these lookup arrays to the mesh copy written to disk. Together they map compact cell provenance IDs to readable source information.

| Field-data array | Dtype | Shape | Status | Meaning |
| --- | --- | --- | --- | --- |
| `FemoraPartTags` | `int32` | `(n_parts,)` | Export-only field data | Consecutive part identifiers. |
| `FemoraPartKindIds` | `int16` | `(n_parts,)` | Export-only field data | Kind identifier for each part. |
| `FemoraPartSourceTags` | `int32` | `(n_parts,)` | Export-only field data | Source mesh-part tag, or `0` when none exists. |
| `FemoraPartNames` | string | `(n_parts,)` | Export-only field data | Human-readable source name. |
| `FemoraPartKinds` | string | `(n_parts,)` | Export-only field data | Source kind: `meshpart`, `interface`, `absorber`, or `generated`. |

## Related Documentation

* [The Assembled Model](../concepts/assembled-model.md): Mesh lifecycle and final assembly process.
* [Assembly](../concepts/assembly.md): Local and final point merging.
* [Partitioning](../concepts/partitioning-and-parallel-execution.md): The `Core` cell-data array.
