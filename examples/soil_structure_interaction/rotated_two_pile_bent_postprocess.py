# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Postprocess the rotated two-pile bent response across orientation angles."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import femora as fm


CASE_ANGLES = {"angle_000": 0, "angle_030": 30, "angle_060": 60, "angle_090": 90}
CASES: Tuple[str, ...] = tuple(CASE_ANGLES)
REQUIRED_PROBES: Tuple[str, ...] = (
    "left_head",
    "right_head",
    "cap_top",
    "ground_surface",
)
PROBE_LABELS: Dict[str, str] = {
    "left_head": "Left Pile Head",
    "right_head": "Right Pile Head",
    "cap_top": "Cap Top Node",
    "ground_surface": "Ground Surface Reference",
}
CASE_COLORS: Dict[str, str] = {
    "angle_000": "#2b6cb0",  # blue
    "angle_030": "#dd6b20",  # amber/orange
    "angle_060": "#805ad5",  # violet
    "angle_090": "#2f855a",  # green
}
CASE_LABELS: Dict[str, str] = {
    "angle_000": "0 deg",
    "angle_030": "30 deg",
    "angle_060": "60 deg",
    "angle_090": "90 deg",
}
RESPONSE_GLOB = "rotated_bent_response*.vtkhdf"
DEFAULT_TOLERANCE = 1.0e-6  # Strict 1e-6 tolerance for probe node discovery
PILE_X = 3.809
PILE_TOP = 5.6
CAP_TOP = 7.28
FINAL_TIME = 50.0
RECORDER_DT = 0.02
EXPERIMENT_TIME_SHIFT = 11.45
TIME_WINDOW = (10.0, 40.0)
GRAVITY = 9.81
FREE_FIELD_XY = (0.0, 10.0)
FREE_FIELD_CHANNELS = {
    "ax_soilTop_global": 0.5,
    "ax_fixSoil_global": 2.6,
    "ax_tipSoil_global": 5.876,
    "ax_soilBottom_global": 21.0,
}
EXPERIMENT_BENT_CHANNEL = {0: "ax_local", 30: "ax_local", 60: "ax_local", 90: "ay_global"}
DEFAULT_EXPERIMENT = (
    Path(__file__).resolve().parents[1]
    / "inputs/validation/rotated_two_pile_bent/selected_experiment_processed.h5"
)


