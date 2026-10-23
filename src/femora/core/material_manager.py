# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, Optional

from femora.core.nd_material_manager import NDMaterialManager
from femora.core.uniaxial_material_manager import UniaxialMaterialManager
from femora.core.material_base import Material
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model


class MaterialManager:
    """Local manager for ``Material`` lifecycle and tag assignment.

    The manager is intentionally not a singleton.  Each :class:`Model`
    instance owns one ``MaterialManager`` with an independent tag space.

    Args:
        mesh_maker: The :class:`Model` that owns this manager.

    Raises:
        TypeError: If *mesh_maker* is not a :class:`Model` instance.

    Attributes:
        nd (NDMaterialManager): Factories available through ``model.material.nd``.
        uniaxial (UniaxialMaterialManager): Factories through
            ``model.material.uniaxial``. Both namespaces share this registry.

    Example:
        ```python
        from femora import Model

        model = Model()
        steel = model.material.uniaxial.elastic(user_name="steel", E=200e6)
        assert model.material.get(steel.tag) is steel
        assert model.material.get_by_name("steel") is steel
        ```

    Warning:
        Removal and start-tag changes can retag surviving objects. Do not
        treat a cached integer tag as a persistent identifier across edits.
        Use object references or unique names while constructing the model.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "add",
            "get",
            "get_by_name",
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
        self._materials: Dict[int, Material] = {}
        self._names: Dict[str, Material] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Material]()
        self.nd = NDMaterialManager(self)
        self.uniaxial = UniaxialMaterialManager(self)

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def add(self, material: Material) -> Material:
        """Add an existing material and assign a tag if needed.

        Args:
            material: Unmanaged or already-managed :class:`Material` instance.

        Returns:
            The same ``material`` instance after it is stored by this manager.

        Raises:
            TypeError: If *material* is not a :class:`Material` instance.
            ValueError: If its preassigned tag conflicts with a different object
                already managed here, or if it already belongs to another manager.
        """
        if not isinstance(material, Material):
            raise TypeError("material must be a Material instance")
        if material._owner is None:
            material._owner = self
        elif material._owner is not self:
            raise ValueError("material already belongs to another manager")
        existing_by_name = self._names.get(material.user_name)
        if existing_by_name is not None and existing_by_name is not material:
            raise ValueError(f"Material user_name '{material.user_name}' already exists")

        try:
            material.tag = self._tagging.assign_tag(self._materials, material, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Material tag {material.tag} already exists") from exc

        self._materials[material.tag] = material
        self._names[material.user_name] = material
        return material

    def get(self, tag: int) -> Optional[Material]:
        """Look up a material by its current manager-assigned tag.

        Args:
            tag (int): Tag, converted with ``int(tag)`` before lookup.

        Returns:
            Material | None: Registered object, or None if the tag is absent.

        Raises:
            TypeError: The supplied value cannot be converted to an integer.
            ValueError: Integer conversion fails for the supplied value.
        """
        return self._materials.get(int(tag))

    def get_by_name(self, name: str) -> Optional[Material]:
        """Look up a registered material by its exact user name.

        Args:
            name (str): Case-sensitive registered ``user_name``.

        Returns:
            Material | None: Matching object or None. No material is created.
        """
        return self._names.get(name)

    def get_all(self) -> Dict[int, Material]:
        """Return a shallow registry snapshot keyed by current integer tag.

        Returns:
            dict[int, Material]: New dictionary containing the original objects.
            Editing its keys does not edit the manager; changing an object does.
        """
        return dict(self._materials)

    def remove(self, tag: int) -> None:
        """Remove a managed material and compact the remaining tags.

        Args:
            tag: Tag of the material to remove.  Missing tags are ignored.
        """
        material = self._materials.pop(int(tag), None)
        if material is not None:
            self._names.pop(material.user_name, None)
            material.tag = None
            material._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach every material, clear its tag, and empty both lookup indices.

        This does not remove elements or sections referring to those objects,
        clear the whole Model, or execute an OpenSees command. Detached objects
        must be registered again before rendering tag-dependent definitions.
        """
        for material in list(self._materials.values()):
            material.tag = None
            material._owner = None
        self._materials.clear()
        self._names.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the first tag used by this manager and retag existing objects.

        Args:
            start_tag: Positive integer for the first assigned tag.

        Raises:
            ValueError: If *start_tag* is less than ``1``.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._materials)

    def __iter__(self) -> Iterator[Material]:
        return iter(self._materials.values())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _next_available_tag(self) -> int:
        return self._tagging.next_available_tag(self._materials, self._start_tag)

    def _reassign_tags(self) -> None:
        """Rebuild *_materials* and *_names* after a removal or start-tag change."""
        # Retag objects (updates obj.tag in place and rebuilds _materials dict)
        self._tagging.reassign_tags(self._materials, self._start_tag)
        # Rebuild name index to stay consistent
        self._names = {mat.user_name: mat for mat in self._materials.values()}


__all__ = ["MaterialManager"]
