# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Union
from numpy.typing import ArrayLike

from femora.core.element_base import Element
from femora.core.meshpart_base import MeshPart
from femora.core.region_base import RegionBase
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from pyvista import DataSet
    from femora.components.mesh.general_meshparts import CompositeMesh
    from femora.components.mesh.general_meshparts import ExternalMesh
    from femora.components.mesh.line_meshparts import SingleLineMesh
    from femora.components.mesh.line_meshparts import StructuredLineMesh
    from femora.components.mesh.surface_meshparts import CircularOGrid2D
    from femora.components.mesh.volume_meshparts import CustomRectangularGrid3D
    from femora.components.mesh.volume_meshparts import GeometricStructuredRectangular3D
    from femora.components.mesh.volume_meshparts import StructuredRectangular3D
    from femora.core.model import Model


class _MeshPartNamespace:
    def __init__(self, manager: "MeshPartManager") -> None:
        self._manager = manager


class LineMeshNamespace(_MeshPartNamespace):
    """Line-mesh factories accessed through ``model.meshpart.line``.

    Definitions use the supplied element object and optional region. Factories
    return generated, registered parts; no section creation or final assembly
    is performed. Use density or mass_per_length, not both, for line mass input.
    """

    __doc_controls__ = {"summary": True, "members": ["single_line", "structured_lines"]}

    def single_line(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        x0: float = 0.0,
        y0: float = 0.0,
        z0: float = 0.0,
        x1: float = 1.0,
        y1: float = 0.0,
        z1: float = 0.0,
        number_of_lines: int = 1,
        merge_points: bool = True,
        density: Optional[float] = None,
        mass_per_length: Optional[float] = None,
    ) -> SingleLineMesh:
        """Generate a subdivided straight segment through ``model.meshpart.line``.

        Args:
            user_name (str): Unique registered part name.
            element (Element): Compatible line element definition.
            region (RegionBase | None): Region; None selects the global region.
            x0 (float): Start-point global x coordinate.
            y0 (float): Start-point global y coordinate.
            z0 (float): Start-point global z coordinate.
            x1 (float): End-point global x coordinate.
            y1 (float): End-point global y coordinate.
            z1 (float): End-point global z coordinate.
            number_of_lines (int): Segment subdivision count.
            merge_points (bool): Point-merging option within the generated part.
            density (float | None): Volumetric density for section-based mass.
            mass_per_length (float | None): Alternative explicit line mass density.

        Returns:
            part (MeshPart): Generated and registered SingleLineMesh.

        Note:
            Density and mass_per_length are mutually exclusive. Check component
            mass settings to avoid counting the same physical mass twice.
        """
        from femora.components.mesh.line_meshparts import SingleLineMesh

        component = SingleLineMesh(
            user_name,
            element,
            region,
            x0=x0,
            y0=y0,
            z0=z0,
            x1=x1,
            y1=y1,
            z1=z1,
            number_of_lines=number_of_lines,
            merge_points=merge_points,
            density=density,
            mass_per_length=mass_per_length,
        )
        self._manager.add(component)
        return component

    def structured_lines(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        base_point_x: float = 0.0,
        base_point_y: float = 0.0,
        base_point_z: float = 0.0,
        base_vector_1_x: float = 1.0,
        base_vector_1_y: float = 0.0,
        base_vector_1_z: float = 0.0,
        base_vector_2_x: float = 0.0,
        base_vector_2_y: float = 1.0,
        base_vector_2_z: float = 0.0,
        normal_x: float = 0.0,
        normal_y: float = 0.0,
        normal_z: float = 1.0,
        grid_size_1: int = 10,
        grid_size_2: int = 10,
        spacing_1: float = 1.0,
        spacing_2: float = 1.0,
        length: float = 1.0,
        offset_1: float = 0.0,
        offset_2: float = 0.0,
        number_of_lines: int = 1,
        merge_points: bool = True,
        density: Optional[float] = None,
        mass_per_length: Optional[float] = None,
    ) -> StructuredLineMesh:
        """Generate an array of subdivided line members on a base grid.

        Args:
            user_name (str): Unique registered part name.
            element (Element): Compatible line element definition.
            region (RegionBase | None): Region; None selects the global region.
            base_point_x (float): Base origin global x coordinate.
            base_point_y (float): Base origin global y coordinate.
            base_point_z (float): Base origin global z coordinate.
            base_vector_1_x (float): First grid direction x component.
            base_vector_1_y (float): First grid direction y component.
            base_vector_1_z (float): First grid direction z component.
            base_vector_2_x (float): Second grid direction x component.
            base_vector_2_y (float): Second grid direction y component.
            base_vector_2_z (float): Second grid direction z component.
            normal_x (float): Member direction x component.
            normal_y (float): Member direction y component.
            normal_z (float): Member direction z component.
            grid_size_1 (int): Grid count along the first base direction.
            grid_size_2 (int): Grid count along the second base direction.
            spacing_1 (float): Spacing along the first base direction.
            spacing_2 (float): Spacing along the second base direction.
            length (float): Member length in model length units.
            offset_1 (float): Initial offset along the first grid direction.
            offset_2 (float): Initial offset along the second grid direction.
            number_of_lines (int): Subdivision count per member.
            merge_points (bool): Point-merging option within the generated part.
            density (float | None): Optional volumetric density.
            mass_per_length (float | None): Alternative explicit mass per length.

        Returns:
            part (MeshPart): Registered StructuredLineMesh. Concrete constructor
                validation applies to directions, sizes, and mass inputs.
        """
        from femora.components.mesh.line_meshparts import StructuredLineMesh

        component = StructuredLineMesh(
            user_name,
            element,
            region,
            base_point_x=base_point_x,
            base_point_y=base_point_y,
            base_point_z=base_point_z,
            base_vector_1_x=base_vector_1_x,
            base_vector_1_y=base_vector_1_y,
            base_vector_1_z=base_vector_1_z,
            base_vector_2_x=base_vector_2_x,
            base_vector_2_y=base_vector_2_y,
            base_vector_2_z=base_vector_2_z,
            normal_x=normal_x,
            normal_y=normal_y,
            normal_z=normal_z,
            grid_size_1=grid_size_1,
            grid_size_2=grid_size_2,
            spacing_1=spacing_1,
            spacing_2=spacing_2,
            length=length,
            offset_1=offset_1,
            offset_2=offset_2,
            number_of_lines=number_of_lines,
            merge_points=merge_points,
            density=density,
            mass_per_length=mass_per_length,
        )
        self._manager.add(component)
        return component


