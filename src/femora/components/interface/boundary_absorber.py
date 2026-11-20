# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Rectangular absorbing-boundary augmentation for assembled meshes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Optional

import tqdm
import vtk
from numpy import (
    abs,
    arange,
    array,
    concatenate,
    float32,
    full,
    int16,
    int32,
    meshgrid,
    ones,
    repeat,
    uint16,
    unique,
    where,
    zeros,
)
from pykdtree.kdtree import KDTree as pykdtree
from pyvista import Cube, MultiBlock, StructuredGrid

from femora.constants import FEMORA_MAX_NDF
from femora.components.partitioner import PartitionerError, PartitionerRegistry

if TYPE_CHECKING:
    from femora.core.model import Model


@contextmanager
def _suppress_vtk_clip_warning():
    """Suppress noisy VTK clip warnings for the rectangular absorber path."""
    previous_state = vtk.vtkObject.GetGlobalWarningDisplay()
    vtk.vtkObject.GlobalWarningDisplayOff()
    try:
        yield
    finally:
        if previous_state:
            vtk.vtkObject.GlobalWarningDisplayOn()
        else:
            vtk.vtkObject.GlobalWarningDisplayOff()


def _normalize_absorber_kwargs(
    *,
    num_layers: Optional[int] = None,
    num_partitions: Optional[int] = None,
    partition_algo: Optional[str] = None,
    geometry: Optional[str] = None,
    boundary_type: Optional[str] = None,
    rayleigh_damping: Optional[float] = None,
    match_damping: Optional[bool] = None,
    progress_callback: Optional[Callable] = None,
    **legacy_kwargs,
) -> dict:
    """Normalize and validate keyword arguments for boundary absorber creation.

    Args:
        num_layers: Number of absorbing cell layers.
        num_partitions: Number of domain partitions/cores for parallel processing.
        partition_algo: "kd-tree" uses VTK's spatial partitioner, which may
            round the requested count upward. "metis" uses the shared mesh
            partitioner, requires pymetis, and checks for the exact requested
            number of nonempty absorber partitions.
        geometry: Boundary layer geometry. Must be "Rectangular" or "Cylindrical".
        boundary_type: Boundary absorber formulation type. One of "PML", "Rayleigh", or "ASDA".
        rayleigh_damping: Rayleigh damping factor. Defaults to 0.95.
        match_damping: If True, matches existing model damping rather than applying new.
        progress_callback: Optional callback receiving float values to track progress.
        **legacy_kwargs: Legacy snakeCase/camelCase arguments for backward compatibility.

    Returns:
        A dictionary of normalized and validated parameter values.

    Raises:
        TypeError: If required parameters are missing.
        ValueError: If argument values are mathematically invalid or unsupported.
        NotImplementedError: If unsupported experimental formulations are requested.
    """
    num_layers = num_layers if num_layers is not None else legacy_kwargs.get("numLayers")
    num_partitions = num_partitions if num_partitions is not None else legacy_kwargs.get("numPartitions")
    partition_algo = partition_algo if partition_algo is not None else legacy_kwargs.get("partitionAlgo")
    geometry = geometry if geometry is not None else legacy_kwargs.get("geometry")
    boundary_type = boundary_type if boundary_type is not None else legacy_kwargs.get("type")
    if rayleigh_damping is None:
        rayleigh_damping = legacy_kwargs.get("rayleighDamping", 0.95)
    if match_damping is None:
        match_damping = legacy_kwargs.get("matchDamping", False)
    if progress_callback is None:
        progress_callback = legacy_kwargs.get("progress_callback")

    if num_layers is None:
        raise TypeError("absorber() missing required argument: num_layers")
    if num_partitions is None:
        raise TypeError("absorber() missing required argument: num_partitions")
    if partition_algo is None:
        raise TypeError("absorber() missing required argument: partition_algo")
    if geometry is None:
        raise TypeError("absorber() missing required argument: geometry")
    if boundary_type is None:
        raise ValueError(
            "Type of the absorbing layer should be provided. "
            "The type could be one of ['PML', 'Rayleigh', 'ASDA']"
        )

    if num_layers < 1:
        raise ValueError("Number of layers should be greater than 0")
    if num_partitions < 0:
        raise ValueError("Number of partitions should be greater or equal to 0")
    if geometry not in ["Rectangular", "Cylindrical"]:
        raise ValueError("Geometry should be one of ['Rectangular', 'Cylindrical']")
    if partition_algo not in ["kd-tree", "metis"]:
        raise ValueError("Partition algorithm should be one of ['kd-tree', 'metis']")
    if geometry == "Cylindrical":
        raise NotImplementedError("Cylindrical absorbing layer is not implemented yet")
    if boundary_type not in ["PML", "Rayleigh", "ASDA"]:
        raise ValueError("Type of the absorbing layer should be one of ['PML', 'Rayleigh', 'ASDA']")
    if boundary_type == "ASDA":
        raise NotImplementedError("ASDA absorbing layer is not implemented yet")

    return {
        "num_layers": int(num_layers),
        "num_partitions": int(num_partitions),
        "partition_algo": partition_algo,
        "geometry": geometry,
        "boundary_type": boundary_type,
        "rayleigh_damping": float(rayleigh_damping),
        "match_damping": bool(match_damping),
        "progress_callback": progress_callback,
    }


