"""Regression checks for the temporary embedded-node host mesh."""

from types import SimpleNamespace

import numpy as np
import pyvista as pv

from femora.components.interface.embedded_node_interface import EmbeddedNodeInterface


def test_hex_decomposition_has_positive_unique_tets_and_preserves_volume():
    grid = pv.ImageData(dimensions=(3, 2, 2)).cast_to_unstructured_grid()
    # ImageData uses voxels; convert explicitly to VTK Hex8 ordering.
    cells = grid.cells.reshape(-1, 9).copy()
    cells[:, 1:] = cells[:, 1:][:, [0, 1, 3, 2, 4, 5, 7, 6]]
    mesh = pv.UnstructuredGrid(cells.ravel(), [pv.CellType.HEXAHEDRON] * 2, grid.points)
    mesh.cell_data["MeshPartTag_celldata"] = [1, 2]
    mesh.cell_data["Core"] = [3, 4]
    mesh.point_data["node_id"] = np.arange(mesh.n_points)
    interface = SimpleNamespace(retained_nodes=[SimpleNamespace(tag=1)])

    result = EmbeddedNodeInterface._tetrahedralize(interface, mesh)

    assert result.n_cells == 6  # Five selected-host tetrahedra and one untouched hex.
    tets = result.cells[:25].reshape(5, 5)[:, 1:]
    points = result.points[tets]
    jacobians = np.linalg.det(np.transpose(points[:, 1:] - points[:, :1], (0, 2, 1)))
    assert np.all(jacobians > 0)
    assert len(np.unique(np.sort(tets, axis=1), axis=0)) == 5
    np.testing.assert_allclose(jacobians.sum() / 6, 1.0)
    np.testing.assert_array_equal(result.cell_data["Core"], [3] * 5 + [4])
    np.testing.assert_array_equal(result.point_data["node_id"], mesh.point_data["node_id"])
