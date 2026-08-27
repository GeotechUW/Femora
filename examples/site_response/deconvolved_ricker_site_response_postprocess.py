# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-source: examples/site_response/layered_elastic_soil_column_postprocess.py

"""Plot and animate the deconvolved Ricker-wave site response."""

from __future__ import annotations

from pathlib import Path

import femora as fm
import matplotlib.pyplot as plt
import numpy as np

if __package__:
    from .layered_elastic_soil_column_postprocess import save_response_movie
else:
    from layered_elastic_soil_column_postprocess import save_response_movie


OUTPUT_DIR = Path("example_outputs") / "deconvolved_ricker_site_response"
RESULTS_DIR = OUTPUT_DIR / "results"
MOTIONS_DIR = OUTPUT_DIR / "motions"
POSTPROCESS_DIR = OUTPUT_DIR / "post_processing"

GRAVITY = 9.81
SURFACE_COORDINATE = np.array([0.0, 0.0, 0.0])


def _load_motion(stem: str) -> tuple[np.ndarray, np.ndarray]:
    """Load one generated acceleration history from the example output."""
    return (
        np.loadtxt(MOTIONS_DIR / f"{stem}.time"),
        np.loadtxt(MOTIONS_DIR / f"{stem}.acc"),
    )


def save_deconvolution_plot(output_file: Path) -> None:
    """Plot the prescribed surface pulse and calculated base motion."""
    target_time, target_acceleration = _load_motion("ricker_surface_aligned")
    base_time, base_acceleration = _load_motion("ricker_base")

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(9.0, 5.8),
        sharex=True,
        constrained_layout=True,
    )
    axes[0].plot(target_time, target_acceleration, color="#b65f3a", linewidth=1.4)
    axes[0].set_title("Target surface motion", loc="left")
    axes[1].plot(base_time, base_acceleration, color="#315c6d", linewidth=1.3)
    axes[1].set_title("Deconvolved base motion", loc="left")
    axes[1].set_xlabel("Time (s)")
    for axis in axes:
        axis.set_ylabel("Acceleration (g)")
        axis.grid(alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    figure.savefig(output_file, dpi=180)
    plt.close(figure)


def save_surface_comparison_plot(
    response_time: np.ndarray,
    relative_surface_acceleration: np.ndarray,
    output_file: Path,
) -> float:
    """Compare the absolute numerical response with the target surface pulse."""
    target_time, target_acceleration_g = _load_motion("ricker_surface_aligned")
    base_time, base_acceleration_g = _load_motion("ricker_base")

    base_acceleration = np.interp(
        response_time,
        base_time,
        base_acceleration_g * GRAVITY,
    )
    numerical_surface_g = (
        relative_surface_acceleration + base_acceleration
    ) / GRAVITY
    target_on_response = np.interp(
        response_time,
        target_time,
        target_acceleration_g,
    )
    active = response_time <= target_time[-1]
    difference = numerical_surface_g[active] - target_on_response[active]
    reference_rms = float(np.sqrt(np.mean(target_on_response[active] ** 2)))
    normalized_rms_error = float(np.sqrt(np.mean(difference**2)) / reference_rms)

    figure, axis = plt.subplots(figsize=(9.0, 4.8), constrained_layout=True)
    axis.plot(
        response_time[active],
        target_on_response[active],
        color="#b65f3a",
        linewidth=1.6,
        linestyle="--",
        label="Target surface",
    )
    axis.plot(
        response_time[active],
        numerical_surface_g[active],
        color="#315c6d",
        linewidth=1.25,
        label="Numerical surface",
    )
    axis.set(xlabel="Time (s)", ylabel="Acceleration (g)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    axis.spines[["top", "right"]].set_visible(False)
    axis.text(
        0.99,
        0.04,
        f"Normalized RMS error: {normalized_rms_error:.3f}",
        ha="right",
        va="bottom",
        transform=axis.transAxes,
    )
    figure.savefig(output_file, dpi=180)
    plt.close(figure)
    return normalized_rms_error


# --8<-- [start:post-processing-workflow]
def generate_results() -> tuple[Path, ...]:
    """Generate the deconvolution and surface-response comparisons."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    deconvolution_plot = POSTPROCESS_DIR / "deconvolved-motion.png"
    response_plot = POSTPROCESS_DIR / "surface-response-comparison.png"
    save_deconvolution_plot(deconvolution_plot)

    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        surface = results.nearest_point(SURFACE_COORDINATE, tolerance=1.0e-6)
        relative_surface_acceleration = results.point_history(
            "acceleration",
            surface,
            component="x",
        )
        error = save_surface_comparison_plot(
            results.times,
            relative_surface_acceleration,
            response_plot,
        )
    print(f"Normalized surface-response RMS error: {error:.4f}")
    return deconvolution_plot, response_plot


def generate_animations() -> tuple[Path, ...]:
    """Generate the optional amplified response animation."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = POSTPROCESS_DIR / "response.mp4"
    result_pattern = str(RESULTS_DIR / "site_response*.vtkhdf")
    with fm.results.open(result_pattern) as results:
        save_response_movie(
            results,
            output_file,
            deformation_scale=15.0,
            stride=10,
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
