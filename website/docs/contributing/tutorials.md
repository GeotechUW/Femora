# Authoring Tutorials

Femora tutorials use one canonical executable source while keeping teaching
content and website presentation in their natural formats.

## File Set

Each tutorial consists of three coordinated files:

| File | Responsibility | Maintenance |
|---|---|---|
| `examples/tutorials/<name>.py` | Executable model and notebook Markdown cells | Edit directly |
| `examples/tutorials/<name>.ipynb` | Colab notebook with runtime bootstrap | Generate and commit |
| `website/docs/tutorials/<name>.md` | Explanations, figures, equations, and page layout | Edit directly |

The Python file is the source of truth for executable code. Do not manually
copy model code into the notebook or documentation.

## Canonical Python Script

Write the example as linear, top-to-bottom code. Use Jupytext percent cells to
define the notebook narrative and named snippet markers around code that the
documentation will display:

```python
# %% [markdown]
# ## Mesh and assemble the model
# Explain the purpose of this stage.

# %%
# --8<-- [start:mesh-and-assembly]
model.meshpart.line.single_line(...)
model.assembler.create_section(...)
model.assembler.assemble(...)
# --8<-- [end:mesh-and-assembly]
```

Follow these rules:

- Keep model parameters and run options in a short configuration section.
- Prefer linear execution over `main()`, `argparse`, or application-style
  wrappers.
- Use helper functions only when an operation is genuinely reusable or would
  obscure the main workflow if written inline.
- Read the local OpenSees executable from `FEMORA_OPENSEES`.
- Write generated results below `example_outputs/`.
- Prefix utility Python files with `_`; automatic notebook discovery ignores
  them.

## Generated Colab Notebook

Generate all tutorial notebooks from their Python sources:

```powershell
python scripts/sync_documentation_notebooks.py
```

The generator discovers every non-underscore `.py` file in
`examples/tutorials/`. It converts Jupytext cells, injects the Colab-only
Femora and OpenSees setup, removes outputs, and writes deterministic notebook
cell IDs.

Never edit the generated notebook directly. Verify synchronization before
committing:

```powershell
python scripts/sync_documentation_notebooks.py --check
```

The generated `.ipynb` file must be committed because the **Open in Colab**
link reads it directly from GitHub.

## Documentation Page

The Markdown page owns the teaching narrative, interactive assets, equations,
expected output, and links to related concepts. Embed executable sections from
the Python source with `pymdownx.snippets`:

````markdown
```python
; --8<-- "examples/tutorials/<name>.py:mesh-and-assembly"
```
````

A tutorial page should normally contain:

1. Frontmatter with a title and Material icon.
2. **Open in Colab** and **View source** actions.
3. A compact metadata table.
4. A visual summary of the completed model.
5. A guided walkthrough that embeds named Python sections.
6. Expected output and generated-file descriptions.
7. One controlled modification the reader can try.
8. Links to the concepts behind the workflow.

Keep explanations in Markdown rather than Python comments when they only serve
the website. Keep executable behavior in Python rather than duplicating it in
Markdown.

## Gallery Card

Add one card to `website/docs/tutorials/index.md`:

```html
<a class="learning-card" href="<name>/">
  <div class="learning-card__preview">
    <iframe
      src="../assets/tutorials/<name>/index.html"
      title="<Tutorial title> preview"
      loading="lazy"
      tabindex="-1"
    ></iframe>
  </div>
  <div class="learning-card__body">
    <p class="learning-card__sequence">Tutorial NN</p>
    <h2>Tutorial Title</h2>
    <p>One sentence describing the completed workflow.</p>
    <div class="learning-card__meta" aria-label="Tutorial metadata">
      <span>Level</span>
      <span>Analysis type</span>
      <span>Execution mode</span>
    </div>
    <span class="learning-card__link">
      Start tutorial <span aria-hidden="true">&rarr;</span>
    </span>
  </div>
</a>
```

Add the documentation page to the Tutorials navigation in
`website/mkdocs.yml`. Keep tutorial numbering sequential and use the same
slug for the Python file, notebook, documentation page, and asset directory,
changing underscores to hyphens where required by the website URL.

## Validation

Before committing a tutorial:

```powershell
python examples/tutorials/<name>.py
python scripts/sync_documentation_notebooks.py --check
python website/serve_docs.py --skip-api-reference
```

Confirm that the local script assembles without OpenSees, the notebook opens
and runs in Colab, every embedded code block renders, and the gallery preview
loads in both light and dark site themes.