def read_single_case_response(
    case_dir: Path,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Tuple[dict, np.ndarray, Dict[str, np.ndarray]]:
    """Read one rotated case and locate its probes in the recorded mesh.

    Parameters
    ----------
    case_dir : Path
        Directory containing a `results` folder.
    tolerance : float
        Spatial tolerance for matching pile-head and ground-surface nodes.

    Returns
    -------
    metadata : dict
        Case angle and the selected probe coordinates.
    time : np.ndarray
        1D strictly monotonic physical time array.
    probe_displacements : dict[str, np.ndarray]
        Mapping of probe name to (N_steps, 3) array of signed displacements (dx, dy, dz) in meters.
    """
    case_dir = Path(case_dir)
    if case_dir.name not in CASES:
        raise ValueError(f"Unknown orientation case: {case_dir.name}")
    angle = CASE_ANGLES[case_dir.name]
    theta = math.radians(angle)
    x, y = PILE_X * math.cos(theta), PILE_X * math.sin(theta)
    probes = {
        "left_head": (-x, -y, PILE_TOP),
        "right_head": (x, y, PILE_TOP),
        "cap_top": (0.0, 0.0, CAP_TOP),
        "ground_surface": (0.0, 0.0, 0.0),
    }

    results_dir = case_dir / "results"
    matches = sorted(results_dir.glob(RESPONSE_GLOB))
    if not matches:
        raise FileNotFoundError(
            f"No VTKHDF results matching '{RESPONSE_GLOB}' in {results_dir}. "
            f"Run the '{case_dir.name}' simulation stage first."
        )

    pattern = str(results_dir / RESPONSE_GLOB)
    probe_displacements: Dict[str, np.ndarray] = {}

    with fm.results.open(pattern) as results:
        raw_times = results.times
        if raw_times is None:
            raise ValueError(f"{case_dir.name}: recorder output has no physical time values")

        time = np.asarray(raw_times, dtype=float)
        if time.ndim != 1 or time.size < 2:
            raise ValueError(f"{case_dir.name}: time history must be 1D, got shape {time.shape}")

        if not np.all(np.isfinite(time)):
            raise ValueError(f"{case_dir.name}: time history contains non-finite values (NaN or Inf)")

        if not np.all(np.diff(time) > 0.0):
            raise ValueError(f"{case_dir.name}: time values are not strictly monotonically increasing")

        if time[0] > RECORDER_DT + 1.0e-9 or time[0] < -1.0e-9:
            raise ValueError(
                f"{case_dir.name}: start time {time[0]:.6f} s is outside the first "
                f"recorder interval ({RECORDER_DT:g} s)"
            )

        if abs(time[-1] - FINAL_TIME) > RECORDER_DT + 1.0e-9:
            raise ValueError(
                f"{case_dir.name}: end time {time[-1]:.6f} s differs from final time "
                f"{FINAL_TIME:.6f} s by more than recorder dt {RECORDER_DT:g} s"
            )

        selected_coords = {}
        for probe_name in REQUIRED_PROBES:
            point = results.nearest_point(
                probes[probe_name],
                tolerance=None if probe_name == "cap_top" else tolerance,
            )
            if probe_name == "cap_top" and abs(point.coordinate[2] - CAP_TOP) > tolerance:
                raise ValueError(f"{case_dir.name}: no cap top node found at z={CAP_TOP:g} m")
            selected_coords[probe_name] = list(point.coordinate)
            hist = np.asarray(results.point_history("displacement", point), dtype=float)

            if hist.ndim != 2 or hist.shape[0] != time.size or hist.shape[1] < 3:
                raise ValueError(
                    f"{case_dir.name}, probe '{probe_name}': displacement history has fewer "
                    f"than 3 translational components (shape {hist.shape})"
                )

            disp = hist[:, :3]

            if not np.all(np.isfinite(disp)):
                raise ValueError(
                    f"{case_dir.name}, probe '{probe_name}': displacement history contains "
                    "non-finite values (NaN or Inf)"
                )

            probe_displacements[probe_name] = disp

    metadata = {
        "angle_degrees": angle,
        "final_time_s": FINAL_TIME,
        "recorder_dt_s": RECORDER_DT,
        "units": "m-N-kg-s",
        "probes": selected_coords,
    }
    return metadata, time, probe_displacements


def plot_rotated_bent_comparison(
    case_data: Dict[str, Tuple[dict, np.ndarray, Dict[str, np.ndarray]]],
    output_png: Path,
) -> Tuple[Path, Path]:
    """Plot three side-by-side displacement panels (left head, right head, cap top).

    Panels display raw recorded relative-to-base global x-displacements across
    the four orientation angles (0, 30, 60, 90 degrees), preserving the initial gravity
    offset explicitly.
    """
    panels: Sequence[str] = ("left_head", "right_head", "cap_top")
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.8), sharey=True)

    for ax, probe_name in zip(axes, panels):
        for case_name in CASES:
            metadata, time, disp_map = case_data[case_name]
            disp = disp_map[probe_name]
            color = CASE_COLORS.get(case_name, "black")
            label = CASE_LABELS.get(case_name, case_name)
            # Plot raw recorded global-x displacement (m)
            ax.plot(time, 1000 * disp[:, 0], label=label, color=color, linewidth=1.1)

        ax.set_title(PROBE_LABELS.get(probe_name, probe_name), fontsize=12, fontweight="bold")
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.tick_params(labelsize=10)

    axes[0].set_ylabel("Relative-to-ground dx (mm)", fontsize=10)
    axes[0].legend(loc="upper right", frameon=True, fontsize=9)

    fig.suptitle(
        "Bent response under global-x base motion",
        fontsize=12,
        y=1.03,
    )
    fig.tight_layout()

    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=200, bbox_inches="tight")

    output_pdf = output_png.with_suffix(".pdf")
    fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)

    return output_png, output_pdf


