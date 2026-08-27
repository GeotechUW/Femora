# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

# femora-colab-source: examples/site_response/layered_elastic_soil_column_postprocess.py

"""Plot and animate the partitioned layered soil-domain response."""

from __future__ import annotations

from pathlib import Path

import femora as fm

if __package__:
    from .layered_elastic_soil_column_postprocess import (
        SURFACE_COORDINATE,
        compute_analytical_transfer_function,
        compute_numerical_transfer_function,
        save_response_movie,
        save_transfer_function_plot,
    )
else:
    from layered_elastic_soil_column_postprocess import (
        SURFACE_COORDINATE,
        compute_analytical_transfer_function,
        compute_numerical_transfer_function,
        save_response_movie,
        save_transfer_function_plot,
    )


OUTPUT_DIR = Path("example_outputs") / "partitioned_layered_soil_domain"
RESULTS_DIR = OUTPUT_DIR / "results"
POSTPROCESS_DIR = OUTPUT_DIR / "post_processing"
RESULT_PATTERN = "partitioned_site_response*.vtkhdf"


# --8<-- [start:post-processing-workflow]
def generate_results() -> tuple[Path, ...]:
    """Generate the numerical and analytical transfer-function comparison."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    with fm.results.open(str(RESULTS_DIR / RESULT_PATTERN)) as results:
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
        output = POSTPROCESS_DIR / "transfer-function-comparison.png"
        save_transfer_function_plot(
            numerical_frequency,
            numerical_tf,
            analytical_frequency,
            analytical_tf,
            output,
        )
    return (output,)


def generate_animations() -> tuple[Path, ...]:
    """Render all result partitions as one synchronized deformation movie."""
    POSTPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    output = POSTPROCESS_DIR / "response.mp4"
    with fm.results.open(str(RESULTS_DIR / RESULT_PATTERN)) as results:
        save_response_movie(results, output)
    return (output,)
# --8<-- [end:post-processing-workflow]


def main() -> None:
    """Generate all documented post-processing outputs."""
    generated = (*generate_results(), *generate_animations())
    print("Post-processing outputs:")
    for output in generated:
        print(f"  {output.resolve()}")


if __name__ == "__main__":
    main()
