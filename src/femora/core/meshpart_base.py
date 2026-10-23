# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np
from numpy.typing import ArrayLike
import pyvista as pv

from femora.components.geometry_ops import MeshPartTransform
from femora.constants import FEMORA_MAX_NDF
from femora.core.damping_base import Damping
from femora.core.element_base import Element
from femora.core.material_base import Material
from femora.core.region_base import RegionBase


class MeshPart(ABC):
    """Extension contract for a discretized component owned by one Model.

    Instances do not self-register. A :class:`MeshPartManager` owns tag
    assignment and lifecycle.

    Concrete subclasses generate ``mesh`` and define compatible element types.
    Ordinary scripts create parts through ``model.meshpart``. Source-part edits
    must precede section creation, or affected sections must be rebuilt.

    Attributes:
        user_name (str): Registry name used by assembly section definitions.
        element (Element | None): Shared reusable element definition.
        region (RegionBase | None): Region associated with this part.
        mesh (pyvista.DataSet | None): Generated geometry and per-point/cell data.
        transform (MeshPartTransform): Geometry transformation helper.
        tag (int | None): Part registry tag, not an individual solver cell tag.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "generate_mesh",
            "is_elemnt_compatible",
            "remove_cells",
            "plot",
            "set_damping",
        ],
    }

    _compatible_elements: list = []

    def __init__(
        self,
        category: str,
        mesh_type: str,
        user_name: str,
        element: Optional[Element],
        region: Optional[RegionBase] = None,
    ) -> None:
        self.category = category
        self.mesh_type = mesh_type
        self.user_name = user_name
        self.element = element
        self.region = region
        self.mesh: Optional[pv.DataSet] = None
        self.actor = None
        self.transform = MeshPartTransform(self)
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None

    @abstractmethod
    def generate_mesh(self) -> None:
        """Generate this part's geometry and metadata in a concrete subclass.

        Implementations populate ``mesh`` in place and may replace previous
        geometry/data. This abstract contract does not specify a returned mesh.
        Regeneration does not automatically rebuild existing assembly sections.
        """
        pass

    @classmethod
    def is_elemnt_compatible(cls, element: str) -> bool:
        """Test an element-type name against this mesh family's compatibility list.

        Args:
            element (str): Element-type name, compared case-insensitively.

        Returns:
            compatible (bool): Whether the name occurs in the class list. This
                does not validate a material, DOF layout, or cell geometry.

        Note:
            The public method retains the historical spelling ``elemnt``.
        """
        return element.lower() in [e.lower() for e in cls._compatible_elements]

    def assign_material(self, material: Material) -> None:
        """Attempt to replace the material on the shared element definition.

        This legacy helper depends on an element-specific ``material`` attribute
        not supplied by the common Element base. Prefer creating a compatible
        element definition through ``model.element``. The helper is excluded
        from the ordinary mesh-part reference pending a consistent contract.
        """
        if self.element is None:
            raise ValueError("No element to assign material to")
        if self.element.material is not None:
            self.element.assign_material(material)
        else:
            raise ValueError("No material to assign to the element")

    def assign_actor(self, actor: Any) -> None:
        """Store a visualization actor reference without modifying geometry.

        Args:
            actor (Any): Actor managed by a visualization client. This assignment
                neither creates a plotter nor opens a rendering window.
        """
        self.actor = actor

    def remove_cells(self, selection: ArrayLike) -> None:
        """Remove whole cells in place, before creating assembly sections.

        Args:
            selection (ArrayLike): One-dimensional Boolean mask with one entry per current
                cell, or integer cell indices. True entries are removed.

        Remaining cell/point data are preserved and unused points are discarded.
        Coordinates, masses, and connectivity are not interpolated. Other mesh
        parts are untouched. An empty integer selection is a no-op; removing
        every cell leaves an empty mesh. Regenerating the mesh resets this edit.

        Raises:
            ValueError: No mesh exists, indices are invalid, or this part has
                already been copied into an assembly section. Create a new part
                or remove/rebuild its sections before editing it.

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
            centers = part.mesh.cell_centers().points
            inside = (abs(centers[:, 0]) < 16) & (centers[:, 2] > -4)
            part.remove_cells(inside)
            ```
        """
        if self.mesh is None:
            raise ValueError("Mesh not generated yet")
        if self._owner is not None:
            assembler = self._owner._mesh_maker.assembler
            if any(self in section.meshparts_list for section in assembler.get_all().values()):
                raise ValueError(
                    "Remove assembly sections containing this mesh part before removing cells"
                )
        selected = np.asarray(selection)
        if selected.ndim != 1:
            raise ValueError("selection must be a one-dimensional mask or integer indices")
        keep = np.ones(self.mesh.n_cells, dtype=bool)
        if np.issubdtype(selected.dtype, np.bool_):
            if selected.size != self.mesh.n_cells:
                raise ValueError("Boolean mask length must equal the current number of cells")
            keep &= ~selected
        elif selected.size == 0:
            return
        elif np.issubdtype(selected.dtype, np.integer):
            if np.any(selected < 0) or np.any(selected >= self.mesh.n_cells):
                raise ValueError("Cell index out of range")
            keep[selected] = False
        else:
            raise ValueError("selection must contain Boolean values or integer cell indices")
        if not keep.all():
            self.mesh = self.mesh.extract_cells(keep)

    def _ensure_mass_array(self) -> None:
        if self.mesh is None:
            return
        if "Mass" not in self.mesh.point_data:
            n_pts = self.mesh.n_points
            self.mesh.point_data["Mass"] = np.zeros((n_pts, FEMORA_MAX_NDF), dtype=np.float32)

    def plot(
        self, off_screen: bool = False, screenshot: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Display this part's mesh using a new PyVista plotter.

        Args:
            off_screen (bool): Request off-screen rendering from PyVista.
            screenshot (str | None): Optional screenshot output passed to ``show``.
            **kwargs (Any): Display options forwarded to ``Plotter.add_mesh``.

        Raises:
            ValueError: No generated mesh exists. Rendering/backend errors propagate.

        Note:
            Creates a zero-filled Mass point-data array when absent. Off-screen
            rendering still requires a compatible VTK graphics environment.
        """
        if self.mesh is None:
            raise ValueError("Mesh not generated yet. Call generate_mesh() first.")
        self._ensure_mass_array()
        plotter = pv.Plotter(off_screen=off_screen)
        plotter.add_mesh(self.mesh, **kwargs)
        plotter.show(screenshot=screenshot)

    def set_damping(self, damping_instance: Damping) -> None:
        """Assign damping through this part's existing region.

        Args:
            damping_instance (Damping): Damping definition accepted by the region.

        Raises:
            ValueError: No region is assigned. Region validation errors propagate.

        Note:
            Other parts sharing the region also observe the change. This does
            not create an isolated region or patch an already exported script.
        """
        if self.region is None:
            raise ValueError("No region available to assign damping to.")
        self.region.set_damping(damping_instance)


__all__ = ["MeshPart"]
