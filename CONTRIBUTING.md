# Contributing to Femora

Thank you for contributing to Femora. This guide describes the standards used
for code changes, documentation updates, and pull requests.

## Development Setup

Create a Python environment with Python 3.9 or newer, then install Femora in
editable mode:

```bash
pip install -e .
```

Install optional dependency groups only when they are relevant to your work:

```bash
pip install -e ".[metis]"
pip install -e ".[gui]"
pip install -e ".[all]"
```

## Running Tests

Run the full test suite before opening a pull request:

```bash
pytest
```

For focused changes, run the smallest relevant test group first, then run the
full suite when practical.

## Code Style

Femora follows normal Python conventions:

- Use clear `snake_case` names for functions, methods, and variables.
- Use `PascalCase` for classes.
- Keep public APIs explicit and manager-owned through `Model` where practical.
- Avoid reintroducing singleton-style runtime state in non-GUI code.
- Add type hints for new public functions and methods.
- Keep behavior changes covered by tests.

## Documentation Style

Femora API documentation is generated from Python docstrings through MkDocs and
mkdocstrings. Docstring changes must follow:

```text
.github/DOCSTRING_STYLE.md
```

The short version:

- Use Google-style docstrings.
- Keep class docstrings conceptual.
- Keep `__init__` docstrings focused on constructor arguments and validation.
- Do not duplicate constructor `Args:` in both the class and `__init__`
  docstrings.
- Use current `Model` manager-based examples.
- Do not use stale singleton/default-model examples.

Executable documentation has an additional single-source workflow. Follow
`website/docs/contributing/tutorials.md` for guided tutorials and
`website/docs/contributing/examples.md` for application examples.

## Pull Requests

Pull requests should be focused and easy to review.

Before opening a pull request:

- Confirm tests pass for the affected area.
- Include or update tests for behavior changes.
- Keep generated files, temporary outputs, and local experiment files out of the
  repository.
- Explain the user-facing impact and any compatibility concerns.

For documentation-only changes, state that no runtime behavior was changed.

## Generated Files

Do not commit local output files such as generated Tcl, VTK, result folders,
temporary plots, or local build directories unless they are intentional examples
or documentation assets.
