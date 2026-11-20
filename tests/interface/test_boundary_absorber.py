# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

import pytest
import numpy as np

from femora.core.model import Model
from femora.components.material.nd import ElasticIsotropicMaterial


@pytest.fixture
def mesh_maker():
    mm = Model()
    mm.clear_model()
    return mm


def _make_box_meshpart(mm: Model, divisions=1):
    mat = mm.material.add(
        ElasticIsotropicMaterial(user_name="mat", E=200e3, nu=0.3, rho=0.0)
    )
    ele = mm.element.brick.std(ndof=3, material=mat)
    mm.meshpart.volume.uniform_rectangular_grid(
        user_name="box",
        element=ele,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        z_min=0.0,
        z_max=1.0,
        nx=divisions,
        ny=divisions,
        nz=divisions,
    )
    mm.assembler.create_section(meshparts=["box"], num_partitions=1, merge_points=False)
    return mm


def test_boundary_absorber_registers_before_assembly(mesh_maker):
    _make_box_meshpart(mesh_maker)
    mesh_maker.interface.boundary.absorber(
        num_layers=1,
        num_partitions=0,
        partition_algo="kd-tree",
        geometry="Rectangular",
        type="Rayleigh",
        rayleigh_damping=0.95,
        match_damping=False,
    )
    assert len(mesh_maker.interface._boundary_absorbers) == 1


def test_boundary_absorber_applies_after_assembly(mesh_maker):
    _make_box_meshpart(mesh_maker)
    mesh_maker.interface.boundary.absorber(
        num_layers=1,
        num_partitions=0,
        partition_algo="kd-tree",
        geometry="Rectangular",
        type="Rayleigh",
        rayleigh_damping=0.95,
        match_damping=False,
    )
    base_cells = None
    mesh_maker.assembler.assemble(merge_points=False)
    assert mesh_maker.assembled_mesh is not None
    assert mesh_maker.assembled_mesh.n_cells > 1
    assert "AbsorbingRegion" in mesh_maker.assembled_mesh.cell_data
    assert int(mesh_maker.assembled_mesh.cell_data["AbsorbingRegion"].max()) > 0
    points = mesh_maker.assembled_mesh.points
    assert np.unique(np.round(points, decimals=8), axis=0).shape[0] == len(points)


def test_interface_manager_has_boundary_namespace(mesh_maker):
    assert hasattr(mesh_maker.interface, "boundary")
    assert callable(mesh_maker.interface.boundary.absorber)


def test_meshmaker_has_no_drm_runtime(mesh_maker):
    assert not hasattr(mesh_maker, "drm")


def test_metis_absorber_has_exact_non_power_of_two_partition_count(mesh_maker):
    pytest.importorskip("pymetis")
    _make_box_meshpart(mesh_maker, divisions=4)
    mesh_maker.interface.boundary.absorber(
        num_layers=2, num_partitions=54, partition_algo="metis",
        geometry="Rectangular", boundary_type="Rayleigh",
        rayleigh_damping=0.95, match_damping=False,
    )
    mesh_maker.assembler.assemble(merge_points=False, progress_callback=lambda *_: None)
    mesh = mesh_maker.assembled_mesh
    absorber = mesh.cell_data["AbsorbingRegion"] != 0
    np.testing.assert_array_equal(np.unique(mesh.cell_data["Core"][absorber]), np.arange(1, 55))
    np.testing.assert_array_equal(np.unique(mesh.cell_data["Core"][~absorber]), [0])


def test_metis_absorber_rejects_empty_partitions(mesh_maker, monkeypatch):
    from femora.components.partitioner import PartitionerError, PartitionerRegistry

    _make_box_meshpart(mesh_maker, divisions=4)
    monkeypatch.setattr(
        PartitionerRegistry, "partition",
        lambda mesh, num_partitions, **kwargs: np.zeros(mesh.n_cells, dtype=int),
    )
    mesh_maker.interface.boundary.absorber(
        num_layers=1, num_partitions=3, partition_algo="metis",
        geometry="Rectangular", boundary_type="Rayleigh",
        rayleigh_damping=0.95, match_damping=False,
    )
    with pytest.raises(PartitionerError, match="nonempty partitions"):
        mesh_maker.assembler.assemble(merge_points=False, progress_callback=lambda *_: None)
