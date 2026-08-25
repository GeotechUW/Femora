---
title: Interfaces
icon: material/vector-link
---

# Interfaces

Interfaces describe relationships between mesh parts that should be executed through the assembly pipeline instead of being hard-coded into one conforming mesh up front.

In other words, mesh parts define geometry separately, and interfaces tell Femora how those separate pieces should interact when the global model is compiled.

---

## Mental Model

Think of interfaces as **declared relationships** rather than finished connectivity.

```mermaid
flowchart LR
    meshparts["Mesh parts<br/>independent geometry"]
    interface["Interface declaration<br/>relationship rule"]
    assembly{{"Assembly pipeline<br/>event-driven execution"}}
    result["Resolved interface result<br/>assembled-model updates"]

    meshparts --> interface
    interface --> assembly
    assembly --> result

    classDef stage stroke-width:1px;
    classDef compile stroke-width:2px;

    class meshparts,interface,result stage;
    class assembly compile;
```

An interface usually means one of these ideas:

- one part is embedded inside another
- one set of cells should search for nearby host cells
- one boundary treatment should be generated from the assembled model

The important point is that the interface is **declared before assembly**, but its real work is **event-driven inside the assembly pipeline**.

???+ note "Interfaces are not just geometry"
    A mesh part answers: "what geometry do I have?" An interface answers: "how should two already-defined parts relate once Femora sees the full assembled model?"

---

## Where It Fits

Interfaces belong after mesh parts and before assembly.

That ordering matters because an interface usually needs:

1. mesh parts to already exist
2. one or more assembly stages to perform search, filtering, boundary processing, or conflict resolution

So interfaces sit at the boundary between **local modeling** and **global compilation**.

---

## What Interfaces Mean In Femora

Femora interfaces are model objects managed under `model.interface`. They are useful when you do **not** want to force everything into one perfectly matching mesh by hand. Instead, you let Femora inspect the assembled model and generate the needed relationships.

Current interface ideas in Femora include:

| Interface idea | What it connects or generates | Typical use |
| --- | --- | --- |
| Embedded beam-solid interface | A line mesh part inside surrounding solid cells | Piles, embedded beams, beam-soil interaction |
| Embedded node interface | Node-based embedding relationship | Specialized node-to-domain coupling |
| Boundary absorber | New absorbing boundary layers derived from the assembled model | Truncating wave-reflecting boundaries |

---

## Before vs After Assembly

Explicitly contrast how the model sees the pieces before assembly versus how it sees the generated interface result after assembly.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 2rem 0;">
  <div style="border: 1px solid var(--md-default-fg-color--lightest); border-radius: 8px; padding: 1.5rem; background: rgba(169, 116, 97, 0.08);">
    <h3 style="margin-top: 0; color: var(--md-typeset-color);">Before Assembly</h3>
    <ul style="margin-bottom: 0;">
      <li><b>Independent Parts:</b> A pile mesh part and a soil mesh part exist separately.</li>
      <li><b>No Connections:</b> They share space but do not interact.</li>
      <li><b>Interface Rule:</b> A lightweight object holding radius, penalty params, and mesh references.</li>
    </ul>
  </div>
  <div style="border: 1px solid var(--md-default-fg-color--lightest); border-radius: 8px; padding: 1.5rem; background: rgba(59, 130, 246, 0.08);">
    <h3 style="margin-top: 0; color: var(--md-typeset-color);">After Assembly</h3>
    <ul style="margin-bottom: 0;">
      <li><b>Unified Global Grid:</b> One assembled <code>pyvista.UnstructuredGrid</code>.</li>
      <li><b>Host Discovery:</b> Surrounding soil cells are tagged as hosts.</li>
      <li><b>Generated Interface Result:</b> Interface-driven cells, metadata, or coupling updates are added depending on the interface type.</li>
    </ul>
  </div>
</div>

---

## Minimal Examples

=== "Embedded beam in solids"

    This is the most important interface pattern in the current workflow.

    ```python
    from femora.core.model import Model

    model = Model()

    # Assume "pile" is a line mesh part and "soil_box" is a solid mesh part.
    interface = model.interface.beam_solid_interface(
        name="pile_soil_interface",
        beam_part="pile",
        solid_parts=["soil_box"],
        radius=0.50,
        n_peri=8,
        n_long=5,
        penalty_param=1.0e12,
        g_penalty=True,
    )

    model.assembler.create_section(
        meshparts=["pile", "soil_box"],
        merge_points=True,
    )
    model.assembler.assemble()
    ```

    Here the interface is declared before assembly, but the surrounding-solid search and embedded relationship generation happen only when the required assembly stage is reached.

=== "Boundary absorber"

    Some interfaces are not part-to-part embedding relationships. They are assembly-time boundary treatments.

    ```python
    from femora.core.model import Model

    model = Model()

    model.interface.boundary.absorber(
        num_layers=3,
        geometry="rectangular",
        boundary_type="dashpot",
        rayleigh_damping=0.05,
    )

    model.assembler.assemble()
    ```

    In this pattern, the interface logic inspects the assembled boundary and then creates the absorbing treatment during the relevant assembly-time stage.

