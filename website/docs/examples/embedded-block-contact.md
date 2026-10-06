---
title: Foundation Contact and Separation
icon: material/file-document-outline
---

# Foundation Contact and Separation

This example introduces frictional node-to-solid contact by placing a shallow
foundation block partly inside an elastic soil domain. Gravity closes the
interface. A horizontal load applied above the ground then rocks the block,
allowing one side to open while the opposite side remains in compression.

<div class="tutorial-actions" markdown>
[:material-code-braces: View source](https://github.com/GeotechUW/Femora/blob/main/examples/soil_structure_interaction/embedded_block_contact.py){ .tutorial-action .tutorial-action--source target="_blank" rel="noopener" }
</div>

| | |
|---|---|
| **Application** | Shallow-foundation contact and uplift |
| **Model** | Elastic soil and elastic solid foundation block |
| **Interface** | Five frictional contact faces |
| **Loading** | Self-weight followed by a 150 kN lateral load |
| **Analysis** | Implicit gravity, then explicit rocking |
| **Output** | VTKHDF displacement history and deformation movie |

## Model

<div class="femora-boundary-schematic">
--8<-- "website/docs/assets/examples/embedded-block-contact/model.svg"
</div>

The soil and foundation are separate bodies. The block penetrates 0.25 m below
the ground surface, placing its base and four short side faces inside the host
soil. Those five buried faces can transfer compression and friction while
remaining free to open when the block rocks.

The green arrows are the outward block normals supplied to `normal_filter`.
They select contact candidates; Femora converts them to the host-to-block
orientation required by the solver element.

## Worked Workflow

=== "1. Mesh both bodies"

    Create independent elastic brick meshes for the soil and foundation. Both
    use lumped mass because the lateral stage uses explicit integration.

    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py:mesh"
    ```

=== "2. Add five contact faces"

    Assemble without merging coincident points. Merging would tie the bodies
    and prevent opening or sliding. `contact=True` selects frictional contact
    instead of the tied embedded formulation. `Kn` controls normal penetration,
    `Kt` controls tangential compliance, and `mu` is the friction coefficient.

    The five calls are explicit so the connection is easy to inspect and adapt.

    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py:interfaces"
    ```

    Set `PLOT_INTERFACES = True` to inspect each selection. The plots show the
    selected host cells, generated interface points, and contact normals.

=== "3. Establish gravity"

    The interface begins closed, so one implicit static step establishes
    equilibrium under self-weight efficiently. Preserve that state and reset
    time before introducing the lateral load.

    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py:gravity"
    ```

=== "4. Apply the rocking load"

    Distribute 150 kN over all 25 top nodes. Its elevated resultant creates an
    overturning moment. The explicit stage then follows opening, sliding, and
    renewed contact without a nonlinear iteration at every increment.

    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py:lateral-loading"
    ```

=== "5. Export and run"

    Exporting always works locally. Setting `FEMORA_OPENSEES` also executes a
    compatible OpenSees build directly after export.

    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py:export-and-run"
    ```

## Rocking And Separation

The left panel gives the three-dimensional context; the right panel cuts away
the front half of the host soil to expose the interface. Opaque wireframes show
the soil mesh in both views. The gray outline is the undeformed foundation, and
the displayed rotation is calculated from the vertical displacement difference
between opposite top nodes.

<div class="femora-video">
  <video controls preload="metadata" poster="../../assets/examples/embedded-block-contact/preview.png">
    <source src="../../assets/examples/embedded-block-contact/block-contact-rocking.mp4" type="video/mp4">
    Your browser does not support embedded MP4 video.
  </video>
</div>

The opening visible beneath one edge is the behavior that a tied interface
cannot represent. This makes the contact formulation useful for raft and
shallow-foundation models where uplift and frictional load transfer matter.

## Run Locally

The OpenSees executable must include `EmbeddedNodeContact`. Point Femora to that
executable, then run the model and postprocessor:

```powershell
$env:FEMORA_OPENSEES = "D:\path\to\OpenSees.exe"
python examples/soil_structure_interaction/embedded_block_contact.py
python examples/soil_structure_interaction/embedded_block_contact_postprocess.py
```

The Tcl model and results are written under
`example_outputs/embedded_block_contact/`.

??? example "Complete model source"
    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact.py"
    ```

??? example "Complete post-processing source"
    ```python
    --8<-- "examples/soil_structure_interaction/embedded_block_contact_postprocess.py"
    ```