def apply_rectangular_absorbing_layer(mesh_maker: "Model", config: dict) -> bool:
    """Apply a registered rectangular absorbing layer to the assembled mesh.

    This function augments the assembled PyVista grid with PML or Rayleigh absorbing
    layers at the model boundaries (left, right, front, back, bottom) and registers
    the corresponding OpenSees elements and node constraints.

    Args:
        mesh_maker: The Model instance whose assembled mesh is to be augmented.
        config: Dictionary containing normalized absorber parameters.

    Returns:
        True if the absorbing boundary was applied successfully.

    Raises:
        ValueError: If no assembled mesh is found, if partitioning parameters are 
            inconsistent, or if boundary element types or materials are incompatible.
    """
    if mesh_maker.assembled_mesh is None:
        raise ValueError("No mesh found\n Please assemble the mesh first")

    num_layers = config["num_layers"]
    num_partitions = config["num_partitions"]
    partition_algo = config["partition_algo"]
    boundary_type = config["boundary_type"]
    rayleigh_damping = config["rayleigh_damping"]
    match_damping = config["match_damping"]
    progress_callback = config.get("progress_callback")

    if boundary_type == "PML":
        ndof = 9
    else:
        ndof = 3

    mesh = mesh_maker.assembled_mesh.copy()
    num_partitions_existing = mesh.cell_data["Core"].max()
    bounds = mesh.bounds
    eps = 1e-6
    bounds = tuple(array(bounds) + array([eps, -eps, eps, -eps, eps, +10]))

    if num_partitions == 0:
        if num_partitions_existing > 0:
            raise ValueError(
                "The number of partitions should be greater than 0 if your model has partitions"
            )

    cube = Cube(bounds=bounds)
    cube = cube.clip(normal=[0, 0, 1], origin=[0, 0, bounds[5] - eps])
    with _suppress_vtk_clip_warning():
        clipped = mesh.copy().clip_surface(cube, invert=False, crinkle=True)

    cell_centers = clipped.cell_centers(vertex=True)
    cell_centers_coords = cell_centers.points

    xmin, xmax, ymin, ymax, zmin, zmax = cell_centers.bounds

    left = abs(cell_centers_coords[:, 0] - xmin) < eps
    right = abs(cell_centers_coords[:, 0] - xmax) < eps
    front = abs(cell_centers_coords[:, 1] - ymin) < eps
    back = abs(cell_centers_coords[:, 1] - ymax) < eps
    bottom = abs(cell_centers_coords[:, 2] - zmin) < eps

    clipped.cell_data["absRegion"] = zeros(clipped.n_cells, dtype=int)
    clipped.cell_data["absRegion"][left] = 1
    clipped.cell_data["absRegion"][right] = 2
    clipped.cell_data["absRegion"][front] = 3
    clipped.cell_data["absRegion"][back] = 4
    clipped.cell_data["absRegion"][bottom] = 5
    clipped.cell_data["absRegion"][left & front] = 6
    clipped.cell_data["absRegion"][left & back] = 7
    clipped.cell_data["absRegion"][right & front] = 8
    clipped.cell_data["absRegion"][right & back] = 9
    clipped.cell_data["absRegion"][left & bottom] = 10
    clipped.cell_data["absRegion"][right & bottom] = 11
    clipped.cell_data["absRegion"][front & bottom] = 12
    clipped.cell_data["absRegion"][back & bottom] = 13
    clipped.cell_data["absRegion"][left & front & bottom] = 14
    clipped.cell_data["absRegion"][left & back & bottom] = 15
    clipped.cell_data["absRegion"][right & front & bottom] = 16
    clipped.cell_data["absRegion"][right & back & bottom] = 17

    cell_centers.cell_data["absRegion"] = clipped.cell_data["absRegion"]
    normals = [
        [-1, 0, 0],
        [1, 0, 0],
        [0, -1, 0],
        [0, 1, 0],
        [0, 0, -1],
        [-1, -1, 0],
        [-1, 1, 0],
        [1, -1, 0],
        [1, 1, 0],
        [-1, 0, -1],
        [1, 0, -1],
        [0, -1, -1],
        [0, 1, -1],
        [-1, -1, -1],
        [-1, 1, -1],
        [1, -1, -1],
        [1, 1, -1],
    ]

    absorbing = MultiBlock()

    total_cells = clipped.n_cells
    tqdm_progress = tqdm.tqdm(range(total_cells), desc="Boundary absorber", leave=False)
    tqdm_progress.reset()
    material_tags = []
    absorbing_regions = []
    element_tags = []
    region_tags = []

    for i in range(total_cells):
        cell = clipped.get_cell(i)
        xmin, xmax, ymin, ymax, zmin, zmax = cell.bounds
        dx = abs((xmax - xmin))
        dy = abs((ymax - ymin))
        dz = abs((zmax - zmin))

        absregion = clipped.cell_data["absRegion"][i]
        material_tag = clipped.cell_data["MaterialTag"][i]
        element_tag = clipped.cell_data["ElementTag"][i]
        region_tag = clipped.cell_data["Region"][i]
        normal = array(normals[absregion - 1])
        coords = cell.points + normal * num_layers * array([dx, dy, dz])
        coords = concatenate([coords, cell.points])
        xmin, ymin, zmin = coords.min(axis=0)
        xmax, ymax, zmax = coords.max(axis=0)
        x = arange(xmin, xmax + 1e-6, dx)
        y = arange(ymin, ymax + 1e-6, dy)
        z = arange(zmin, zmax + 1e-6, dz)
        x_grid, y_grid, z_grid = meshgrid(x, y, z, indexing="ij")
        tmpmesh = StructuredGrid(x_grid, y_grid, z_grid)

        material_tags.append(material_tag)
        absorbing_regions.append(absregion)
        element_tags.append(element_tag)
        region_tags.append(region_tag)

        absorbing.append(tmpmesh)
        tqdm_progress.update(1)
        if progress_callback:
            progress_callback((i + 1) / total_cells * 80)

    tqdm_progress.close()

    total_absorbing_cells = sum(block.n_cells for block in absorbing)
    material_tag_array = zeros(total_absorbing_cells, dtype=uint16)
    absorbing_region_array = zeros(total_absorbing_cells, dtype=uint16)
    element_tag_array = zeros(total_absorbing_cells, dtype=uint16)
    region_tag_array = zeros(total_absorbing_cells, dtype=uint16)

    offset = 0
    for i, block in enumerate(absorbing):
        n_cells = block.n_cells
        material_tag_array[offset : offset + n_cells] = repeat(material_tags[i], n_cells).astype(uint16)
        absorbing_region_array[offset : offset + n_cells] = repeat(absorbing_regions[i], n_cells).astype(
            uint16
        )
        element_tag_array[offset : offset + n_cells] = repeat(element_tags[i], n_cells).astype(uint16)
        region_tag_array[offset : offset + n_cells] = repeat(region_tags[i], n_cells).astype(uint16)
        offset += n_cells
        if progress_callback:
            progress_callback((i + 1) / absorbing.n_blocks * 20 + 80)

    absorbing = absorbing.combine(merge_points=True)
    absorbing.cell_data["MaterialTag"] = material_tag_array
    absorbing.cell_data["AbsorbingRegion"] = absorbing_region_array
    absorbing.cell_data["ElementTag"] = element_tag_array
    absorbing.cell_data["Region"] = region_tag_array

    absorbing_idx = absorbing.find_cells_within_bounds(cell_centers.bounds)
    indices = ones(absorbing.n_cells, dtype=bool)
    indices[absorbing_idx] = False
    absorbing = absorbing.extract_cells(indices)
    absorbing = absorbing.clean(
        tolerance=1e-6,
        remove_unused_points=True,
        produce_merge_map=False,
        average_point_data=True,
        progress_bar=False,
    )

    mat_tag = absorbing.cell_data["MaterialTag"]
    ele_tag = absorbing.cell_data["ElementTag"]
    reg_tag = absorbing.cell_data["AbsorbingRegion"]
    region_tag = absorbing.cell_data["Region"]

    absorbing.clear_data()
    absorbing.cell_data["MaterialTag"] = mat_tag
    absorbing.cell_data["ElementTag"] = ele_tag
    absorbing.cell_data["AbsorbingRegion"] = reg_tag
    absorbing.cell_data["Region"] = region_tag
    absorbing.point_data["ndf"] = full(absorbing.n_points, ndof, dtype=uint16)
    absorbing.point_data["Mass"] = full(
        shape=(absorbing.n_points, FEMORA_MAX_NDF), fill_value=0.0, dtype=float32
    )
    absorbing.cell_data["SectionTag"] = full(absorbing.n_cells, 0, dtype=uint16)
    absorbing.point_data["MeshPartTag_pointdata"] = full(absorbing.n_points, 0, dtype=uint16)
    absorbing.cell_data["MeshPartTag_celldata"] = full(absorbing.n_cells, 0, dtype=uint16)
    absorber_part = mesh_maker._register_femora_part(
        kind="absorber",
        name=f"{boundary_type.lower()}_absorber",
    )
    absorbing.cell_data["FemoraPartTag"] = full(absorbing.n_cells, absorber_part.tag, dtype=int32)
    absorbing.cell_data["FemoraPartKind"] = full(absorbing.n_cells, absorber_part.kind_id, dtype=int16)
    absorbing.cell_data["Core"] = full(absorbing.n_cells, 0, dtype=int)

    if boundary_type == "PML":
        ele_tags = unique(absorbing.cell_data["ElementTag"])
        pml_tags = {}

        xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
        rd_width_x = xmax - xmin
        rd_width_y = ymax - ymin
        rd_depth = zmax - zmin
        rd_center_x = (xmax + xmin) / 2
        rd_center_y = (ymax + ymin) / 2
        rd_center_z = zmax

        for tag in ele_tags:
            ele = mesh_maker.element.get(tag)

            if ele.element_type not in ["stdBrick", "bbarBrick", "SSPbrick"]:
                raise ValueError(
                    f"boundary elements should be of type stdBrick or bbarBrick or SSPbrick not {ele.element_type}"
                )

            mat = ele.get_material()

            if mat.material_name != "ElasticIsotropic" or mat.material_type != "nDMaterial":
                raise ValueError(
                    f"boundary elements should have an ElasticIsotropic material not {mat.material_name} {mat.material_type}"
                )

            pml_ele = mesh_maker.element.brick.pml3d(
                ndof=ndof,
                material=mat,
                gamma=0.5,
                beta=0.25,
                eta=1.0 / 12.0,
                ksi=1.0 / 48.0,
                PML_Thickness=num_layers * dx,
                m=2,
                R=1.0e-8,
                meshType="Box",
                meshTypeParameters=[
                    rd_center_x,
                    rd_center_y,
                    rd_center_z,
                    rd_width_x,
                    rd_width_y,
                    rd_depth,
                ],
            )

            pml_tags[tag] = pml_ele.tag

        for tag in ele_tags:
            absorbing.cell_data["ElementTag"][absorbing.cell_data["ElementTag"] == tag] = pml_tags[tag]

    if num_partitions > 1:
        if partition_algo == "metis":
            labels = PartitionerRegistry.partition(
                absorbing, num_partitions, partitioner=partition_algo,
            )
            if len(unique(labels)) != num_partitions:
                raise PartitionerError(
                    f"Absorber METIS partitioning requested {num_partitions} "
                    f"nonempty partitions, but produced {len(unique(labels))}."
                )
            absorbing.cell_data["Core"] = labels + num_partitions_existing + 1
        else:
            # Preserve the existing VTK KD-tree layout for existing models.
            partitions = absorbing.partition(num_partitions, generate_global_id=True, as_composite=True)
            for i, partition in enumerate(partitions):
                ids = partition.cell_data["vtkGlobalCellIds"]
                absorbing.cell_data["Core"][ids] = i + num_partitions_existing + 1
            del partitions

    elif num_partitions == 1:
        absorbing.cell_data["Core"] = full(absorbing.n_cells, num_partitions_existing + 1, dtype=int)

    if boundary_type == "Rayleigh":
        if not match_damping:
            damping = mesh_maker.damping.frequency_rayleigh(damping_factor=rayleigh_damping)
            region = mesh_maker.region.element(damping=damping)
            absorbing.cell_data["Region"] = full(absorbing.n_cells, region.tag, dtype=uint16)

    if boundary_type == "PML":
        if not match_damping:
            damping = mesh_maker.damping.frequency_rayleigh(damping_factor=rayleigh_damping)
            region = mesh_maker.region.element(damping=damping)
            absorbing.cell_data["Region"] = full(absorbing.n_cells, region.tag, dtype=uint16)

    mesh.cell_data["AbsorbingRegion"] = zeros(mesh.n_cells, dtype=uint16)

    if boundary_type == "PML":
        absorbing_centers = absorbing.cell_centers(vertex=True).points
        tree = pykdtree(absorbing_centers)
        tree.query(cell_centers_coords, k=1)

    mesh_maker.assembled_mesh = mesh.merge(
        absorbing,
        merge_points=False,
        tolerance=1e-6,
        inplace=False,
        progress_bar=False,
    )
    mesh_maker.assembled_mesh.set_active_scalars("AbsorbingRegion")

    if boundary_type == "Rayleigh":
        interfacepoints = mesh.points
        xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
        xmin = xmin + eps
        xmax = xmax - eps
        ymin = ymin + eps
        ymax = ymax - eps
        zmin = zmin + eps
        zmax = zmax + 10
        mask = (
            (interfacepoints[:, 0] > xmin)
            & (interfacepoints[:, 0] < xmax)
            & (interfacepoints[:, 1] > ymin)
            & (interfacepoints[:, 1] < ymax)
            & (interfacepoints[:, 2] > zmin)
            & (interfacepoints[:, 2] < zmax)
        )
        mask = where(~mask)
        interfacepoints = interfacepoints[mask]
        tree = pykdtree(mesh_maker.assembled_mesh.points)
        _distances, indices = tree.query(interfacepoints, k=2)

        # Array-constrained cleaning only merges geometrically coincident points;
        # snap the generated shell interface to the source mesh before cleaning.
        mesh_maker.assembled_mesh.points[indices] = interfacepoints[:, None, :]
        mesh_maker.assembled_mesh.point_data["drm_absorbing_interface"] = arange(
            mesh_maker.assembled_mesh.n_points, dtype=int
        )
        mesh_maker.assembled_mesh.point_data["drm_absorbing_interface"][indices.flatten()] = -1
        mesh_maker.assembled_mesh = mesh_maker.assembled_mesh.clean(
            tolerance=0.0001,
            remove_unused_points=False,
            produce_merge_map=False,
            average_point_data=False,
            merging_array_name="drm_absorbing_interface",
            progress_bar=False,
        )
        del mesh_maker.assembled_mesh.point_data["drm_absorbing_interface"]

    elif boundary_type == "PML":
        interfacepoints = mesh.points
        xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
        xmin = xmin + eps
        xmax = xmax - eps
        ymin = ymin + eps
        ymax = ymax - eps
        zmin = zmin + eps
        zmax = zmax + 10

        mask = (
            (interfacepoints[:, 0] > xmin)
            & (interfacepoints[:, 0] < xmax)
            & (interfacepoints[:, 1] > ymin)
            & (interfacepoints[:, 1] < ymax)
            & (interfacepoints[:, 2] > zmin)
            & (interfacepoints[:, 2] < zmax)
        )
        mask = where(~mask)
        interfacepoints = interfacepoints[mask]

        tree = pykdtree(mesh_maker.assembled_mesh.points)
        distances, indices = tree.query(interfacepoints, k=2)

        distances = abs(distances)
        if distances.max() > 1e-6:
            raise ValueError("The PML layer mesh points are not matching with the original mesh points")

        start_node_tag = mesh_maker._start_nodetag
        for index in indices:
            ndf1 = mesh_maker.assembled_mesh.point_data["ndf"][index[0]]
            ndf2 = mesh_maker.assembled_mesh.point_data["ndf"][index[1]]

            if ndf1 == 9 and ndf2 == 3:
                master_node = index[1] + start_node_tag
                slave_node = index[0] + start_node_tag
            elif ndf1 == 3 and ndf2 == 9:
                master_node = index[0] + start_node_tag
                slave_node = index[1] + start_node_tag
            else:
                raise ValueError(
                    "The PML layer node should have 9 dof and the original mesh should have at least 3 dof"
                )

            mesh_maker.constraint.mp.equal_dof(
                master_node,
                [slave_node],
                [1, 2, 3],
            )

    return True
