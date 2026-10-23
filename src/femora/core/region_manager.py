# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Union

import numpy as np

from femora.core.region_base import RegionBase
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.core.damping_base import Damping
    from femora.components.region.regions import ElementRegion, NodeRegion, GlobalRegion


class _ElementRegionFactory:
    """Callable exposed as ``model.region.element``; not constructed by users."""

    def __init__(self, manager: "RegionManager") -> None:
        self._manager = manager

    def __call__(
        self,
        user_name: str | None = None,
        damping: Damping | None = None,
        *,
        elements: list[int] | np.ndarray | None = None,
        element_range: list[int] | np.ndarray | None = None,
        element_only: bool = False,
    ) -> ElementRegion:
        """Create an ElementRegion and register it with the owning model.

        Args:
            user_name (str | None): Unique label or None for a generated name.
            damping (Damping | None): Optional damping definition retained weakly.
            elements: Explicit solver element tags.
            element_range: Inclusive start/end solver element tags.
            element_only: Restrict the region to its selected elements.

        Returns:
            region (RegionBase): Registered ElementRegion. Component/registry
                validation errors propagate; no solver command executes here.
        """
        from femora.components.region.regions import ElementRegion

        selection = {}
        if elements is not None:
            selection["elements"] = elements
        if element_range is not None:
            selection["element_range"] = element_range
        region = ElementRegion(
            user_name=user_name,
            damping=damping,
            element_only=element_only,
            **selection,
        )
        self._manager.add(region)
        return region


class _NodeRegionFactory:
    """Callable exposed as ``model.region.node``; not constructed by users."""

    def __init__(self, manager: "RegionManager") -> None:
        self._manager = manager

    def __call__(
        self,
        user_name: str | None = None,
        damping: Damping | None = None,
        *,
        nodes: list[int] | np.ndarray | None = None,
        node_range: list[int] | np.ndarray | None = None,
        node_only: bool = False,
    ) -> NodeRegion:
        """Create a NodeRegion and register it with the owning model.

        Args:
            user_name (str | None): Unique label or None for a generated name.
            damping (Damping | None): Optional damping definition retained weakly.
            nodes: Explicit solver node tags.
            node_range: Inclusive start/end solver node tags.
            node_only: Restrict the region to its selected nodes.

        Returns:
            region (RegionBase): Registered NodeRegion. Creation does not generate
                a node group or add new nodes to the model.
        """
        from femora.components.region.regions import NodeRegion

        selection = {}
        if nodes is not None:
            selection["nodes"] = nodes
        if node_range is not None:
            selection["node_range"] = node_range
        region = NodeRegion(
            user_name=user_name,
            damping=damping,
            node_only=node_only,
            **selection,
        )
        self._manager.add(region)
        return region


