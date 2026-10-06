# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import List
from collections import defaultdict
# import time

import numpy as np
import pyvista as pv
from pykdtree.kdtree import KDTree

from femora.core.interface_base import InterfaceBase
from femora.components.event.mixins import GeneratesMeshMixin
from femora.core.meshpart_base import MeshPart
from femora.core.event_bus import FemoraEvent
from femora.constants import FEMORA_MAX_NDF

class EmbeddedNodeInterface(InterfaceBase, GeneratesMeshMixin):
    """Embedded node constraint contact interface.

    EmbeddedNodeInterface models multi-point constraint boundary connections in 
    OpenSees by constraining the displacements (and optionally rotations) of a 
    constrained node to be a weighted average of a set of surrounding retained nodes. 
    It leverages a penalty approach element formulation internally.

    Tcl form:
        None (renders internally via OpenSees interface-specific TCL commands).

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        # Create an embedded node interface mapping a constrained node part to retained parts
        interface = model.interface.node_interface(
            name="node_soil_interface",
            constrained_node="pile_head_node",
            retained_nodes=["soil_volume"],
            rot=True,
            p=True,
            K=1e10,
        )
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__", "plot"],
    }

    def _subscribe_events(self) -> None:
        """Subscribe this interface to post-assemble mesh generation events."""
        self._model_events().subscribe(FemoraEvent.POST_ASSEMBLE, self._on_post_assemble)

    def _unsubscribe_events(self) -> None:
        """Unsubscribe this interface from all model events."""
        self._model_events().unsubscribe(FemoraEvent.POST_ASSEMBLE, self._on_post_assemble)

    def __init__(
        self,
        name: str,
        constrained_node: 'MeshPart | str | int',
        retained_nodes: 'List[MeshPart | str | int] | None' = None,
        rot: bool = False, 
        p: bool = False, 
        K: float | None = None,
        KP: float | None = None,
        offset: float = None,
        use_mesh_part_points = True,
        normal_filter: list[float] | None = None,
        filter_tolerance: float = 0.98,
        contact: bool = False,
        Kn: float = 1e8,
        Kt: float = 1e8,
        mu: float = 0.5,
        int_type: int = 1,
        *,
        meshpart,

    ) -> None:
        """Initialize the EmbeddedNodeInterface.

        Args:
            name: Unique name of the node interface.
            constrained_node: The constrained node part instance, name, or tag.
            retained_nodes: Optional list of retained node part instances, names, or tags.
                If None, uses all mesh parts in the model except the constrained node.
            rot: If True, constrains rotational degrees of freedom. Defaults to False.
            p: If True, activates pressure-dof constraints. Defaults to False.
            K: Penalty stiffness parameter for translation constraints.
            KP: Penalty stiffness parameter for rotational constraints.
            offset: Geometric normal offset for locating coupling nodes. Defaults to None.
            use_mesh_part_points: If True, uses mesh part nodal points directly. Defaults to True.
            normal_filter: Optional 3D orientation direction vector to filter points. Defaults to None.
            filter_tolerance: Direction cosine tolerance for the normal filter. Defaults to 0.98.
            contact: If True, creates a frictional ``EmbeddedNodeContact``
                interface. Otherwise, creates a tied ``ASDEmbeddedNodeElement``
                interface. Defaults to False.
            Kn: Normal penalty stiffness for contact. Defaults to 1e8.
            Kt: Tangential penalty stiffness for contact. Defaults to 1e8.
            mu: Friction coefficient for contact. Defaults to 0.5.
            int_type: Contact integration type: 0 for implicit or 1 for
                IMPL-EX. Defaults to 1.
            meshpart: MeshPart registry manager from the parent model.

        Raises:
            ValueError: If `offset` is negative or if constrained node matches retained node tag.
        """
        
        self.constrained_node = meshpart.resolve(constrained_node)
        if retained_nodes:
            self.retained_nodes = [meshpart.resolve(mp) for mp in retained_nodes]
        else:
            self.retained_nodes = list(meshpart.get_all().values())
            self.retained_nodes.remove(self.constrained_node)


        if offset is None:
            offset = 0.0
        if offset < 0:
            raise ValueError("Offset must be a positive number")
        self.offset = offset

        if offset > 1e-2 and use_mesh_part_points:
            print("Warning: Using offset greater than 1e-2 with use_mesh_part_points=True may lead to unexpected results.")
        self._use_mesh_part_points = use_mesh_part_points

        self._rot = rot
        self._p = p
        self._K = K
        self._KP = KP
        if normal_filter is not None:
            normal_filter = np.array(normal_filter) / np.linalg.norm(normal_filter)
        self._normal_filter = normal_filter
        self._filter_tolerance = filter_tolerance
        self._contact = bool(contact)
        self._Kn = Kn
        self._Kt = Kt
        self._mu = mu
        self._int_type = int_type
        if self._contact and (rot or p or K is not None or KP is not None):
            raise ValueError(
                "Contact interfaces do not support rot, p, K, or KP; "
                "these options belong to tied embedded-node interfaces"
            )
        self._interface_part_tag: int | None = None

        if self._contact:
            if not self._use_mesh_part_points:
                self._use_mesh_part_points = True
                print("Warning: contact=True automatically enables use_mesh_part_points")
            

        super().__init__(name, owners=[self.constrained_node.user_name])
        

    @staticmethod
    def _extract_surface_compat(mesh: pv.UnstructuredGrid) -> pv.PolyData:
        """Extract a surface while supporting multiple PyVista versions.

        Newer PyVista versions accept ``algorithm=...`` and warn when the
        argument is omitted. Older versions do not accept that keyword at all.
        This helper preserves the current extraction behavior on new versions
        and falls back cleanly on older ones.
        """
        try:
            return mesh.extract_surface(algorithm="dataset_surface")
        except TypeError:
            return mesh.extract_surface()

    def _collect_embedding_data(
        self,
        assembled_mesh: pv.UnstructuredGrid,
    ) -> tuple[pv.UnstructuredGrid, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Collect selected host cells and constrained points for embedding.

        Returns:
            A tuple containing:
            - tetrahedralized working mesh
            - original assembled cell ids for selected host cells
            - selected offset points
            - selected point ids on the constrained part
            - selected normals for those points
        """
        tetrahedra_mesh = self._tetrahedralize(assembled_mesh)
        offset_points, point_ids, normals = self._create_offset_mesh(assembled_mesh)

        tetra_mask = tetrahedra_mesh.celltypes == pv.CellType.TETRA
        retained_mask = np.zeros(tetrahedra_mesh.n_cells, dtype=bool)
        for part in self.retained_nodes:
            retained_mask |= tetrahedra_mesh.cell_data['MeshPartTag_celldata'] == part.tag
        cell_mask = tetra_mask & retained_mask

        tetrahedra_mesh.cell_data['CellIndex'] = np.arange(tetrahedra_mesh.n_cells, dtype=int)
        tetrahedra_mesh_filtered = tetrahedra_mesh.extract_cells(cell_mask)
        cell_ids = tetrahedra_mesh_filtered.find_containing_cell(offset_points)
        point_mask = cell_ids != -1

        selected_cells = cell_ids[point_mask]
        selected_points = offset_points[point_mask]
        selected_normals = normals[point_mask]
        selected_point_ids = point_ids[point_mask]

        if selected_point_ids.size == 0:
            msg = (
                f"Interface '{self.name}': No intersection found between constrained node "
                f"'{self.constrained_node.user_name}' and retained nodes.\n"
                "Possible reasons:\n"
                "1. The constrained mesh part is not inside the retained mesh parts.\n"
                f"2. The normal_filter {self._normal_filter} (tol={self._filter_tolerance}) "
                "might be too restrictive or in a wrong direction."
            )
            raise ValueError(msg)

        original_cells = tetrahedra_mesh_filtered.cell_data['CellIndex'][selected_cells]
        return (
            tetrahedra_mesh,
            np.asarray(original_cells, dtype=int),
            np.asarray(selected_points),
            np.asarray(selected_point_ids, dtype=int),
            np.asarray(selected_normals),
        )

    def plot(
        self,
        *,
        show_mesh: bool = True,
        show_selected_hosts: bool = True,
        show_generated_interface: bool = True,
        show_normals: bool = True,
        show_edges: bool = True,
        mesh_opacity: float = 0.08,
        host_opacity: float = 0.55,
        interface_opacity: float = 0.90,
        constrained_color: str = "black",
        host_color: str = "orange",
        point_color: str = "deepskyblue",
        interface_color: str = "crimson",
        normal_color: str = "seagreen",
        off_screen: bool = False,
        screenshot: str | None = None,
        window_size: tuple[int, int] = (1400, 900),
        return_plotter: bool = False,
    ) -> pv.Plotter | None:
        """Plot the assembled embedded-node interface selection.

        The plot shows the constrained mesh part, the selected retained host
        cells that contain constrained points, the constrained points used by
        the interface, optional normals, and the generated interface cells when
        they are present in the assembled mesh.
        """
        if self._owner is None:
            raise RuntimeError(
                f"EmbeddedNodeInterface '{self.name}' must be managed before plotting."
            )

        mesh = self._owner._mesh_maker.assembler.get_mesh()
        if mesh is None:
            raise RuntimeError("The model must be assembled before plotting an interface.")

        (
            tetrahedra_mesh,
            original_cells,
            selected_points,
            _selected_point_ids,
            selected_normals,
        ) = self._collect_embedding_data(mesh.copy())

        constrained_mask = mesh.cell_data['MeshPartTag_celldata'] == self.constrained_node.tag
        constrained_mesh = mesh.extract_cells(constrained_mask, progress_bar=False)
        host_mesh = tetrahedra_mesh.extract_cells(original_cells, progress_bar=False)

        interface_mesh = None
        if (
            show_generated_interface
            and self._interface_part_tag is not None
            and 'FemoraPartTag' in mesh.cell_data
        ):
            interface_mask = mesh.cell_data['FemoraPartTag'] == self._interface_part_tag
            if np.any(interface_mask):
                interface_mesh = mesh.extract_cells(interface_mask, progress_bar=False)

        plotter = pv.Plotter(off_screen=off_screen, window_size=window_size)
        plotter.add_text(
            (
                f"{self.name}: selected points={selected_points.shape[0]}, "
                f"host cells={original_cells.size}"
            ),
            font_size=12,
        )

        if show_mesh:
            plotter.add_mesh(
                mesh,
                style="wireframe",
                color="lightgray",
                opacity=mesh_opacity,
            )

        if show_selected_hosts:
            plotter.add_mesh(
                host_mesh,
                color=host_color,
                opacity=host_opacity,
                show_edges=show_edges,
            )

        plotter.add_mesh(
            constrained_mesh,
            color=constrained_color,
            line_width=8,
            point_size=10,
            render_points_as_spheres=True,
        )
        plotter.add_mesh(
            pv.PolyData(selected_points),
            color=point_color,
            point_size=14,
            render_points_as_spheres=True,
        )

        if show_normals and selected_points.size > 0:
            arrow_scale = max(float(self.offset), 1.0) * 0.35
            glyph_source = pv.Arrow()
            glyphs = pv.PolyData(selected_points)
            # For contact, show the normal used by EmbeddedNodeContact rather
            # than the constrained surface normal used to find the host cell.
            glyphs["vectors"] = -selected_normals if self._contact else selected_normals
            glyphs = glyphs.glyph(
                orient="vectors",
                scale=False,
                factor=arrow_scale,
                geom=glyph_source,
            )
            plotter.add_mesh(glyphs, color=normal_color)

        if interface_mesh is not None:
            interface_points = interface_mesh.cell_centers(vertex=True)
            plotter.add_mesh(
                interface_points,
                color=interface_color,
                point_size=12,
                render_points_as_spheres=True,
                opacity=interface_opacity,
            )

        plotter.view_isometric()
        if screenshot:
            plotter.screenshot(screenshot)
        if return_plotter:
            return plotter
        plotter.show()
        plotter.close()
        return None


    def _create_offset_mesh(self, asembelled_mesh: pv.UnstructuredGrid) -> pv.PolyData:
        """Construct the geometric surface representing offset coupling points.

        Args:
            asembelled_mesh: The main assembled PyVista grid.

        Returns:
            The PyVista PolyData surface representing the offset coupling points.

        Raises:
            ValueError: If the mesh is not a PolyData or UnstructuredGrid.
        """
        if self.offset is None:
            #check if the mesh is a pv.PolyData or pv.UnstructuredGrid
            if isinstance(self.constrained_node.mesh, pv.PolyData):
                return self.constrained_node.mesh
            elif isinstance(self.constrained_node.mesh, pv.UnstructuredGrid):
                return self._extract_surface_compat(self.constrained_node.mesh)
            else:
                raise ValueError("Mesh must be a pv.PolyData or pv.UnstructuredGrid")
        else:

            # offset the mesh
            asembelled_mesh.point_data['NodeIndex'] = np.arange(asembelled_mesh.n_points)
            constrained_mesh = asembelled_mesh.extract_cells(
                asembelled_mesh.cell_data['MeshPartTag_celldata'] == self.constrained_node.tag
            )
            original_mesh = self._extract_surface_compat(constrained_mesh)
            # clean_original_mesh = original_mesh.clean(point_merging=True, tolerance=1e-6)

            # mesh with normals
            normal_filter = self._normal_filter
            filter_tolerance = self._filter_tolerance
            if normal_filter is None:
                if abs(self.offset) <= 1e-12:
                    normals = np.zeros((original_mesh.n_points, 3))
                else:
                    try:
                        mesh_with_normals = original_mesh.compute_normals(
                                                        cell_normals=False, 
                                                        point_normals=True, 
                                                        inplace=False,
                                                        split_vertices= False,
                                                )
                        normals = mesh_with_normals.point_data['Normals']
                    except Exception as e:
                        print("warning: could not compute the normals assuming zero normals")
                        normals = np.zeros((original_mesh.n_points, 3))
                mask = np.ones(original_mesh.n_points, dtype=bool)
                original_mesh.point_data['Normals'] = normals
            else:
                mesh_with_normals = original_mesh.compute_normals(
                                                cell_normals=False, 
                                                point_normals=True, 
                                                inplace=False,
                                                split_vertices= True
                                            )
                mask = np.zeros(original_mesh.n_points, dtype=bool)
                pyvistaOriginalPointIds = mesh_with_normals.point_data['pyvistaOriginalPointIds']
                normals = np.zeros((original_mesh.n_points, 3))
                for i in range(mesh_with_normals.n_points):
                    normal = mesh_with_normals.point_data['Normals'][i]
                    # dot product
                    dot_product = np.dot(normal, normal_filter)
                    if dot_product > filter_tolerance:
                        mask[pyvistaOriginalPointIds[i]] = True

                ids = np.where(mask)[0]
                normals[ids] = np.array(normal_filter)
                original_mesh.point_data['Normals'] = normals
                    




            points = original_mesh.points
            normals = original_mesh.point_data['Normals']
            offset_dist = self.offset
            new_points = points + (normals * offset_dist)
            

            offset_mesh = original_mesh.copy()
            offset_mesh.points = new_points

            

            # find the points in the constrained mesh 
            tree = KDTree(constrained_mesh.points)
            distances, indices = tree.query(points, k=1, distance_upper_bound=1e-6)
            
            # check that all the point are found
            if np.any(distances > 1e-6):
                raise ValueError("Some points in the offset mesh can not be related to the constrained mesh")
            
            # create a new mesh with the offset points
            point_ids = constrained_mesh.point_data['NodeIndex'][indices]

            # apply the mask to the points
            offset_mesh = offset_mesh.extract_points(mask, include_cells=False)
            point_ids = point_ids[mask]
            offset_points = offset_mesh.points
            normals = offset_mesh.point_data["Normals"]


            # now we need to filter out the point_ids that are in the retained mesh
            mask = np.zeros(asembelled_mesh.n_cells, dtype=bool)
            for part in self.retained_nodes:
                mask |= asembelled_mesh.cell_data['MeshPartTag_celldata'] == part.tag
            
            retained_mesh = asembelled_mesh.extract_cells(mask)
            reained_point_ids = retained_mesh.point_data['NodeIndex']

            mask = np.ones(len(point_ids), dtype=bool)
            for i, point_id in enumerate(point_ids):
                if point_id in reained_point_ids:
                    mask[i] = False
            
            offset_points = offset_points[mask]
            point_ids = point_ids[mask]
            normals = normals[mask]


            # pl = pv.Plotter()
            # pl.add_mesh(constrained_mesh, opacity=0.5, show_edges=True, color='gray')
            # pl.add_mesh(pv.PolyData(offset_points), opacity=0.5, show_edges=True, color='blue')
            # pl.show()
            return offset_points, point_ids, normals
        



    def _on_post_assemble(self, assembled_mesh: pv.UnstructuredGrid) -> None:
        """Detect the nodes from the offset mesh that are inside tetrahedra elements of the retained nodes.

        Args:
            assembled_mesh: The main assembled PyVista grid.

        Raises:
            ValueError: If required model parts or elements cannot be found.
        """
        # 1) get the asembelled mesh
        asembelled_mesh = assembled_mesh.copy()

        if asembelled_mesh is None:
            raise ValueError("Assembled mesh not found; please run Assembler first.")
        
        tetrahedra_mesh, original_cells, selected_points, point_ids, selected_normals = (
            self._collect_embedding_data(asembelled_mesh)
        )


        # 9) create tet elements
        tet_elements = np.zeros((selected_points.shape[0], 4), dtype=int)
        start = tetrahedra_mesh.offset[original_cells]
        indices = start[:, None] + np.arange(4)
        tet_elements = tetrahedra_mesh.cell_connectivity[indices]





        # 10) create tet cores
        # each selected point is related to a tetrahedron element so the point should be in the core
        # each point id is related to selected_point but the point can be exist in a different core
        tet_cores = tetrahedra_mesh.cell_data['Core'][original_cells]
        point_id_cores = []
        for point_id in point_ids:
            tmp_mesh = asembelled_mesh.extract_points(point_id,include_cells = True)
            point_id_cores.append(np.unique(tmp_mesh.cell_data['Core']))

        

        

        # 11) 
        # pl = pv.Plotter()
        mask = asembelled_mesh.cell_data['MeshPartTag_celldata'] == self.constrained_node.tag
        mask = ~mask
        tmp = tetrahedra_mesh.extract_cells(original_cells)
        tmp = tmp.cell_quality('jacobian')
        if np.any(tmp.cell_data['jacobian'] <= 0):
            raise ValueError("Some tetrahedral elements have negative jacobians")
            
    

        # create a embedded node element
        mesh_maker = self._owner._mesh_maker
        ndf = 3

        # 1. Get references to the existing assembled mesh data
        base_mesh = mesh_maker.assembled_mesh
        old_points = base_mesh.points
        # 2. Offset the indices in the new mesh
        offset = old_points.shape[0]

        start_node_tag = mesh_maker.get_start_node_tag()

        # create the element orientation map 
        orientation_map = {}
        for i in range(point_ids.shape[0]):
            if self._use_mesh_part_points:
                node_tag = point_ids[i] + start_node_tag
            else:
                node_tag = offset + i + start_node_tag
            # Surface normals point from the constrained body toward the host.
            # EmbeddedNodeContact expects the opposite: host (master) to the
            # embedded node (slave).
            orientation_map[node_tag] = (-selected_normals[i]).tolist()
            
        if self._contact:
            embededd_ele = mesh_maker.element.special.embedded_node_contact(
                ndof=ndf,
                Kn=self._Kn,
                Kt=self._Kt,
                mu=self._mu,
                int_type=self._int_type,
                orient_map=orientation_map,
            )
        else:
            embededd_ele = mesh_maker.element.special.asd_embedded_node(
                ndof=ndf,
                rot=self._rot,
                p=self._p,
                K=self._K,
                KP=self._KP,
            )

        # mesh_maker.assembled_mesh.merge(embedded_mesh, merge_points=True, inplace=True)
        old_cells = base_mesh.cells
        old_celltypes = base_mesh.celltypes

        # Extract the cells array. Remember VTK format: [n, p1, p2, ..., n, p1, p2...]
        new_cells_raw = []
        new_celltypes = []
        new_ndf = base_mesh.point_data['ndf'][point_ids]
        num_new_cells = tet_elements.shape[0]
        num_new_points = selected_points.shape[0] if not self._use_mesh_part_points else 0
        tet_cores = np.array(tet_cores, dtype=int)
        for i in range(0, selected_points.shape[0]):
            new_cells_raw.append(5)
            if self._use_mesh_part_points:
                new_cells_raw.append(point_ids[i])  # Constrained node from original mesh
            else:
                new_cells_raw.append(i + offset)  # Constrained node
            for j in tet_elements[i]:
                new_cells_raw.append(j)
            new_celltypes.append(pv.CellType.POLY_VERTEX)

        # 3. Concatenate Point and Cell arrays
        if self._use_mesh_part_points:
            combined_points = old_points
        else:
            combined_points = np.vstack((old_points, selected_points))
            
        combined_cells = np.concatenate((old_cells, new_cells_raw))
        combined_celltypes = np.concatenate((old_celltypes, new_celltypes))

        # 4. Create the final Mesh
        final_mesh = pv.UnstructuredGrid(combined_cells, combined_celltypes, combined_points)

        # 5. Copy over existing data arrays
        # cell data
        final_mesh.cell_data['Core'] = np.concatenate((base_mesh.cell_data['Core'], tet_cores))
        final_mesh.cell_data['ElementTag'] = np.concatenate((base_mesh.cell_data['ElementTag'], np.full(num_new_cells, embededd_ele.tag, dtype=np.uint16)))
        final_mesh.cell_data['MaterialTag'] = np.concatenate((base_mesh.cell_data['MaterialTag'], np.full(num_new_cells, 0, dtype=np.uint16)))
        final_mesh.cell_data['Region'] = np.concatenate((base_mesh.cell_data['Region'], np.full(num_new_cells, 0, dtype=np.uint16)))
        final_mesh.cell_data['MeshPartTag_celldata'] = np.concatenate((base_mesh.cell_data['MeshPartTag_celldata'], np.full(num_new_cells, 0, dtype=np.uint16)))
        interface_part = mesh_maker._register_femora_part(
            kind="interface",
            name=self.name,
        )
        self._interface_part_tag = int(interface_part.tag)
        final_mesh.cell_data['FemoraPartTag'] = np.concatenate((
            base_mesh.cell_data['FemoraPartTag'],
            np.full(num_new_cells, interface_part.tag, dtype=np.int32),
        ))
        final_mesh.cell_data['FemoraPartKind'] = np.concatenate((
            base_mesh.cell_data['FemoraPartKind'],
            np.full(num_new_cells, interface_part.kind_id, dtype=np.int16),
        ))

        # point_data 
        if num_new_points > 0:
            final_mesh.point_data['MeshPartTag_pointdata'] = np.concatenate((base_mesh.point_data['MeshPartTag_pointdata'], np.full(num_new_points, 0, dtype=np.uint16)))
            final_mesh.point_data['Mass'] = np.vstack((base_mesh.point_data['Mass'], np.full(shape=(num_new_points, FEMORA_MAX_NDF), fill_value=0.0, dtype=np.float32)))
            final_mesh.point_data['ndf'] = np.concatenate((base_mesh.point_data['ndf'], new_ndf))
        else:
            final_mesh.point_data['MeshPartTag_pointdata'] = base_mesh.point_data['MeshPartTag_pointdata']
            final_mesh.point_data['Mass'] = base_mesh.point_data['Mass']
            final_mesh.point_data['ndf'] = base_mesh.point_data['ndf']
                                                 

        # 6. Update model-owned assembled mesh
        mesh_maker.assembled_mesh = final_mesh
            



        


            
    def _tetrahedralize(self, mesh: pv.UnstructuredGrid) -> pv.UnstructuredGrid:
        """Decompose hexahedron elements to standard tetrahedrons for contact search.

        Args:
            mesh: The PyVista UnstructuredGrid to decompose.

        Returns:
            The tetrahedralized PyVista UnstructuredGrid.
        """
        new_cells = []
        new_cell_types = []
        parent_indices = [] # Track which original cell each new cell came from
        
        cells = mesh.cells
        cell_types = mesh.celltypes
        offset = 0



        # only tetrahedralize the cells that are from the retained nodes
        mask = np.zeros(mesh.n_cells, dtype=bool)
        for meshpart in self.retained_nodes:
            mask |= mesh.cell_data["MeshPartTag_celldata"] == meshpart.tag
         
        for i in range(mesh.n_cells):
            n_points = cells[offset]
            cell_nodes = cells[offset + 1 : offset + 1 + n_points]
            c_type = cell_types[i]
            
            # 1. Handle Hexahedrons (Decompose)
            if c_type == pv.CellType.HEXAHEDRON and n_points == 8 and mask[i]:
                # Standard 5-tetra decomposition
                tets = [
                    [cell_nodes[0], cell_nodes[1], cell_nodes[2], cell_nodes[5]],
                    [cell_nodes[0], cell_nodes[2], cell_nodes[3], cell_nodes[7]],
                    [cell_nodes[0], cell_nodes[5], cell_nodes[2], cell_nodes[7]], # Internal bridge
                    [cell_nodes[0], cell_nodes[4], cell_nodes[5], cell_nodes[7]],
                    [cell_nodes[2], cell_nodes[5], cell_nodes[6], cell_nodes[7]],
                    [cell_nodes[0], cell_nodes[5], cell_nodes[7], cell_nodes[2]]  # Re-oriented bridge
                ]
                for t in tets:
                    new_cells.extend([4] + t)
                    new_cell_types.append(pv.CellType.TETRA)
                    parent_indices.append(i) # All 5 tets point to the original Hex index
            
            # 2. Handle everything else (Preserve)
            else:
                new_cells.extend([n_points] + list(cell_nodes))
                new_cell_types.append(c_type)
                parent_indices.append(i) # 1-to-1 mapping
                
            offset += n_points + 1

        # Create the new mesh structure
        new_mesh = pv.UnstructuredGrid(np.array(new_cells), np.array(new_cell_types), mesh.points)
        
        # --- Data Preservation ---
        
        # 1. Point Data: Node numbering is identical, so we just copy
        new_mesh.point_data.update(mesh.point_data)
        
        # 2. Cell Data: Use parent_indices to map original data to new cells
        parent_indices = np.array(parent_indices)
        for key, data in mesh.cell_data.items():
            # This handles both scalars and vectors (e.g., stress tensors)
            new_mesh.cell_data[key] = data[parent_indices]
            
        # return new_mesh

        # print(f"New mesh has {new_mesh.n_cells} cells")
        # print(f"New mesh has {new_mesh.n_points} points")
        
        # print cell types
        # print(f"original mesh has {mesh.n_cells} cells")
        # print(f"original mesh has {mesh.n_points} points")


        # check the number of points are equal
        assert new_mesh.n_points == mesh.n_points, "Number of points are not equal in the new and original mesh"
    
        # check the number of cells are equal
        num_hex = mesh.celltypes == pv.CellType.HEXAHEDRON
        num_hex = num_hex & mask
        assert new_mesh.n_cells == mesh.n_cells + 5*sum(num_hex), "Number of cells are not equal in the new and original mesh"        


        # pl = pv.Plotter()
        # pl.add_mesh(new_mesh, color='red', opacity=1.0, style='wireframe')
        # pl.add_mesh(mesh, color='blue', opacity=0.5)
        # pl.show()

        return new_mesh

    


        

    


            
            


            
            

        

    



    