=== "Embedded nodes in a host mesh"

    Embedded node interfaces are useful when the constrained part should be tied to surrounding retained cells through node-based embedding logic instead of the beam-solid workflow.

    ```python
    from femora.core.model import Model

    model = Model()

    interface = model.interface.node_interface(
        name="building_foundation_interface",
        constrained_node="building",
        retained_nodes=["foundation"],
        rot=False,
        p=False,
        offset=0.0,
    )

    model.assembler.assemble()
    ```

## Visualizing Generated Interfaces

After `model.assembler.assemble()`, you can often call `plot()` on an interface object to inspect what Femora actually selected and added. These plot helpers are useful for debugging because they show the **resolved interface result**, not just the declaration.

The exact plotting options depend on the interface type, but the basic usage pattern is:

```python
model.assembler.assemble()
interface.plot()
```

### Embedded Beam-Solid Plot

```python
interface = model.interface.beam_solid_interface(
    name="pile_soil_interface",
    beam_part="pile",
    solid_parts=["soil_box"],
    radius=0.50,
)

model.assembler.assemble()
interface.plot()
```

<div style="margin: 1.25rem 0; border: 1px solid var(--md-default-fg-color--lightest); border-radius: 12px; overflow: hidden; background: var(--md-default-bg-color);">
  <div style="position: relative; width: 100%; aspect-ratio: 16/9; background: #fafafa;">
    <iframe src="../../assets/interfaces/embedded_beam_solid_plot.html" style="width: 100%; height: 100%; border: none;" title="Embedded Beam-Solid Interactive Visual"></iframe>
  </div>
</div>

This view is useful because it shows:

- the beam path owned by the interface
- the surrounding host solid cells selected by the search
- the geometric search envelope used by the interface

If those highlights do not match the intended physical relationship, the interface definition should be adjusted before export or analysis.

### Embedded Node Plot

```python
interface = model.interface.node_interface(
    name="building_foundation_interface",
    constrained_node="building",
    retained_nodes=["foundation"],
)

model.assembler.assemble()
interface.plot()
```

<div style="margin: 1.25rem 0; border: 1px solid var(--md-default-fg-color--lightest); border-radius: 12px; overflow: hidden; background: var(--md-default-bg-color);">
  <div style="position: relative; width: 100%; aspect-ratio: 16/9; background: #fafafa;">
    <iframe src="../../assets/interfaces/embedded_node_plot.html" style="width: 100%; height: 100%; border: none;" title="Embedded Node Interactive Visual"></iframe>
  </div>
</div>

This view is useful because it shows:

- the constrained mesh part
- the retained host cells used by the interface
- the constrained points selected for embedding
- the generated interface cells added to the assembled model

Each interface may expose different plotting options, but the main idea is the same: inspect the resolved relationship before continuing to export or analysis.

---

## What Femora Stores

When you create an interface, Femora stores the **relationship definition**, not just a final Tcl line.

Depending on the interface type, that can include:

- referenced mesh parts
- geometric search parameters such as radius or section envelope settings
- discretization controls such as `n_peri` and `n_long`
- penalty settings and formulation flags
- event subscriptions for assembly-time execution
- generated embedded information used for conflict resolution across cores

Conceptually, an interface is a model object that waits for the right assembly stage to do its work.

???+ tip "This is why interfaces are easier to debug than raw solver commands"
    Because the interface exists as a Femora object before export, you can inspect names, owners, participating parts, and often plot or trace the relationship before committing to the final solver script.

---

## What Interfaces Are Not

Interfaces are not the same thing as ordinary constraints.

- Interfaces start from mesh-part relationships and assembly-pipeline events.
- Constraints usually start from already-known nodes, DOFs, or assembled selections.

So even though both can eventually affect the solver domain, they solve different modeling problems.

Constraints belong later in the concept chain because users usually think about them after the assembled model exists.

---

## Common Mistakes

???+ warning "Do not use an interface when simple node merging is enough"
    If two mesh parts are meant to become one continuous domain and their coincident points should simply be merged, ordinary assembly point merging is the simpler path. Use an interface only when you need a declared relationship beyond shared nodes.

???+ warning "Do not think of interfaces as immediate solver commands"
    Creating an interface object does not finish the connection. The heavy work happens when `model.assembler.assemble()` triggers the relevant model events for that interface type.

???+ warning "Make the participating parts explicit when needed"
    For embedded workflows, restricting the relevant solid parts is often clearer and more controllable than letting the search operate over everything.

???+ tip "Use interfaces to keep complex coupling readable"
    A named interface such as `"pile_soil_interface"` is far easier to inspect and maintain than scattering equivalent coupling logic throughout a long hand-written solver script.

---

## How To Proceed In Practice

When you reach interfaces in a model, ask:

1. Are these parts truly separate sources that need a relationship?
2. Should assembly point merging handle the connection automatically?
3. If not, what interface object best expresses the intended coupling?
4. Which participating parts should the interface search or modify?

Once those answers are clear, define the interface and move on to assembly.

---

## Related Concepts

- [Mesh Parts](mesh-parts.md): Define the independent geometric sources that interfaces relate.
- [Assembly](assembly.md): The stage where interface searches and updates actually run.
