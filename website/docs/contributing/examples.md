# Authoring Examples

Examples are complete reference models organized by engineering application.
Unlike tutorials, they do not form a required learning sequence and should use
descriptive names rather than numbers.

## Canonical Files

Use one lowercase category directory and one descriptive slug:

```text
examples/site_response/layered_elastic_soil_column.py
examples/site_response/layered_elastic_soil_column.ipynb
website/docs/examples/layered-elastic-soil-column.md
website/docs/assets/examples/layered-elastic-soil-column/
```

The Python file owns all executable behavior. The notebook is generated, and
the Markdown page embeds named sections from the Python source. Do not maintain
separate model implementations for local execution, Colab, and the website.

## Example Structure

Write examples as linear Jupytext percent-format scripts, following the same
section-marker convention used by tutorials:

```python
# %% [markdown]
# ## Assemble and constrain the domain

# %%
# --8<-- [start:assembly-and-constraints]
model.assembler.create_section(...)
model.assembler.assemble(...)
model.constraint.sp.fix_macro_z_min(...)
# --8<-- [end:assembly-and-constraints]
```

An application example should normally include:

- A compact configuration block and explicit unit system.
- Descriptive engineering data rather than unexplained constants.
- Current `Model` manager APIs only.
- Controlled output below `example_outputs/`.
- Optional solver execution through `FEMORA_OPENSEES`.
- An interactive visualization that can be regenerated from the canonical
  model.

## Colab Inputs

Colab opens the notebook without cloning the repository. Declare each required
repository input near the top of the Python source:

```python
# femora-colab-input: examples/inputs/motions/FrequencySweep.acc
# femora-colab-input: examples/inputs/motions/FrequencySweep.time
```

The notebook generator downloads only the declared files. Motion files are
placed below `/content/femora_inputs/motions`, and the setup cell configures
`FEMORA_MOTIONS_DIR` before the model code executes.

## Notebook Generation

The generator discovers curated sources in the directories listed by
`SOURCE_DIRS` in `scripts/sync_documentation_notebooks.py`.

```powershell
python scripts/sync_documentation_notebooks.py
python scripts/sync_documentation_notebooks.py --check
```

When adding a new example category, add its canonical directory to
`SOURCE_DIRS` and to the notebook workflow path filters. Commit the generated
notebook because the Colab action reads it directly from GitHub.

## Website Page

An example page should contain:

1. **Open in Colab** and **View source** actions.
2. A compact table describing the application, behavior, analysis, output, and
   execution mode.
3. An interactive model visualization.
4. The engineering inputs required to understand the model.
5. A concise explanation of important modeling decisions.
6. Embedded source sections rather than duplicated code.
7. Local and Colab execution instructions.
8. Expected model size and generated outputs.

Examples should be concise application references. Move foundational teaching
and detailed API explanations to Concepts or Tutorials and link to them.

## Migration Checklist

When migrating a legacy numbered example:

- Replace the number with a descriptive engineering name.
- Move the canonical source into a lowercase application directory.
- Convert singleton or module-level managers to a local `Model`.
- Replace legacy factory and camel-case calls with current APIs.
- Remove working-directory mutation and machine-specific paths.
- Review units, material properties, loading, and analysis staging.
- Declare external Colab inputs.
- Generate and commit the notebook and interactive asset.
- Add the page to the example gallery and MkDocs navigation.
- Run the Python source, notebook synchronization check, and documentation
  build.
