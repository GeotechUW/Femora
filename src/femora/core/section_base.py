# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from femora.core.material_base import Material


_UNMANAGED_MATERIAL_MSG = (
    "Cannot resolve material by tag or name on an unmanaged section. "
    "Pass a managed Material object directly, or create the section through "
    "model.section / SectionManager."
)

_UNMANAGED_SECTION_MSG = (
    "Cannot resolve section by tag or name on an unmanaged section. "
    "Pass a managed Section object directly, or create the section through "
    "model.section / SectionManager."
)


class Section(ABC):
    """Abstract base class for all sections with manager-owned tagging.

    Section objects do not self-register and do not assign their own tags.
    A :class:`~femora.core.section_manager.SectionManager` owns lifecycle
    operations, tag assignment, removal, and retagging for a local model context.

    Args:
        section_type: The type of section (e.g., 'section').
        section_name: The specific section name for OpenSees (e.g., 'Elastic').
        user_name: User-specified name for the section.

    Attributes:
        tag: Manager-assigned OpenSees tag. It remains ``None`` until the
            instance is added to a :class:`~femora.core.section_manager.SectionManager`.
        _owner: Reference to the owning manager, or ``None`` when unmanaged.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "to_tcl",
            "resolve_material",
            "resolve_materials_dict",
            "resolve_section",
            "resolve_material_reference",
            "get_materials",
            "has_material",
            "get_area",
            "get_Iy",
            "get_Iz",
            "get_J",
        ],
    }

    def __init__(self, section_type: str, section_name: str, user_name: str) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[Any] = None  # Should be SectionManager
        self.section_type = section_type
        self.section_name = section_name
        self.user_name = user_name

        # Base class material placeholder
        self.material: Optional[Material] = None

    def _require_tag(self) -> int:
        """Return the assigned tag or fail if the instance is unmanaged.

        Returns:
            The manager-assigned integer tag.

        Raises:
            ValueError: If this section has not been added to a manager.
        """
        if self.tag is None:
            raise ValueError(f"Section '{self.user_name}' must be managed before rendering TCL")
        return self.tag

    @abstractmethod
    def to_tcl(self) -> str:
        """Convert the section to a TCL string representation for OpenSees.

        Returns:
            TCL command string for this section.
        """
        raise NotImplementedError

    def resolve_material(
        self, material_input: Union[int, str, "Material", None]
    ) -> Optional["Material"]:
        """Resolve a material object, tag, or name in this section's context.

        Args:
            material_input (int | str | Material | None): Material reference.
                Objects pass through unchanged and None remains None.

        Returns:
            material (Material | None): Resolved dependency without copying.

        Raises:
            ValueError: A name/tag cannot be resolved, or no owner is available
                to perform the lookup. Direct objects do not require an owner.
        """
        if material_input is None:
            return None

        from femora.core.material_base import Material as MaterialClass

        if isinstance(material_input, MaterialClass):
            return material_input

        if self._owner is not None and hasattr(self._owner, "resolve_material"):
            resolved = self._owner.resolve_material(material_input)
            if resolved is None:
                raise ValueError(f"Material not found: {material_input}")
            return resolved

        raise ValueError(_UNMANAGED_MATERIAL_MSG)

    def resolve_materials_dict(
        self, materials_input: Dict[str, Union[int, str, "Material"]]
    ) -> Dict[str, "Material"]:
        """Resolve each value of a dependency mapping, preserving its keys.

        Args:
            materials_input (dict[str, int | str | Material]): Named references
                interpreted by ``resolve_material``.

        Returns:
            materials (dict[str, Material]): New mapping containing resolved
                objects. Lookup failures propagate; input is not mutated.
        """
        return {key: self.resolve_material(value) for key, value in materials_input.items()}

    def resolve_section(
        self, section_input: Union[int, str, "Section", None]
    ) -> Optional["Section"]:
        """Resolve a section object, integer tag, or user name.

        Args:
            section_input (int | str | Section | None): Dependency reference.

        Returns:
            section (Section | None): Direct object, looked-up section, or None
                for None input. Existing objects are neither copied nor registered.

        Raises:
            ValueError: Lookup fails or an unmanaged section is asked to resolve
                a name/tag without an owning manager.
        """
        if section_input is None:
            return None
        if isinstance(section_input, Section):
            return section_input
        if self._owner is not None and hasattr(self._owner, "get"):
            resolved = self._owner.get(section_input)
            if resolved is None:
                raise ValueError(f"Section not found: {section_input}")
            return resolved

        raise ValueError(_UNMANAGED_SECTION_MSG)

    @staticmethod
    def resolve_material_reference(
        material_input: Union[int, str, "Material", None],
    ) -> Optional["Material"]:
        """Accept a direct material object without a manager lookup.

        Args:
            material_input (int | str | Material | None): Only Material objects
                and None can be resolved by this context-free helper.

        Returns:
            material (Material | None): Original object, or None.

        Raises:
            ValueError: A name, tag, or other unsupported value is supplied.
        """
        if material_input is None:
            return None

        from femora.core.material_base import Material as MaterialClass

        if isinstance(material_input, MaterialClass):
            return material_input

        raise ValueError(_UNMANAGED_MATERIAL_MSG)

    def get_materials(self) -> List["Material"]:
        """Return this base section's direct material dependency as a new list.

        The base returns ``[self.material]`` or an empty list. Composite/fiber
        implementations override this hook to report their own dependencies.
        Material objects are shared, not copied.
        """
        if self.material is not None:
            return [self.material]
        return []

    def has_material(self) -> bool:
        """Report whether the base ``material`` attribute is non-None.

        Concrete section families may override this hook. The base does not
        search arbitrary nested sections or fiber collections.
        """
        return self.material is not None

    def get_area(self) -> float:
        """Return section area in squared model length units.

        The base returns 0.0 as a fallback, not an integrated geometric result.
        Implementations with area information must override the hook.
        """
        return 0.0

    def get_Iy(self) -> float:
        """Return the local-y second moment in length-to-the-fourth units.

        The base returns 0.0. A concrete section must override this method when
        a consuming element requires its bending property.
        """
        return 0.0

    def get_Iz(self) -> float:
        """Return the local-z second moment in length-to-the-fourth units.

        The base returns 0.0 rather than deriving geometry from materials or
        discretized fibers. Concrete implementations supply the property.
        """
        return 0.0

    def get_J(self) -> float:
        """Return the torsional constant in length-to-the-fourth units.

        The base returns 0.0. This hook is not an automatic polar-inertia or
        warping calculation; concrete section implementations determine it.
        """
        return 0.0

    def __str__(self) -> str:
        tag = self.tag if self.tag is not None else "unmanaged"
        material_info = (
            f", Material: {self.material.user_name}" if self.material else ", No Material"
        )
        return (
            f"Section '{self.user_name}' (Tag: {tag}, Type: {self.section_name}" f"{material_info})"
        )
