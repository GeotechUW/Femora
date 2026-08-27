# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-source: examples/site_response/layered_elastic_soil_column_postprocess.py

"""Plot and animate the nonlinear layered soil-column response."""

from __future__ import annotations

from pathlib import Path

import femora as fm
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import hilbert

from femora.utils.paths import motions_dir

if __package__:
    from .layered_elastic_soil_column_postprocess import (
        compute_analytical_transfer_function,
        save_response_movie,
    )
else:
    from layered_elastic_soil_column_postprocess import (
        compute_analytical_transfer_function,
        save_response_movie,
    )


OUTPUT_DIR = Path("example_outputs") / "nonlinear_layered_soil_column"
RESULTS_DIR = OUTPUT_DIR / "results"
POSTPROCESS_DIR = OUTPUT_DIR / "post_processing"

SURFACE_COORDINATE = np.array([0.0, 0.0, 0.0])
HYSTERESIS_COORDINATE = np.array([0.5, 0.5, -5.0])
MAX_FREQUENCY = 22.0
GRAVITY = 9.81


def compute_sweep_amplification(
    response_time: np.ndarray,
    relative_surface_acceleration: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate the fundamental response locally along the frequency sweep."""
    motion_directory = motions_dir()
    input_time = np.loadtxt(motion_directory / "FrequencySweep.time")
    input_acceleration = (
        np.loadtxt(motion_directory / "FrequencySweep.acc") * GRAVITY
    )
    base_acceleration = np.interp(
        response_time,
        input_time,
        input_acceleration,
    )
    surface_acceleration = relative_surface_acceleration + base_acceleration

    analytic_input = hilbert(base_acceleration)
    phase = np.unwrap(np.angle(analytic_input))
    instantaneous_frequency = np.gradient(phase, response_time) / (2.0 * np.pi)
    envelope = np.abs(analytic_input)
    edge_margin = min(1.0, 0.05 * float(np.ptp(response_time)))
    valid = (
        (envelope > 0.1 * float(np.max(envelope)))
        & (response_time > response_time[0] + edge_margin)
        & (response_time < response_time[-1] - edge_margin)
        & (instantaneous_frequency >= 0.5)
        & (instantaneous_frequency <= MAX_FREQUENCY)
    )
    valid_indices = np.flatnonzero(valid)
    if valid_indices.size == 0:
        raise ValueError("The recorded interval does not contain the frequency sweep")

    frequencies = np.arange(0.5, MAX_FREQUENCY + 0.05, 0.1)
    amplification = np.full(frequencies.shape, np.nan, dtype=float)
    for index, frequency in enumerate(frequencies):
        center = valid_indices[
            np.argmin(
                np.abs(instantaneous_frequency[valid_indices] - frequency)
            )
        ]
        window_duration = float(np.clip(4.0 / frequency, 1.0, 4.0))
        window = np.abs(response_time - response_time[center]) <= window_duration / 2.0
        local_time = response_time[window] - response_time[center]
        basis = np.column_stack(
            (
                np.cos(phase[window]),
                np.sin(phase[window]),
                np.ones(np.count_nonzero(window)),
                local_time,
            )
        )
        base_coefficients = np.linalg.lstsq(
            basis,
            base_acceleration[window],
            rcond=None,
        )[0]
        surface_coefficients = np.linalg.lstsq(
            basis,
            surface_acceleration[window],
            rcond=None,
        )[0]
        base_amplitude = np.hypot(*base_coefficients[:2])
        if base_amplitude > np.finfo(float).eps:
            amplification[index] = (
                np.hypot(*surface_coefficients[:2]) / base_amplitude
            )

    return frequencies, amplification


def save_amplification_plot(
    numerical_frequency: np.ndarray,
    nonlinear_transfer_function: np.ndarray,
    elastic_frequency: np.ndarray,
    elastic_transfer_function: np.ndarray,
    output_file: Path,
) -> None:
    """Compare nonlinear amplification with the elastic reference profile."""
    mask = (numerical_frequency > 0.0) & (numerical_frequency <= MAX_FREQUENCY)
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(9.0, 6.4),
        sharex=True,
        constrained_layout=True,
    )
    axes[0].plot(
        numerical_frequency[mask],
        np.abs(nonlinear_transfer_function[mask]),
        color="#315c6d",
        linewidth=1.6,
    )
    axes[0].set_ylabel("Amplification")
    axes[0].set_title("Nonlinear sweep response (fundamental)", loc="left")

    axes[1].plot(
        elastic_frequency,
        np.abs(elastic_transfer_function),
        color="#b65f3a",
        linewidth=1.5,
        linestyle="--",
    )
    axes[1].set(
        xlabel="Frequency (Hz)",
        ylabel="Amplification",
        xlim=(0.0, MAX_FREQUENCY),
    )
    axes[1].set_title("Elastic reference", loc="left")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    figure.savefig(output_file, dpi=180)
    plt.close(figure)


def save_hysteresis_plot(
    shear_strain: np.ndarray,
    shear_stress: np.ndarray,
    output_file: Path,
) -> None:
    """Plot the representative xz shear stress-strain response."""
    figure, axis = plt.subplots(figsize=(6.8, 5.4), constrained_layout=True)
    axis.plot(
        100.0 * shear_strain,
        shear_stress,
        color="#315c6d",
        linewidth=1.25,
    )
    axis.set(xlabel="Shear strain, gamma_xz (%)", ylabel="Shear stress, tau_xz (kPa)")
    axis.grid(alpha=0.25)
    axis.spines[["top", "right"]].set_visible(False)
    figure.savefig(output_file, dpi=180)
    plt.close(figure)


# --8<-- [start:post-processing-workflow]
def generate_results() -> tuple[Path, ...]:
    """Generate amplification and material-hysteresis plots."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    amplification_plot = POSTPROCESS_DIR / "nonlinear-amplification.png"
    hysteresis_plot = POSTPROCESS_DIR / "shear-hysteresis.png"

    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        surface = results.nearest_point(SURFACE_COORDINATE, tolerance=1.0e-6)
        surface_acceleration = results.point_history(
            "acceleration",
            surface,
            component="x",
        )
        numerical_frequency, nonlinear_tf = compute_sweep_amplification(
            results.times,
            surface_acceleration,
        )
        elastic_frequency, elastic_tf = compute_analytical_transfer_function()
        save_amplification_plot(
            numerical_frequency,
            nonlinear_tf,
            elastic_frequency,
            elastic_tf,
            amplification_plot,
        )

        mesh = results.mesh()
        cell_centers = mesh.cell_centers().points
        cell_index = int(
            np.argmin(np.linalg.norm(cell_centers - HYSTERESIS_COORDINATE, axis=1))
        )
        shear_stress = results.cell_history(
            "stress3D6",
            cell_index,
            component=5,
        )
        shear_strain = results.cell_history(
            "strain3D6",
            cell_index,
            component=5,
        )
        save_hysteresis_plot(shear_strain, shear_stress, hysteresis_plot)

    return amplification_plot, hysteresis_plot


def generate_animations() -> tuple[Path, ...]:
    """Generate the optional amplified nonlinear response animation."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = POSTPROCESS_DIR / "response.mp4"
    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        save_response_movie(
            results,
            output_file,
            deformation_scale=1.0,
            stride=20,
            frame_rate=50,
        )
    return (output_file,)
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
