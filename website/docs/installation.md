# Installation

Femora is released to **PyPI** and can also be installed directly from source for development workflows.

## Requirements

Before installing Femora, make sure you have:

- **Python 3.9 or newer**
- `pip`
- a normal scientific Python environment with permission to install packages

Femora depends on packages such as `vtk`, `pyvista`, `scipy`, `h5py`, `meshlib`, and `trame`, so a clean virtual environment is strongly recommended.

## Recommended: Install From PyPI

For most users, the standard installation path is:

```bash
pip install femora
```

This installs the core package and its required dependencies from PyPI.

## Optional Extras

Femora exposes a few optional dependency groups depending on your workflow.

### Jupyter Support

If you plan to use Femora heavily in notebooks:

```bash
pip install "femora[jupyter]"
```

### METIS / Partitioning Support

If you need partition-related workflows that depend on `pymetis`:

```bash
pip install "femora[metis]"
```

### Extended Local Tooling

If you want the broader optional set used for richer local development environments:

```bash
pip install "femora[all]"
```

Use this only when you actually want the larger optional stack.

### Documentation Development

Contributors who regenerate tutorial notebooks should install the documentation
tooling:

```bash
pip install -e ".[docs]"
```

## Install From Source

If you are developing Femora itself, testing local changes, or working from the repository:

```bash
git clone https://github.com/GeotechUW/Femora.git
cd Femora
pip install -e .
```

For source development with optional extras:

```bash
pip install -e ".[all]"
```

An editable install is the right choice when:

- you are modifying Femora source code
- you are working on docs and examples together
- you want local changes reflected immediately without reinstalling

## Conda Workflow

If you prefer Conda, create an isolated environment first and then install Femora inside it.

Example:

```bash
conda create -n femora python=3.10
conda activate femora
pip install femora
```

If you are working from the repository and want to start from the included environment file:

```bash
conda env create -f environment.yml
conda activate myenv
pip install -e .
```

If you rename the environment in `environment.yml`, activate that name instead of `myenv`.

## Configure OpenSees

Femora exports models for OpenSees and can register the executable used by
tutorials and solver helpers. For a local installation, pass the executable
directly:

```python
import femora as fm

runtime = fm.runtime.setup(
    "local",
    executable=r"D:\path\to\OpenSees.exe",
)
print(runtime.version)
```

You can instead set `FEMORA_OPENSEES` or place OpenSees on `PATH` and call
`fm.runtime.setup("local")` without `executable`.

In Google Colab, install Femora before importing it and then configure the
portable runtime:

```python
%pip install -q "https://github.com/GeotechUW/Femora/archive/refs/heads/main.zip"

import femora as fm

runtime = fm.runtime.setup("colab")
```

Colab setup downloads the packaged OpenSees launcher and matching Tcl library,
verifies the published checksum, validates startup, and sets
`FEMORA_OPENSEES`. Repeated calls in the same session reuse the installation.

## Verify the Installation

The quickest verification is to import Femora in Python:

```bash
python -c "import femora; print(femora.__name__)"
```

You can also check that the main workflow entry is available:

```python
from femora.core.model import Model

model = Model()
print(type(model).__name__)
```

## Local Documentation Workflow

If you are working on the website or docs locally, Femora's repo includes a local workflow helper.

For fast website editing:

```bash
python run_local.py --mode website
```

For the full combined site check:

```bash
python run_local.py --mode full
```

The full mode builds:

- the website
- the generated API docs
- the merged local documentation site

## Common Notes

### Use a Virtual Environment

Do not install Femora into a crowded global Python environment if you can avoid it.
`vtk`, `pyvista`, and related packages are easier to manage inside a dedicated environment.

### PyPI vs Source

Use **PyPI** when you want a clean released version.

Use **source installation** when you want:

- the latest local code
- editable development
- docs or website work
- contribution workflows

### Interactive Plotting

Femora supports in-code inspection and plotting workflows.
If your local environment is missing visualization-related dependencies, install the optional extras you need or use the richer source-development environment.

## Next Steps

After installation:

1. read the [Getting Started](getting_started.md) guide
2. open the [Tutorial Gallery](tutorials/index.md)
3. use the [API Reference](reference/) when you need exact manager, class, or method behavior