class RegionManager:
    """Organize region definitions through ``model.region``.

    The manager always includes a global region at tag zero. Mesh parts without
    an explicit region receive that global region on registration. Non-global
    regions have unique names and positive tags and can associate damping with
    selected model components.

    Attributes:
        element: Typed callable factory returning a registered ElementRegion.
            Select elements with ``elements`` or ``element_range``.
        node: Typed callable factory returning a registered NodeRegion.
            Select nodes with ``nodes`` or ``node_range``.

    Example:
        ```python
        from femora import Model

        model = Model()
        damping = model.damping.frequency_rayleigh(damping_factor=0.03, f1=3, f2=15)
        soil = model.region.element(user_name="soil", damping=damping)
        assert model.region.get("soil") is soil
        assert model.region.get(0) is model.region.global_region
        ```

    Warning:
        Parts sharing a region share its damping association. Removing/replacing
        regions does not repair dependent parts or refresh an assembled mesh.
    """

    __doc_controls__ = {
        "summary": True,
        "show_docstring_attributes": True,
        "members": [
            "global_region",
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
        existing_manager = getattr(mesh_maker, "region", None)
        if isinstance(existing_manager, RegionManager):
            raise ValueError("mesh_maker already owns a region manager")

        from femora.components.region.regions import ElementRegion, GlobalRegion, NodeRegion

        self._mesh_maker = mesh_maker
        self._regions: Dict[int, RegionBase] = {}
        self._names: Dict[str, RegionBase] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[RegionBase]()

        self._global_region = GlobalRegion()
        self.add(self._global_region)

        self.element = _ElementRegionFactory(self)
        self.node = _NodeRegionFactory(self)

    def add(self, region: RegionBase) -> RegionBase:
        """Register a region, assigning a name and tag where needed.

        Args:
            region (RegionBase): Concrete region object.

        Returns:
            region (RegionBase): Original registered object. GlobalRegion uses
                reserved tag zero; other regions use this manager's positive space.

        Raises:
            TypeError: Input is not a RegionBase.
            ValueError: Foreign ownership, duplicate name, or tag conflict.
        """
        from femora.components.region.regions import GlobalRegion

        if not isinstance(region, RegionBase):
            raise TypeError("region must be a RegionBase instance")
        if region._owner is not None and region._owner is not self:
            raise ValueError("Region already belongs to another manager")
        if region.user_name == "Unnamed":
            region.user_name = self._generate_default_name(region)
        if region.user_name in self._names and self._names[region.user_name] is not region:
            raise ValueError(f"Region name '{region.user_name}' already exists in this manager")

        region._owner = self
        if isinstance(region, GlobalRegion):
            region.tag = 0
        else:
            try:
                region.tag = self._tagging.assign_tag(self._regions, region, self._start_tag)
            except ValueError as exc:
                raise ValueError(f"Region tag {region.tag} already exists") from exc

        self._regions[region.tag] = region
        self._names[region.user_name] = region
        return region

    def get(self, identifier: Union[int, str]) -> Optional[RegionBase]:
        """Look up a region by integer tag or exact name, returning None if absent.

        Args:
            identifier (int | str): Python/NumPy integers are tags. Other values
                are converted to strings for name lookup; numeric strings are names.
        """
        if isinstance(identifier, (int, np.integer)):
            return self._regions.get(int(identifier))
        return self._names.get(str(identifier))

    def get_all(self) -> Dict[int, RegionBase]:
        """Return a shallow registry snapshot, including the global region.

        Object values remain shared; editing dictionary membership does not
        edit the owning manager.
        """
        return dict(self._regions)

    def remove(self, identifier: Union[int, str]) -> None:
        """Detach a non-global region and retag surviving non-global regions.

        Args:
            identifier (int | str): Tag or name; missing entries are ignored.

        Raises:
            ValueError: Attempt to remove the global region at tag zero.

        Dependent parts and already assembled region arrays are not rewritten.
        """
        region = self.get(identifier)
        if region is not None:
            if region.tag == 0:
                raise ValueError("Cannot remove the global region (tag 0)")
            self._regions.pop(region.tag, None)
            self._names.pop(region.user_name, None)
            region.tag = None
            region._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach existing regions and create a new global region at tag zero.

        Old region objects are not reused. Parts retaining those objects must be
        rebuilt/reassigned; this is not a coordinated whole-model clear.
        """
        from femora.components.region.regions import GlobalRegion

        for region in list(self._regions.values()):
            region.tag = None
            region._owner = None
        self._regions.clear()
        self._names.clear()
        self._global_region = GlobalRegion()
        self.add(self._global_region)

    def set_tag_start(self, start_tag: int) -> None:
        """Set the non-global tag origin and retag non-global definitions.

        Args:
            start_tag (int): Integer-convertible origin of at least one.

        Raises:
            ValueError: Converted origin is below one or conversion fails.
            TypeError: Integer conversion is unsupported.

        The global region remains at zero. Existing integer references can become stale.
        """
        self._start_tag = int(start_tag)
        if self._start_tag < 1:
            raise ValueError("start_tag must be >= 1")
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        non_global = sorted(
            [r for r in self._regions.values() if r.tag != 0],
            key=lambda r: r.tag if r.tag is not None else 0,
        )
        self._regions = {0: self._global_region}
        for i, region in enumerate(non_global):
            region.tag = self._start_tag + i
            self._regions[region.tag] = region
        self._names = {r.user_name: r for r in self._regions.values()}

    def _generate_default_name(self, region: RegionBase) -> str:
        base_name = region.get_type()
        if base_name not in self._names:
            return base_name

        index = 2
        while True:
            candidate = f"{base_name}_{index}"
            if candidate not in self._names:
                return candidate
            index += 1

    @property
    def global_region(self) -> GlobalRegion:
        """Current global RegionBase object reserved at registry tag zero.

        A new object is created by ``clear()``; do not assume a previously held
        global-region reference remains registered after that operation.
        """
        return self._global_region

    def __len__(self) -> int:
        return len(self._regions)

    def __iter__(self):
        return iter(self._regions.values())
