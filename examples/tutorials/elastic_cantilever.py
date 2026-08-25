# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# %% [markdown]
# # Elastic Cantilever with Femora
#
# Build a four-element 3D cantilever, run it with OpenSees, and compare the
# computed tip displacement with the Euler-Bernoulli solution.

# %%
"""Build and solve a small elastic cantilever with the current Femora API."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def _running_in_colab() -> bool:
    """Return whether this script is executing in Google Colab."""
    try:
        return importlib.util.find_spec("google.colab") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


IN_COLAB = _running_in_colab()
if IN_COLAB and importlib.util.find_spec("femora") is None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "https://github.com/GeotechUW/Femora/archive/refs/heads/main.zip",
        ]
    )

import numpy as np

import femora as fm
from femora import Model


if IN_COLAB:
    runtime = fm.runtime.setup("colab")
    print(f"OpenSees {runtime.version or 'runtime'} configured at {runtime.executable}")


LENGTH = 4.0
TIP_LOAD = -1_000.0
ELASTIC_MODULUS = 200.0e9
AREA = 0.04
SECOND_MOMENT = 1.333333333e-4
SHEAR_MODULUS = 76.923e9
TORSIONAL_CONSTANT = 2.25e-4


# %% [markdown]
# ## Build and assemble the model
#
# The section and transformation define the beam behavior. Femora then creates
# four line elements, assembles them, and applies the fixed support and tip load.

# %%
def build_model(output_dir: Path) -> tuple[Model, Path, Path]:
    """Create, assemble, and configure the cantilever model."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model = Model(model_name="elastic_cantilever", model_path=str(output_dir))
    model.set_results_folder(output_dir.as_posix())

    section = model.section.beam.elastic(
        user_name="cantilever_section",
        E=ELASTIC_MODULUS,
        A=AREA,
        Iz=SECOND_MOMENT,
        Iy=SECOND_MOMENT,
        G=SHEAR_MODULUS,
        J=TORSIONAL_CONSTANT,
    )
    transformation = model.transformation.transformation3d(
        transf_type="Linear",
        vecxz_x=0.0,
        vecxz_y=0.0,
        vecxz_z=1.0,
    )
    beam_element = model.element.beam.elastic(
        ndof=6,
        section=section,
        transformation=transformation,
    )

    model.meshpart.line.single_line(
        user_name="cantilever",
        element=beam_element,
        x0=0.0,
        y0=0.0,
        z0=0.0,
        x1=LENGTH,
        y1=0.0,
        z1=0.0,
        number_of_lines=4,
    )
    model.assembler.create_section(
        ["cantilever"],
        num_partitions=0,
        merge_points=True,
    )
    model.assembler.assemble(merge_points=True, progress_callback=lambda *_: None)

    model.constraint.sp.fix_x(
        xCoordinate=0.0,
        dofs=[1, 1, 1, 1, 1, 1],
        tol=1.0e-9,
    )

    tip_nodes = model.mask.nodes.near_point(
        point=(LENGTH, 0.0, 0.0),
        radius=1.0e-9,
    )
    if len(tip_nodes) != 1:
        raise RuntimeError(f"Expected one cantilever tip node, found {len(tip_nodes)}")

    load_history = model.time_series.linear(factor=1.0)
    lateral_load = model.pattern.plain(time_series=load_history)
    lateral_load.add_load.node(
        node_mask=tip_nodes,
        values=[0.0, 0.0, TIP_LOAD, 0.0, 0.0, 0.0],
    )

    displacement_file = output_dir / "tip_displacement.out"
    tip_recorder = model.recorder.node(
        file_name=displacement_file.as_posix(),
        nodes=tip_nodes.to_tags(),
        dofs=[3],
        resp_type="disp",
        time=True,
        precision=12,
    )

    static_analysis = model.analysis.static(
        name="tip_load",
        constraint_handler=model.analysis.constraint.transformation(),
        numberer=model.analysis.numberer.rcm(),
        system=model.analysis.system.bandgeneral(),
        algorithm=model.analysis.algorithm.linear(),
        test=model.analysis.test.normunbalance(tol=1.0e-10, max_iter=10),
        integrator=model.analysis.integrator.loadcontrol(incr=0.1),
        num_steps=10,
    )

    model.process.add_step(lateral_load, "Apply the cantilever tip load")
    model.process.add_step(tip_recorder, "Record the tip displacement")
    model.process.add_step(static_analysis, "Run the linear static analysis")

    tcl_file = output_dir / "elastic_cantilever.tcl"
    vtk_file = output_dir / "elastic_cantilever.vtk"
    model.export_to_tcl(
        filename=str(tcl_file),
        progress_callback=lambda *_: None,
    )
    model.export_to_vtk(filename=str(vtk_file), write_info_json=True)
    return model, tcl_file, displacement_file