def generate_results(
    results_root: Path | str,
    output_dir: Optional[Path | str] = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Tuple[Path, ...]:
    """Generate per-case probe CSVs, a multi-angle comparison plot, and summary JSON.

    Parameters
    ----------
    results_root : Path or str
        Root directory containing one subdirectory for each orientation in CASES.
    output_dir : Path or str, optional
        Destination directory for generated CSVs, plots, and summary JSON.
        Defaults to `results_root / "post_processing"`.
    tolerance : float, optional
        Spatial tolerance for probe node discovery in the assembled mesh.

    Returns
    -------
    artifacts : tuple of Path
        Paths to all generated artifacts (CSVs, PNG plot, PDF plot, summary JSON).

    Raises
    ------
    FileNotFoundError
        If any required case or result file is missing.
    ValueError
        If time or displacement validation fails, or if time alignment between
        cases fails.
    """
    results_root = Path(results_root)
    # Check that all required cases exist; missing case fails immediately
    for case_name in CASES:
        case_dir = results_root / case_name
        if not case_dir.is_dir():
            raise FileNotFoundError(
                f"Missing required rotated case directory: '{case_dir}'. "
                f"All cases in {CASES} must be present."
            )

    case_data: Dict[str, Tuple[dict, np.ndarray, Dict[str, np.ndarray]]] = {}

    for case_name in CASES:
        case_dir = results_root / case_name
        metadata, time, disp_map = read_single_case_response(case_dir, tolerance=tolerance)

        # Adaptive stepping may give different recorder times in each case.
        # Overlay the actual histories; do not silently resample or shift them.

        case_data[case_name] = (metadata, time, disp_map)

    # Establish output directory
    if output_dir is not None:
        out_dir = Path(output_dir)
    else:
        out_dir = results_root / "post_processing"
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts: List[Path] = []
    summary: dict = {
        "cases": {},
        "description": (
            "Rotated two-pile bent dynamic response summary under uniform base excitation. "
            "CSVs and summary record raw signed displacements in meters (dx, dy, dz), "
            "including the initial post-gravity settling position."
        ),
    }

    # Write per-case, per-probe CSVs and compute summary statistics
    for case_name in CASES:
        metadata, time, disp_map = case_data[case_name]
        angle_deg = float(metadata.get("angle_degrees", 0.0))
        case_summary: dict = {
            "angle_degrees": angle_deg,
            "case_name": case_name,
            "final_time_s": float(metadata.get("final_time_s", 50.0)),
            "recorder_dt_s": float(metadata.get("recorder_dt_s", 0.02)),
            "units": metadata.get("units", "m-N-kg-s"),
            "probes": {},
        }

        for probe_name in REQUIRED_PROBES:
            disp = disp_map[probe_name]
            csv_path = out_dir / f"{case_name}_{probe_name}.csv"
            # Format: time_s, dx_m, dy_m, dz_m
            data_block = np.column_stack((time, disp))
            np.savetxt(
                csv_path,
                data_block,
                delimiter=",",
                header="time_s,dx_m,dy_m,dz_m",
                comments="",
                fmt="%.16e",
            )
            artifacts.append(csv_path)

            # Calculate signed extrema and corresponding timestamps
            idx_max_abs_x = int(np.argmax(np.abs(disp[:, 0])))
            idx_max_abs_y = int(np.argmax(np.abs(disp[:, 1])))
            idx_max_abs_z = int(np.argmax(np.abs(disp[:, 2])))

            case_summary["probes"][probe_name] = {
                "coords_m": [float(c) for c in metadata["probes"][probe_name]],
                "n_steps": int(len(time)),
                "end_time_s": float(time[-1]),
                "initial_displacement_m": [float(d) for d in disp[0]],
                "peak_abs_dx_m": float(np.abs(disp[idx_max_abs_x, 0])),
                "signed_peak_dx_m": float(disp[idx_max_abs_x, 0]),
                "time_peak_dx_s": float(time[idx_max_abs_x]),
                "peak_abs_dy_m": float(np.abs(disp[idx_max_abs_y, 1])),
                "signed_peak_dy_m": float(disp[idx_max_abs_y, 1]),
                "time_peak_dy_s": float(time[idx_max_abs_y]),
                "peak_abs_dz_m": float(np.abs(disp[idx_max_abs_z, 2])),
                "signed_peak_dz_m": float(disp[idx_max_abs_z, 2]),
                "time_peak_dz_s": float(time[idx_max_abs_z]),
                "csv_file": csv_path.name,
            }

        summary["cases"][case_name] = case_summary

    # Plot multi-angle comparison panels
    plot_png = out_dir / "rotated_bent_displacement_comparison.png"
    png_path, pdf_path = plot_rotated_bent_comparison(case_data, plot_png)
    artifacts.append(png_path)
    artifacts.append(pdf_path)

    # Save summary JSON
    summary_file = out_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    artifacts.append(summary_file)

    return tuple(artifacts)


def _point_history(results, response: str, coordinate) -> Tuple[np.ndarray, np.ndarray]:
    """Return the selected coordinate and its finite three-component history."""
    point = results.nearest_point(coordinate)
    values = np.asarray(results.point_history(response, point), dtype=float)[:, :3]
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError(f"Invalid {response} history at {coordinate}")
    return np.asarray(point.coordinate, dtype=float), values


def _base_acceleration(path: Path, time: np.ndarray, dt: float) -> np.ndarray:
    values = np.loadtxt(path, dtype=float).reshape(-1) * GRAVITY
    source_time = np.arange(len(values), dtype=float) * dt
    return np.interp(time, source_time, values, left=values[0], right=0.0)


def extract_reduced_results(
    results_root: Path,
    motion_file: Path,
    output_file: Path,
    motion_dt: float = 0.0127,
) -> Path:
    """Reduce distributed VTKHDF results to portable validation histories."""
    import h5py

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_file, "w") as reduced:
        reduced.attrs["units"] = "SI; acceleration stored in m/s^2"
        reduced.attrs["free_field_xy_m"] = FREE_FIELD_XY
        for case_name, angle in CASE_ANGLES.items():
            results_dir = Path(results_root) / case_name / "results"
            if not list(results_dir.glob(RESPONSE_GLOB)):
                raise FileNotFoundError(f"Missing VTKHDF results in {results_dir}")
            print(f"Reading {case_name}", flush=True)
            with fm.results.open(str(results_dir / RESPONSE_GLOB)) as results:
                time = np.asarray(results.times, dtype=float)
                if time.ndim != 1 or len(time) < 2 or np.any(np.diff(time) <= 0):
                    raise ValueError(f"{case_name}: invalid time vector")
                base_x = _base_acceleration(Path(motion_file), time, motion_dt)
                group = reduced.create_group(case_name)
                group.attrs["angle_degrees"] = angle
                group.create_dataset("time", data=time, compression="gzip")
                group.create_dataset("base_acceleration_x", data=base_x, compression="gzip")

                coordinate, relative = _point_history(results, "acceleration", (0, 0, CAP_TOP))
                absolute = relative.copy()
                absolute[:, 0] += base_x
                theta = math.radians(angle)
                local = np.column_stack((
                    absolute[:, 0] * math.cos(theta) + absolute[:, 1] * math.sin(theta),
                    -absolute[:, 0] * math.sin(theta) + absolute[:, 1] * math.cos(theta),
                    absolute[:, 2],
                ))
                bent = group.create_group("bent_top")
                bent.attrs["coordinate_m"] = coordinate
                bent.create_dataset("acceleration_global", data=absolute, compression="gzip")
                bent.create_dataset("acceleration_local", data=local, compression="gzip")

                free_field = group.create_group("free_field")
                for channel, depth in FREE_FIELD_CHANNELS.items():
                    coordinate, relative = _point_history(
                        results, "acceleration", (*FREE_FIELD_XY, -depth)
                    )
                    dataset = free_field.create_dataset(
                        channel, data=relative[:, 0] + base_x, compression="gzip"
                    )
                    dataset.attrs["coordinate_m"] = coordinate
                    dataset.attrs["requested_depth_m"] = depth
            print(f"  {len(time)} samples, time {time[0]:g} to {time[-1]:g} s", flush=True)
    return output_file


