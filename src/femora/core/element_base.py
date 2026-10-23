# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Union, Any, TYPE_CHECKING
from femora.core.material_base import Material
from femora.core.section_base import Section
from femora.core.transformation_base import GeometricTransformation

if TYPE_CHECKING:
    from femora.core.element_manager import ElementManager


class Element(ABC):
    """Base abstract class for manager-owned OpenSees finite elements.

    Element instances do not self-register and do not assign their own tags.
    An `ElementManager` owns lifecycle operations, tag assignment, removal,
    and retagging for a local model context.

    Attributes:
        tag: Manager-assigned OpenSees element tag. Remains None until
            this object is added to an ElementManager.
        _owner: Reference to the owning manager, or None when unmanaged.
        element_type: The type of element (e.g., 'quad', 'truss', 'beam').
        _ndof: Number of degrees of freedom for the element.
        element_params: Dictionary of element-specific parameters.
        _material: Primary material assigned to this element.
        _materials: List of all materials assigned to this element.
        _section: Section assigned to this element (for section-based elements).
        _transformation: Geometric transformation assigned to this element (for beam elements).
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "assign_material",
            "assign_section",
            "assign_transformation",
            "assign_ndof",
            "get_material",
            "get_materials",
            "get_section",
            "get_transformation",
            "get_element_params",
            "update_element_params",
            "get_ndof",
            "to_tcl",
            "get_section_tag",
            "get_material_tag",
            "get_mass_per_length",
            "get_density",
        ],
    }

    def __init__(
        self,
        element_type: str,
        ndof: int,
        material: Union[Material, List[Material], None] = None,
        section: Section = None,
        transformation: GeometricTransformation = None,
        **element_params,
    ) -> None:
        """Initializes the Element with flexible dependency support."""
        self.tag: Optional[int] = None
        self._owner: object | None = None

        self.element_type = element_type
        self._ndof = ndof
        self.element_params = element_params

        # Store dependencies without validation (child classes handle validation)
        self._material = material
        self._section = section
        self._transformation = transformation

        # Handle multiple materials for list case
        if isinstance(material, list):
            self._materials = material
            self._material = material[0] if material else None  # Primary material
        else:
            self._materials = [material] if material else []

    def _require_tag(self) -> int:
        """Return the assigned tag, or raise if this element is unmanaged."""
        if self.tag is None:
            raise ValueError(
                f"Element of type '{self.element_type}' must be added to an ElementManager "
                "before rendering TCL."
            )
        return self.tag

    def assign_material(self, material: Union[Material, List[Material]]) -> None:
        """Replace this definition's material references without registration.

        Args:
            material (Material | list[Material]): Primary material or ordered
                material list. An empty list clears the primary reference.

        Note:
            The base setter does not validate compatibility or register materials.
            Changes affect the shared definition, not just one assembled cell.
        """
        if isinstance(material, list):
            self._materials = material
            self._material = material[0] if material else None
        else:
            self._material = material
            self._materials = [material] if material else []

    def assign_section(self, section: Section) -> None:
        """Replace the section reference without compatibility validation.

        Args:
            section (Section): Section object; this setter does not resolve tags
                or add the section to a manager.
        """
        self._section = section

    def assign_transformation(self, transformation: GeometricTransformation) -> None:
        """Replace the transformation reference without registry lookup.

        Args:
            transformation (GeometricTransformation): Transformation object.
                Ensure registration and formulation compatibility before export.
        """
        self._transformation = transformation

    def assign_ndof(self, ndof: int) -> None:
        """Store a new nodal DOF count on this definition.

        Args:
            ndof (int): Requested count. The base setter does not validate it,
                rebuild a mesh, or update already assembled node metadata.
        """
        self._ndof = ndof

    def get_material(self) -> Optional[Material]:
        """Return the primary material reference, or None when absent.

        For a material list, the primary material is its first entry. No object
        is copied and no registry lookup is performed.
        """
        return self._material

    def get_materials(self) -> List[Material]:
        """Return a shallow copy of the assigned material list.

        Material objects are shared; editing list membership does not alter the
        definition, but changing an individual material affects that object.
        """
        return self._materials.copy()

    def get_section(self) -> Optional[Section]:
        """Return the assigned section object, or None if absent.

        This is the original reference, not a copy or newly resolved section.
        """
        return self._section

    def get_transformation(self) -> Optional[GeometricTransformation]:
        """Return the assigned transformation object, or None if absent.

        No copy is made. This method does not test whether it remains registered.
        """
        return self._transformation

    def get_element_params(self) -> Dict[str, Any]:
        """Return a shallow copy of the element parameter dictionary.

        Editing top-level keys does not change this definition; nested mutable
        values remain shared. Use ``update_element_params`` to replace entries.
        """
        return self.element_params.copy()

    def update_element_params(self, **new_params: Any) -> None:
        """Merge keyword entries into the element parameter dictionary.

        Args:
            **new_params (Any): Keys and replacement values. The base method
                does not validate them, rerun the constructor, or reassemble meshes.
        """
        self.element_params.update(new_params)

    def get_ndof(self) -> int:
        """Return the stored nodal degree-of-freedom count.

        This describes the reusable definition, not the total equation count
        of a model or the number of nodes in a cell.
        """
        return self._ndof

    @abstractmethod
    def to_tcl(self, tag: int, nodes: List[int]) -> str:
        """Render one solver cell using explicit connectivity.

        Args:
            tag (int): Solver element tag for the particular cell, distinct from
                the reusable definition's manager tag.
            nodes (list[int]): Ordered solver node tags required by the formulation.

        Returns:
            command (str): Tcl supplied by a concrete implementation. This
                abstract base does not implement cell rendering or execution.
        """
        pass

    def __str__(self) -> str:
        tag_str = self.tag if self.tag is not None else "unmanaged"
        return f"{self.element_type} Element (Tag: {tag_str}, DOF: {self._ndof})"

    def __repr__(self) -> str:
        tag_str = self.tag if self.tag is not None else "None"
        return (
            f"Element(type='{self.element_type}', tag={tag_str}, ndof={self._ndof}, "
            f"material={'Yes' if self._material else 'No'}, "
            f"section={'Yes' if self._section else 'No'}, "
            f"transformation={'Yes' if self._transformation else 'No'})"
        )

    def get_section_tag(self) -> Optional[int]:
        """Return the section's current tag, or zero if no section is assigned.

        An assigned but unmanaged section can return None. This helper does not
        register the section or guarantee that the tag is exportable.
        """
        return self._section.tag if self._section else 0

    def get_material_tag(self) -> Optional[int]:
        """Return the primary material's tag, or zero if there is no material.

        An assigned unmanaged material can return None. The value is a material
        definition tag, not a solver element tag.
        """
        return self._material.tag if self._material else 0

    def get_mass_per_length(self) -> float:
        """Return mass per unit length as defined by the concrete formulation.

        This base implementation returns 0.0. It does not integrate geometry or
        add nodal masses; relevant subclasses override the hook.
        """
        return 0.0

    def get_density(self) -> float:
        """Return the concrete formulation's density contribution.

        This base implementation returns 0.0 rather than deriving a density
        from its material. Concrete subclasses may supply a formulation-specific value.
        """
        return 0.0
