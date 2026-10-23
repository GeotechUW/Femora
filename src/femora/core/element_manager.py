# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, Optional, List, Union

from femora.core.element_base import Element
from femora.core.beam_element_manager import BeamElementManager
from femora.core.brick_element_manager import BrickElementManager
from femora.core.quad_element_manager import QuadElementManager
from femora.core.special_element_manager import SpecialElementManager
from femora.core.tagging import CompactRetagPolicy
from femora.core.material_base import Material
from femora.core.section_base import Section
from femora.core.transformation_base import GeometricTransformation

if TYPE_CHECKING:
    from femora.core.model import Model


class ElementManager:
    """Create and register element definitions through ``model.element``.

    A definition stores formulation, degrees of freedom, dependencies, and
    options. A mesh part uses it for its cells; it is not an individual solver
    element with node connectivity. The definition's registry tag is distinct
    from the assembled cell tags written to OpenSees.

    Attributes:
        beam (BeamElementManager): Beam-column and truss factories.
        brick (BrickElementManager): Three-dimensional continuum factories.
        quad (QuadElementManager): Quadrilateral continuum factories.
        special (SpecialElementManager): Auxiliary and contact element factories.

    Example:
        ```python
        from femora import Model

        model = Model()
        soil = model.material.nd.elastic_isotropic(user_name="soil", E=1e5, nu=0.3, rho=1.8)
        brick = model.element.brick.std(ndof=3, material=soil)
        assert model.element.get(brick.tag) is brick
        assert brick.get_material() is soil
        ```

    Note:
        Prefer managed dependency objects from the same Model. Material string
        references are converted to integer tags, not looked up by user name.
        Transformation names are explicitly unsupported. Removal and retagging
        do not repair dependent mesh parts or an already assembled mesh.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._elements: Dict[int, Element] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Element]()

        # Initialize namespaces
        self.beam = BeamElementManager(self)
        self.brick = BrickElementManager(self)
        self.quad = QuadElementManager(self)
        self.special = SpecialElementManager(self)

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def add(self, element: Element) -> Element:
        """Register a definition, assign its tag, and retain it in this model.

        Args:
            element (Element): Unmanaged definition, or one already owned here.

        Returns:
            element (Element): The same object, with a registry tag.

        Raises:
            TypeError: The object is not an Element.
            ValueError: Another manager owns it or its tag conflicts.
        """
        if not isinstance(element, Element):
            raise TypeError("element must be an Element instance")
        if element._owner is None:
            element._owner = self
        elif element._owner is not self:
            raise ValueError("element already belongs to another manager")

        try:
            element.tag = self._tagging.assign_tag(self._elements, element, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Element tag {element.tag} already exists") from exc

        self._elements[element.tag] = element
        return element

    def get(self, tag: int) -> Optional[Element]:
        """Return a definition by its current registry tag, or None if absent.

        Args:
            tag (int): Value converted through ``int(tag)``; conversion errors
                propagate. This is not an assembled solver cell tag.
        """
        return self._elements.get(int(tag))

    def get_all(self) -> Dict[int, Element]:
        """Return a shallow registry copy keyed by current definition tag.

        Object values are shared with the model; editing the returned dictionary
        does not add or remove registrations.
        """
        return dict(self._elements)

    def remove(self, tag: int) -> None:
        """Detach one definition and compact the tags of surviving definitions.

        Args:
            tag (int): Current registry tag; missing tags are ignored.

        Warning:
            Held integer tags can become stale. Dependent meshes are not
            removed and solver cells are not individually deleted by this call.
        """
        element = self._elements.pop(int(tag), None)
        if element is not None:
            element.tag = None
            element._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach all definitions and clear their tags without deleting meshes.

        Materials, sections, transformations, and output files are not cleared.
        Rebuild dependent model data before exporting after a registry reset.
        """
        for element in list(self._elements.values()):
            element.tag = None
            element._owner = None
        self._elements.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive registry tag origin and retag existing definitions.

        Args:
            start_tag (int): First definition tag, validated by the tagging policy.

        Raises:
            ValueError: The tag origin is invalid. This setting is unrelated to
                ``model.set_eletag_start()`` for exported solver cells.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def __len__(self) -> int:
        return len(self._elements)

    def __iter__(self) -> Iterator[Element]:
        return iter(self._elements.values())

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._elements, self._start_tag)

    def _resolve_materials(self, material):
        if material is None:
            return None

        if isinstance(material, list):
            resolved_materials = []
            for i, mat in enumerate(material):
                if isinstance(mat, (str, int)):
                    resolved_mat = self._mesh_maker.material.get(mat)
                    if resolved_mat is None:
                        raise ValueError(f"Material {mat} at index {i} not found")
                    resolved_materials.append(resolved_mat)
                elif isinstance(mat, Material):
                    resolved_materials.append(mat)
                else:
                    raise ValueError(f"Invalid material type at index {i}: {type(mat)}")
            return resolved_materials

        elif isinstance(material, (str, int)):
            resolved_material = self._mesh_maker.material.get(material)
            if resolved_material is None:
                raise ValueError(f"Material '{material}' not found")
            return resolved_material

        elif isinstance(material, Material):
            return material
        raise ValueError(f"Invalid material type: {type(material)}")

    def _resolve_section(self, section):
        if section is None:
            return None
        if isinstance(section, (str, int)):
            resolved_section = self._mesh_maker.section.get(section)
            if resolved_section is None:
                raise ValueError(f"Section '{section}' not found")
            return resolved_section
        elif isinstance(section, Section):
            return section
        raise ValueError(f"Invalid section type: {type(section)}")

    def _resolve_transformation(self, transformation):
        if transformation is None:
            return None
        if isinstance(transformation, str):
            raise ValueError("Transformation lookup by name not supported; pass managed object")
        if isinstance(transformation, int):
            resolved_transformation = self._mesh_maker.transformation.get(transformation)
            if resolved_transformation is None:
                raise ValueError(f"Transformation '{transformation}' not found")
            return resolved_transformation
        elif isinstance(transformation, GeometricTransformation):
            if transformation.tag is None:
                raise ValueError("Transformation must be managed")
            return transformation
        raise ValueError(f"Invalid transformation type: {type(transformation)}")