def _time_window(time: np.ndarray) -> np.ndarray:
    return (time >= TIME_WINDOW[0]) & (time <= TIME_WINDOW[1])


def _save_figure(figure, base: Path) -> Tuple[Path, Path]:
    png, pdf = base.with_suffix(".png"), base.with_suffix(".pdf")
    figure.savefig(png, dpi=220, bbox_inches="tight")
    figure.savefig(pdf, bbox_inches="tight")
    plt.close(figure)
    return png, pdf


def generate_validation_plots(
    numerical_file: Path, experiment_file: Path, output_dir: Path
) -> Tuple[Path, ...]:
    """Compare compact numerical histories with the shake-table measurements."""
    import h5py

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: List[Path] = []
    with h5py.File(numerical_file, "r") as numerical, h5py.File(experiment_file, "r") as experiment:
        case = numerical["angle_000"]
        numerical_time = case["time"][:]
        experiment_time = experiment["time"][:] - EXPERIMENT_TIME_SHIFT
        figure, axes = plt.subplots(5, 1, figsize=(10, 10), sharex=True)
        for axis, channel in zip(axes, ("ax_base", *FREE_FIELD_CHANNELS)):
            measured = experiment[f"free_field/acceleration/{channel}"][:]
            if channel == "ax_base":
                calculated = case["base_acceleration_x"][:] / GRAVITY
                title = "Base"
            else:
                calculated = case[f"free_field/{channel}"][:] / GRAVITY
                title = f"Depth {FREE_FIELD_CHANNELS[channel]:g} m"
            axis.plot(experiment_time[_time_window(experiment_time)],
                      measured[_time_window(experiment_time)], color="#a44a3f", lw=0.9,
                      label="Experiment")
            axis.plot(numerical_time[_time_window(numerical_time)],
                      calculated[_time_window(numerical_time)], color="#1f5a7a", lw=0.9,
                      label="Femora")
            axis.set(title=title, ylabel="a (g)")
            axis.grid(alpha=0.25)
        axes[0].legend(ncol=2, frameon=False)
        axes[-1].set(xlabel="Time (s)", xlim=TIME_WINDOW)
        figure.suptitle("Free-field acceleration validation")
        figure.tight_layout()
        artifacts.extend(_save_figure(figure, output_dir / "free_field_acceleration_comparison"))

        figure, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
        for axis, (case_name, angle) in zip(axes.flat, CASE_ANGLES.items()):
            group = numerical[case_name]
            time = group["time"][:]
            calculated = group["bent_top/acceleration_local"][:, 0] / GRAVITY
            channel = EXPERIMENT_BENT_CHANNEL[angle]
            measured = experiment[f"bent_top/theta_{angle}/acceleration/{channel}"][:]
            axis.plot(experiment_time[_time_window(experiment_time)],
                      measured[_time_window(experiment_time)], color="#a44a3f", lw=0.9,
                      label="Experiment")
            axis.plot(time[_time_window(time)], calculated[_time_window(time)],
                      color=CASE_COLORS[case_name], lw=0.9, label="Femora")
            axis.set(title=f"Bent orientation: {angle} deg", xlim=TIME_WINDOW)
            axis.grid(alpha=0.25)
        axes[0, 0].legend(ncol=2, frameon=False)
        axes[1, 0].set(xlabel="Time (s)", ylabel="Local acceleration (g)")
        axes[1, 1].set(xlabel="Time (s)")
        axes[0, 0].set_ylabel("Local acceleration (g)")
        figure.suptitle("Bent-top acceleration validation")
        figure.tight_layout()
        artifacts.extend(_save_figure(figure, output_dir / "bent_top_acceleration_comparison"))
    return tuple(artifacts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Reduce raw results on Stampede")
    extract.add_argument("--results-root", type=Path, default=Path("build"))
    extract.add_argument("--motion-file", type=Path, required=True)
    extract.add_argument("--motion-dt", type=float, default=0.0127)
    extract.add_argument("--output", type=Path, default=Path("rotated_bent_numerical.h5"))
    plot = commands.add_parser("plot", help="Generate validation comparisons")
    plot.add_argument("--numerical-file", type=Path, required=True)
    plot.add_argument("--experiment-file", type=Path, default=DEFAULT_EXPERIMENT)
    plot.add_argument("--output", type=Path, default=Path("post_processing"))
    args = parser.parse_args()
    if args.command == "extract":
        extract_reduced_results(
            args.results_root, args.motion_file, args.output, args.motion_dt
        )
    else:
        for path in generate_validation_plots(
            args.numerical_file, args.experiment_file, args.output
        ):
            print(f"Generated: {path}")
