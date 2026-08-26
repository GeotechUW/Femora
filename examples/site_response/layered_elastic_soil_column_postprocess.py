# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Plot and animate the layered elastic soil-column response."""

from __future__ import annotations

from pathlib import Path

import femora as fm
import matplotlib.pyplot as plt
import numpy as np

from femora.tools.transferFunction import TransferFunction
from femora.utils.paths import motions_dir


OUTPUT_DIR = Path("example_outputs") / "layered_elastic_soil_column"
RESULTS_DIR = OUTPUT_DIR / "results"
POSTPROCESS_DIR = OUTPUT_DIR / "post_processing"

GRAVITY = 9.81
SURFACE_COORDINATE = np.array([0.0, 0.0, 0.0])
MAX_FREQUENCY = 22.0
DEFORMATION_SCALE = 15.0
MOVIE_STRIDE = 20
MOVIE_FRAME_RATE = 50


def compute_numerical_transfer_function(
    response_time: np.ndarray,
    relative_surface_acceleration: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate the absolute surface-to-base transfer function."""
    motion_directory = motions_dir()
    input_time = np.loadtxt(motion_directory / "FrequencySweep.time")
    input_acceleration = (
        np.loadtxt(motion_directory / "FrequencySweep.acc") * GRAVITY
    )
    base_acceleration = np.interp(response_time, input_time, input_acceleration)
    absolute_surface_acceleration = relative_surface_acceleration + base_acceleration

    dt = float(np.mean(np.diff(response_time)))
    frequency = np.fft.rfftfreq(response_time.size, d=dt)
    base_spectrum = np.fft.rfft(base_acceleration)
    surface_spectrum = np.fft.rfft(absolute_surface_acceleration)
    transfer_function = np.divide(
        surface_spectrum,
        base_spectrum,
        out=np.full_like(surface_spectrum, np.nan),
        where=np.abs(base_spectrum) > np.finfo(float).eps,
    )
    return frequency, transfer_function


def compute_analytical_transfer_function() -> tuple[np.ndarray, np.ndarray]:
    """Calculate the analytical response for the three physical strata."""
    soil_profile = [
        {
            "h": 2.0,
            "vs": 144.2535646321813,
            "rho": 19.8 * 1_000.0 / GRAVITY,
            "damping": 0.03,
            "damping_type": "rayleigh",
            "f1": 2.76,
            "f2": 13.84,
        },
        {
            "h": 6.0,
            "vs": 196.2675276462639,
            "rho": 19.1 * 1_000.0 / GRAVITY,
            "damping": 0.03,
            "damping_type": "rayleigh",
            "f1": 2.76,
            "f2": 13.84,
        },
        {
            "h": 10.0,
            "vs": 267.3633200780943,
            "rho": 19.9 * 1_000.0 / GRAVITY,
            "damping": 0.03,
            "damping_type": "rayleigh",
            "f1": 2.76,
            "f2": 13.84,
        },
    ]
    rock = {"vs": 8_000.0, "rho": 2_000.0, "damping": 0.0}
    frequency, transfer_function, _ = TransferFunction(
        soil_profile=soil_profile,
        rock=rock,
        f_max=MAX_FREQUENCY,
    ).compute()
    return frequency, transfer_function


def save_transfer_function_plot(
    numerical_frequency: np.ndarray,
    numerical_transfer_function: np.ndarray,
    analytical_frequency: np.ndarray,
    analytical_transfer_function: np.ndarray,
) -> None:
    """Save the numerical and analytical amplification comparison."""
    frequency_mask = (
        (numerical_frequency > 0.0) & (numerical_frequency <= MAX_FREQUENCY)
    )
    figure, axis = plt.subplots(figsize=(9.0, 4.8), constrained_layout=True)
    axis.plot(
        numerical_frequency[frequency_mask],
        np.abs(numerical_transfer_function[frequency_mask]),
        color="#315c6d",
        linewidth=1.7,
        label="Numerical",
    )
    axis.plot(
        analytical_frequency,
        np.abs(analytical_transfer_function),
        color="#b65f3a",
        linewidth=1.5,
        linestyle="--",
        label="Analytical",
    )
    axis.set(xlabel="Frequency (Hz)", ylabel="Amplification, |TF(f)|")
    axis.set_xlim(0.0, MAX_FREQUENCY)
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    figure.savefig(POSTPROCESS_DIR / "transfer-function-comparison.png", dpi=180)
    plt.close(figure)


def save_response_movie(results: fm.results.ResultSet) -> None:
    """Save an amplified deformation animation colored by physical stratum."""
    mesh = results.mesh()
    cell_elevation = mesh.cell_centers().points[:, 2]
    material_layer = np.full(mesh.n_cells, 2, dtype=int)
    material_layer[cell_elevation < -2.0] = 1
    material_layer[cell_elevation < -8.0] = 0
    mesh.cell_data["Physical layer"] = material_layer

    renderer = results.deformation_renderer()
    renderer.deform_by("displacement", scale=DEFORMATION_SCALE)
    renderer.color_by(
        "Physical layer",
        location="cell",
        categories=True,
        cmap=["#315c6d", "#c59652", "#b65f3a"],
        show_scalar_bar=False,
    )
    renderer.set_view(
        "xz",
        parallel_projection=True,
        zoom=1.15,
        background="#f6f4ef",
    )
    renderer.write(
        POSTPROCESS_DIR / "response.mp4",
        stride=MOVIE_STRIDE,
        frame_rate=MOVIE_FRAME_RATE,
    )


# --8<-- [start:post-processing-workflow]
def generate_results() -> tuple[Path, ...]:
    """Generate inexpensive plots intended for normal notebook execution."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        surface = results.nearest_point(
            SURFACE_COORDINATE,
            tolerance=1.0e-6,
        )
        surface_acceleration = results.point_history(
            "acceleration",
            surface,
            component="x",
        )

        numerical_frequency, numerical_tf = compute_numerical_transfer_function(
            results.times,
            surface_acceleration,
        )
        analytical_frequency, analytical_tf = compute_analytical_transfer_function()
        save_transfer_function_plot(
            numerical_frequency,
            numerical_tf,
            analytical_frequency,
            analytical_tf,
        )
    return (POSTPROCESS_DIR / "transfer-function-comparison.png",)


def generate_animations() -> tuple[Path, ...]:
    """Generate optional animations that can take substantially longer."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        save_response_movie(results)
    return (POSTPROCESS_DIR / "response.mp4",)
# --8<-- [end:post-processing-workflow]


# --8<-- [start:notebook-workflow]
def main() -> None:
    """Generate all documented post-processing outputs."""
    generated = (*generate_results(), *generate_animations())
    print("Post-processing outputs:")
    for output in generated:
        print(f"  {output.resolve()}")
# --8<-- [end:notebook-workflow]


if __name__ == "__main__":
    main()