class VolumeMeshNamespace(_MeshPartNamespace):
    """Volume-mesh factories accessed through ``model.meshpart.volume``.

    Bounds and coordinates use model length units. Rectangular subdivision
    counts specify cells, not points. Returned parts are registered by name;
    geometry/element validation errors propagate from concrete mesh constructors.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "uniform_rectangular_grid",
            "custom_rectangular_grid",
            "geometric_rectangular_grid",
        ],
    }

    def uniform_rectangular_grid(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        z_min: float,
        z_max: float,
        nx: int,
        ny: int,
        nz: int,
    ) -> StructuredRectangular3D:
        """Generate and register a uniform rectangular Hex8 volume mesh.

        Args:
            user_name (str): Unique part name.
            element (Element): Compatible volume element definition.
            region (RegionBase | None): Region; None uses the global region.
            x_min (float): Lower global x bound.
            x_max (float): Upper global x bound.
            y_min (float): Lower global y bound.
            y_max (float): Upper global y bound.
            z_min (float): Lower global z bound.
            z_max (float): Upper global z bound.
            nx (int): Positive number of x cell subdivisions.
            ny (int): Positive number of y cell subdivisions.
            nz (int): Positive number of z cell subdivisions.

        Returns:
            part (MeshPart): Generated part; assembly remains a separate operation.
        """
        from femora.components.mesh.volume_meshparts import StructuredRectangular3D

        component = StructuredRectangular3D(
            user_name,
            element,
            region,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            z_min=z_min,
            z_max=z_max,
            nx=nx,
            ny=ny,
            nz=nz,
        )
        self._manager.add(component)
        return component

    def custom_rectangular_grid(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        x_coords: str,
        y_coords: str,
        z_coords: str,
    ) -> CustomRectangularGrid3D:
        """Generate and register a rectangular mesh from explicit axis coordinates.

        Args:
            user_name (str): Unique part name.
            element (Element): Compatible volume element definition.
            region (RegionBase | None): Region; None uses the global region.
            x_coords (str): Coordinate input accepted by CustomRectangularGrid3D.
            y_coords (str): Corresponding global y coordinate input.
            z_coords (str): Corresponding global z coordinate input.

        Returns:
            part (MeshPart): Generated, registered volume part. Consult the concrete
                mesh component for coordinate-string syntax and validation rules.
        """
        from femora.components.mesh.volume_meshparts import CustomRectangularGrid3D

        component = CustomRectangularGrid3D(
            user_name, element, region, x_coords=x_coords, y_coords=y_coords, z_coords=z_coords
        )
        self._manager.add(component)
        return component

    def geometric_rectangular_grid(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        z_min: float,
        z_max: float,
        nx: int,
        ny: int,
        nz: int,
        x_ratio: float = 1.0,
        y_ratio: float = 1.0,
        z_ratio: float = 1.0,
    ) -> GeometricStructuredRectangular3D:
        """Generate a rectangular mesh with geometric axis grading.

        Args:
            user_name (str): Unique part name.
            element (Element): Compatible volume element definition.
            region (RegionBase | None): Region; None uses the global region.
            x_min (float): Lower global x bound.
            x_max (float): Upper global x bound.
            y_min (float): Lower global y bound.
            y_max (float): Upper global y bound.
            z_min (float): Lower global z bound.
            z_max (float): Upper global z bound.
            nx (int): Positive x cell subdivision count.
            ny (int): Positive y cell subdivision count.
            nz (int): Positive z cell subdivision count.
            x_ratio (float): Adjacent x cell-width grading ratio; 1 is uniform.
            y_ratio (float): Adjacent y cell-width grading ratio.
            z_ratio (float): Adjacent z cell-width grading ratio.

        Returns:
            part (MeshPart): Generated, registered graded volume part.
        """
        from femora.components.mesh.volume_meshparts import GeometricStructuredRectangular3D

        component = GeometricStructuredRectangular3D(
            user_name,
            element,
            region,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            z_min=z_min,
            z_max=z_max,
            nx=nx,
            ny=ny,
            nz=nz,
            x_ratio=x_ratio,
            y_ratio=y_ratio,
            z_ratio=z_ratio,
        )
        self._manager.add(component)
        return component




class SurfaceMeshNamespace(_MeshPartNamespace):
    """Surface-mesh factories accessed through ``model.meshpart.surface``.

    These return registered parts, not standalone solver domains. Use a
    compatible surface element definition and assemble the part separately.
    """

    __doc_controls__ = {"summary": True, "members": ["circular_o_grid"]}

    def circular_o_grid(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        R: float,
        r0_ratio: float = 0.4,
        nt: int = 24,
        nr: int = 12,
        merge_tolerance: float = 1e-12,
    ) -> CircularOGrid2D:
        """Generate a circular quadrilateral surface O-grid and register it.

        Args:
            user_name (str): Unique part name.
            element (Element): Compatible surface element definition.
            region (RegionBase | None): Region; None uses the global region.
            R (float): Outer radius in model length units.
            r0_ratio (float): Inner core ratio of the O-grid construction.
            nt (int): Circumferential discretization parameter.
            nr (int): Radial discretization parameter.
            merge_tolerance (float): Coincident-point merging tolerance.

        Returns:
            part (MeshPart): Registered CircularOGrid2D. This is a surface mesh,
                not an extruded volume; concrete topology validation applies.
        """
        from femora.components.mesh.surface_meshparts import CircularOGrid2D

        component = CircularOGrid2D(
            user_name,
            element,
            region,
            R=R,
            r0_ratio=r0_ratio,
            nt=nt,
            nr=nr,
            merge_tolerance=merge_tolerance,
        )
        self._manager.add(component)
        return component


class GeneralMeshNamespace(_MeshPartNamespace):
    """Import or wrap meshes through ``model.meshpart.general``.

    External meshes use a supplied element definition; composite meshes can
    preserve heterogeneous cell metadata. Inspect those arrays and dependency
    tags before assembly, rather than assuming imported data is solver-ready.
    """

    __doc_controls__ = {"summary": True, "members": ["external_mesh", "composite"]}

    def external_mesh(
        self,
        user_name: str,
        element: Element,
        region: Optional[RegionBase] = None,
        *,
        mesh: DataSet | None = None,
        filepath: str | None = None,
        scale: float | None = None,
        rotate_x: float | None = None,
        rotate_y: float | None = None,
        rotate_z: float | None = None,
        translate_x: float = 0.0,
        translate_y: float = 0.0,
        translate_z: float = 0.0,
    ) -> ExternalMesh:
        """Import a mesh object/file, apply requested geometry edits, and register it.

        Args:
            user_name (str): Unique part name.
            element (Element): Element definition for the imported cells.
            region (RegionBase | None): Region; None uses the global region.
            mesh (pyvista.DataSet | None): In-memory mesh input.
            filepath (str | None): File input supported by the concrete importer.
            scale (float | None): Optional geometry scale.
            rotate_x (float | None): Rotation about global x in degrees.
            rotate_y (float | None): Rotation about global y in degrees.
            rotate_z (float | None): Rotation about global z in degrees.
            translate_x (float): Global x translation in model length units.
            translate_y (float): Global y translation.
            translate_z (float): Global z translation.

        Returns:
            part (MeshPart): Registered ExternalMesh. Input precedence, accepted
                cell types, and operation ordering follow the concrete importer.
                File-reading and constructor errors propagate.
        """
        from femora.components.mesh.general_meshparts import ExternalMesh

        component = ExternalMesh(
            user_name,
            element,
            region,
            mesh=mesh,
            filepath=filepath,
            scale=scale,
            rotate_x=rotate_x,
            rotate_y=rotate_y,
            rotate_z=rotate_z,
            translate_x=translate_x,
            translate_y=translate_y,
            translate_z=translate_z,
        )
        self._manager.add(component)
        return component

    def composite(
        self,
        user_name: str,
        mesh: DataSet,
        region: Optional[RegionBase] = None,
        *,
        ndof: int = 6,
        element_tag: int = 0,
        material_tag: int = 0,
        section_tag: int = 0,
    ) -> CompositeMesh:
        """Wrap heterogeneous cell metadata in a registered composite mesh part.

        Args:
            user_name (str): Unique part name.
            mesh (pyvista.DataSet): Input geometry and cell/point arrays.
            region (RegionBase | None): Region; None uses the global region.
            ndof (int): Fallback nodal DOF count.
            element_tag (int): Fallback element-definition tag.
            material_tag (int): Fallback material-definition tag.
            section_tag (int): Fallback section-definition tag.

        Returns:
            part (MeshPart): Registered CompositeMesh. Fallback tags are metadata,
                not newly registered material/element/section definitions.
                See the concrete component for preserved versus filled arrays.
        """
        from femora.components.mesh.general_meshparts import CompositeMesh

        component = CompositeMesh(
            user_name,
            mesh,
            region,
            ndof=ndof,
            element_tag=element_tag,
            material_tag=material_tag,
            section_tag=section_tag,
        )
        self._manager.add(component)
        return component


class MeshPartManager:
    """Create and retrieve discretized components through ``model.meshpart``.

    A mesh part combines geometry with an element definition and a region.
    Factories construct the mesh and register the returned part by its unique
    ``user_name``. If the part has no region, registration assigns the model's
    global region. Registry tags identify parts, not individual solver cells.

    Attributes:
        line (LineMeshNamespace): Single-line and structured-line factories.
        volume (VolumeMeshNamespace): Rectangular and radial volume meshes.
        surface (SurfaceMeshNamespace): Surface mesh factories.
        general (GeneralMeshNamespace): External and composite meshes.

    Example:
        ```python
        from femora import Model

        model = Model()
        soil = model.material.nd.elastic_isotropic(user_name="soil", E=1e5, nu=0.3, rho=1.8)
        brick = model.element.brick.std(ndof=3, material=soil)
        part = model.meshpart.volume.uniform_rectangular_grid(
            user_name="soil_block", element=brick,
            x_min=0, x_max=4, y_min=0, y_max=4, z_min=-4, z_max=0,
            nx=2, ny=2, nz=2,
        )
        assert model.meshpart.get("soil_block") is part
        assert model.meshpart.get_by_tag(part.tag) is part
        ```

    Warning:
        Assembly sections contain copied mesh data. Editing or removing a source
        part does not automatically refresh existing sections or the final mesh.
        Rebuild the affected assembly sections and assemble again.
    """

    __doc_controls__ = {
        "summary": True,
        "show_docstring_attributes": True,
        "members": [
            "add",
            "get",
            "get_by_tag",
            "resolve",
            "get_all",
            "get_by_category",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing = getattr(mesh_maker, "meshpart", None)
        if isinstance(existing, MeshPartManager):
            raise ValueError("mesh_maker already owns a meshpart manager")

        self._mesh_maker = mesh_maker
        mesh_maker.meshpart = self
        self._meshparts: Dict[str, MeshPart] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[MeshPart]()
        self.line = LineMeshNamespace(self)
        self.volume = VolumeMeshNamespace(self)
        self.surface = SurfaceMeshNamespace(self)
        self.general = GeneralMeshNamespace(self)

    def add(self, meshpart: MeshPart) -> MeshPart:
        """Register a mesh part and assign a model-local part tag.

        Args:
            meshpart (MeshPart): Unmanaged part or one already registered here.

        Returns:
            part (MeshPart): Original object. A missing region is replaced by
                the model's global region; this method does not regenerate geometry.

        Raises:
            TypeError: The input is not a MeshPart.
            ValueError: Name/tag conflicts or the part belongs to another manager.
        """
        if not isinstance(meshpart, MeshPart):
            raise TypeError("meshpart must be a MeshPart instance")
        if (
            meshpart.user_name in self._meshparts
            and self._meshparts[meshpart.user_name] is not meshpart
        ):
            raise ValueError(f"Mesh part name '{meshpart.user_name}' is already in use")
        if meshpart.region is None:
            meshpart.region = self._mesh_maker.region.global_region
        if meshpart._owner is None:
            meshpart._owner = self
        elif meshpart._owner is not self:
            raise ValueError("meshpart already belongs to another manager")
        by_tag = {p.tag: p for p in self._meshparts.values() if p.tag is not None}
        try:
            meshpart.tag = self._tagging.assign_tag(by_tag, meshpart, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"MeshPart tag {meshpart.tag} already exists") from exc
        self._meshparts[meshpart.user_name] = meshpart
        return meshpart

    def get(self, user_name: str) -> Optional[MeshPart]:
        """Return a part by exact user name, or None when absent.

        Args:
            user_name (str): Case-sensitive registry key, not a filename or tag.
        """
        return self._meshparts.get(user_name)

    def get_by_tag(self, tag: int) -> Optional[MeshPart]:
        """Find a part by its current integer-convertible registry tag.

        Args:
            tag (int): Part tag, not a node/cell tag. Conversion errors propagate
                when a populated registry is searched.

        Returns:
            part (MeshPart | None): Matching object, or None when absent.
        """
        for part in self._meshparts.values():
            if part.tag == int(tag):
                return part
        return None

    def resolve(self, item: Union[str, int, MeshPart]) -> Optional[MeshPart]:
        """Resolve an object, name, or integer part tag.

        Args:
            item (str | int | MeshPart): Strings are names; integers are tags.

        Returns:
            part (MeshPart | None): Object unchanged, lookup result, or None for
                unsupported/missing values. Direct objects are not registered
                or checked for ownership by this helper.
        """
        if isinstance(item, MeshPart):
            return item
        if isinstance(item, str):
            return self.get(item)
        if isinstance(item, int):
            return self.get_by_tag(item)
        return None

    def get_all(self) -> Dict[str, MeshPart]:
        """Return a shallow dictionary snapshot keyed by user name.

        Part objects and their mesh arrays remain shared. Editing dictionary
        membership does not edit the manager's registry.
        """
        return dict(self._meshparts)

    def get_by_category(self, category: str) -> Dict[str, MeshPart]:
        """Return a shallow name-to-part mapping for a case-insensitive category.

        Args:
            category (str): Category stored on parts, such as a mesh family's
                category. Matching is exact after lowercasing, not substring-based.
        """
        key = category.lower()
        return {
            name: part for name, part in self._meshparts.items() if part.category.lower() == key
        }

    def remove(self, user_name: str) -> None:
        """Detach a named part and compact remaining registry tags.

        Args:
            user_name (str): Exact part name; missing names are ignored.

        Existing assembly sections, dependent interfaces, and exported files are
        not removed or refreshed. Cached part tags may become stale.
        """
        part = self._meshparts.pop(user_name, None)
        if part is not None:
            part.tag = None
            part._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach every part and clear its tag, without clearing other managers.

        Assembly sections can still hold old part references and mesh copies.
        Use ``model.clear_model()`` for a coordinated whole-model reset.
        """
        for part in list(self._meshparts.values()):
            part.tag = None
            part._owner = None
        self._meshparts.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive part-tag origin and retag registered parts.

        Args:
            start_tag (int): First part registry tag validated by the tagging policy.

        Raises:
            ValueError: The origin is invalid. This setting does not change the
                exported solver node/element tag origins or update old mesh copies.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        by_tag = {p.tag: p for p in self._meshparts.values() if p.tag is not None}
        self._tagging.reassign_tags(by_tag, self._start_tag)


__all__ = ["MeshPartManager"]
