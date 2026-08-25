# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


TARGET_RATIO = 0.05
FREQUENCY_1_HZ = 1.0
FREQUENCY_2_HZ = 15.0


def rayleigh_coefficients(damping_ratio: float, f1: float, f2: float) -> tuple[float, float]:
    """Return mass- and stiffness-proportional Rayleigh coefficients."""
    omega_1 = 2.0 * np.pi * f1
    omega_2 = 2.0 * np.pi * f2
    alpha_m = 2.0 * damping_ratio * omega_1 * omega_2 / (omega_1 + omega_2)
    beta_k = 2.0 * damping_ratio / (omega_1 + omega_2)
    return alpha_m, beta_k


def generate_rayleigh_frequency_plot(output_path: Path) -> None:
    """Plot the Rayleigh damping curve used by the Damping concept example."""
    alpha_m, beta_k = rayleigh_coefficients(
        TARGET_RATIO,
        FREQUENCY_1_HZ,
        FREQUENCY_2_HZ,
    )

    frequencies = np.logspace(-1, 2, 700)
    omega = 2.0 * np.pi * frequencies
    mass_ratio = alpha_m / (2.0 * omega)
    stiffness_ratio = beta_k * omega / 2.0
    total_ratio = mass_ratio + stiffness_ratio

    figure, axis = plt.subplots(figsize=(10.4, 5.8), constrained_layout=True)
    figure.patch.set_facecolor("#f8fafc")
    axis.set_facecolor("#f8fafc")

    axis.axvspan(
        FREQUENCY_1_HZ,
        FREQUENCY_2_HZ,
        color="#0f766e",
        alpha=0.09,
        label="Control-frequency range",
    )
    axis.plot(
        frequencies,
        100.0 * total_ratio,
        color="#007c83",
        linewidth=3.0,
        label="Total Rayleigh damping",
        zorder=4,
    )
    axis.plot(
        frequencies,
        100.0 * mass_ratio,
        color="#d97706",
        linewidth=1.9,
        linestyle="--",
        label="Mass-proportional contribution",
    )
    axis.plot(
        frequencies,
        100.0 * stiffness_ratio,
        color="#2563eb",
        linewidth=1.9,
        linestyle="--",
        label="Stiffness-proportional contribution",
    )
    axis.axhline(
        100.0 * TARGET_RATIO,
        color="#475569",
        linewidth=1.5,
        linestyle=":",
        label="Target damping ratio",
    )

    control_frequencies = np.array([FREQUENCY_1_HZ, FREQUENCY_2_HZ])
    axis.scatter(
        control_frequencies,
        np.full(2, 100.0 * TARGET_RATIO),
        color="#be123c",
        edgecolor="#f8fafc",
        linewidth=1.5,
        s=75,
        zorder=5,
    )
    for label, frequency in zip(("f1", "f2"), control_frequencies):
        axis.annotate(
            f"{label} = {frequency:g} Hz",
            xy=(frequency, 100.0 * TARGET_RATIO),
            xytext=(0, 14),
            textcoords="offset points",
            ha="center",
            color="#881337",
            fontsize=10,
            fontweight="semibold",
        )

    axis.set_xscale("log")
    axis.set_xlim(0.1, 100.0)
    axis.set_ylim(0.0, 18.0)
    axis.set_xlabel("Frequency (Hz)", color="#0f172a", fontsize=11)
    axis.set_ylabel("Equivalent damping ratio (%)", color="#0f172a", fontsize=11)
    axis.set_title(
        "Frequency-based Rayleigh damping",
        color="#0f172a",
        fontsize=15,
        fontweight="semibold",
        pad=12,
    )
    axis.grid(which="major", color="#94a3b8", alpha=0.34, linewidth=0.8)
    axis.grid(which="minor", color="#cbd5e1", alpha=0.24, linewidth=0.55)
    axis.tick_params(colors="#334155")
    for spine in axis.spines.values():
        spine.set_color("#94a3b8")

    legend = axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=2,
        frameon=False,
        fontsize=9.5,
    )
    for text in legend.get_texts():
        text.set_color("#1e293b")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        format="png",
        dpi=180,
        facecolor=figure.get_facecolor(),
        metadata={"Date": None},
    )
    plt.close(figure)


def main() -> None:
    website_dir = Path(__file__).resolve().parents[1]
    output_path = website_dir / "docs" / "assets" / "damping" / "rayleigh-frequency.png"
    generate_rayleigh_frequency_plot(output_path)
    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