# %% [markdown]
# ## Run OpenSees and verify the response
#
# These helpers run the exported Tcl model and compare the recorded displacement
# against the closed-form cantilever solution.

# %%
def run_opensees(executable: Path, tcl_file: Path) -> None:
    """Run the exported Tcl model and surface solver output on failure."""
    completed = subprocess.run(
        [str(executable), str(tcl_file)],
        cwd=tcl_file.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return

    if completed.stdout.strip():
        print(completed.stdout.rstrip())
    if completed.stderr.strip():
        print(completed.stderr.rstrip())
    raise RuntimeError(f"OpenSees failed with exit code {completed.returncode}")


def read_tip_displacement(displacement_file: Path) -> float:
    """Read the final displacement value from the OpenSees node recorder."""
    data = np.atleast_2d(np.loadtxt(displacement_file))
    return float(data[-1, -1])


def analytical_tip_displacement() -> float:
    """Return the Euler-Bernoulli cantilever solution for comparison."""
    return TIP_LOAD * LENGTH**3 / (3.0 * ELASTIC_MODULUS * SECOND_MOMENT)


# %% [markdown]
# ## Execute the tutorial
#
# Local users may pass `--opensees` or set `FEMORA_OPENSEES`. In Colab, the
# runtime setup above configures the solver automatically.

# %%
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            Path("/content/elastic_cantilever")
            if IN_COLAB
            else Path("example_outputs") / "elastic_cantilever"
        ),
        help="Directory for the Tcl, VTK, JSON, and recorder output files.",
    )
    parser.add_argument(
        "--opensees",
        type=Path,
        default=None,
        help="OpenSees executable. Defaults to the FEMORA_OPENSEES environment variable.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Open an interactive PyVista view of the assembled mesh.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    model, tcl_file, displacement_file = build_model(args.output_dir)

    print("\nElastic cantilever model")
    print(f"  Nodes:       {model.assembled_mesh.n_points}")
    print(f"  Elements:    {model.assembled_mesh.n_cells}")
    print(f"  Tcl model:   {tcl_file}")

    configured_executable = args.opensees or os.environ.get("FEMORA_OPENSEES")
    if configured_executable is None:
        print("  Solver:      not run (pass --opensees or set FEMORA_OPENSEES)")
    else:
        run_opensees(Path(configured_executable), tcl_file)
        numerical = read_tip_displacement(displacement_file)
        analytical = analytical_tip_displacement()
        relative_error = abs((numerical - analytical) / analytical)
        if not np.isclose(numerical, analytical, rtol=1.0e-9, atol=1.0e-12):
            raise RuntimeError(
                "Cantilever verification failed: "
                f"numerical={numerical:.12e}, analytical={analytical:.12e}"
            )
        print(f"  Tip disp.:   {numerical:.6e} m")
        print(f"  Analytical:  {analytical:.6e} m")
        print(f"  Rel. error:  {relative_error:.3e}")
        print("  Verification: passed")

    if args.plot:
        model.assembled_mesh.plot(
            show_edges=True,
            line_width=5,
            color="#d67a2f",
            background="#f4f0e8",
        )


if __name__ == "__main__":
    main([] if "ipykernel" in sys.modules else None)
