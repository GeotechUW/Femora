"""Generate interactive irregular-mesh partitioning assets for the Concepts site."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv
from pyvista import examples

from femora.components.partitioner.partitioner import PartitionerRegistry


OUTPUT_DIR = Path("website/docs/assets/partitioning")
PARTITIONERS = ("metis", "kd-tree", "geometric", "morton", "hilbert")
NUM_PARTITIONS = 4


def _inside_domain(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Return a concave L-shaped domain with a circular void removed."""
    in_l_shape = ((x <= 5.0) | (y <= 2.8)) & (x >= 0.0) & (y >= 0.0)
    outside_void = (x - 2.2) ** 2 + (y - 1.4) ** 2 >= 0.42**2
    return in_l_shape & outside_void


def build_irregular_mesh() -> pv.UnstructuredGrid:
    """Create a deterministic, highly irregular 2D triangular test mesh."""
    mesh = examples.download_dolfin(load=True)  # Download the mesh if it doesn't exist
    # mesh.plot(show_edges=True)
    return mesh


def save_partition_view(mesh: pv.UnstructuredGrid, partitioner: str) -> None:
    """Partition ``mesh`` and export an interactive PyVista view."""
    result = mesh.copy(deep=True)
    partition_labels = PartitionerRegistry.partition(
        result,
        NUM_PARTITIONS,
        partitioner=partitioner,
    )

    # ``extract_cells`` and downloaded example datasets can contain vtkOriginal*
    # provenance arrays. They are useful in Python, but some vtk.js versions
    # fail silently when such arrays are embedded in export_html output.
    result.point_data.clear()
    result.cell_data.clear()
    result.field_data.clear()
    result.cell_data["Core"] = np.asarray(partition_labels, dtype=np.int32)

    # Match the proven export pattern used by the Assembly concept assets.
    plotter = pv.Plotter(off_screen=True)
    plotter.add_mesh(
        result,
        scalars="Core",
        show_edges=True,
        # cmap="coolwarm",
        clim=(0, NUM_PARTITIONS - 1),
        line_width=1,
        show_scalar_bar=False,
    )
    plotter.view_xy()
    plotter.export_html(OUTPUT_DIR / f"irregular_2d_{partitioner}.html")
    plotter.close()


def main() -> None:
    """Generate one interactive view for every built-in partitioner."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mesh = build_irregular_mesh()
    for partitioner in PARTITIONERS:
        save_partition_view(mesh, partitioner)
        print(f"Generated {partitioner} partitioning view.")


if __name__ == "__main__":
    main()
