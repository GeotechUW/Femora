# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Generic, Optional, Type, TypeVar

from femora.core.analysis_component_base import AnalysisComponent
from femora.core.tagging import CompactRetagPolicy

TComponent = TypeVar("TComponent", bound=AnalysisComponent)


class TaggedComponentManager(Generic[TComponent]):
    """Shared registry operations inherited by analysis component managers.

    Algorithm, constraint-handler, system, test, and integrator managers expose
    these operations through their model.analysis namespaces. This implementation
    is not constructed directly in ordinary scripts. Each instance has its own
    tag space; factory type maps are supplied by the concrete component family.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "add",
            "create",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
            "get_available_types",
        ],
    }

    def __init__(self, owner: object, component_cls: Type[TComponent], registry_attr: str) -> None:
        self._owner = owner
        self._component_cls = component_cls
        self._registry_attr = registry_attr
        self._items: Dict[int, TComponent] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[TComponent]()

    def add(self, component: TComponent) -> TComponent:
        """Register an object of this manager's component family and assign its tag.

        Args:
            component (TComponent): Unmanaged object or one already owned here.

        Returns:
            component (TComponent): Original object, retained by this manager.

        Raises:
            TypeError: Object is not of the expected component family.
            ValueError: Ownership or registry-tag conflict.
        """
        if not isinstance(component, self._component_cls):
            raise TypeError(f"component must be a {self._component_cls.__name__} instance")
        if component._owner is None:
            component._owner = self
        elif component._owner is not self:
            raise ValueError("component already belongs to another manager")
        try:
            component.tag = self._tagging.assign_tag(self._items, component, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Component tag {component.tag} already exists") from exc
        self._items[component.tag] = component
        return component

    def create(self, component_type: str, **kwargs: Any) -> TComponent:
        """Construct and register a component using its family factory key.

        Args:
            component_type (str): Case-insensitive registry type name.
            **kwargs (Any): Arguments passed to the registered constructor.

        Returns:
            component (TComponent): New registered definition.

        Raises:
            ValueError: Type name is unknown or component/registration validation fails.
            TypeError: Constructor arguments are unsupported.
        """
        registry: Dict[str, Type[TComponent]] = getattr(self._component_cls, self._registry_attr)
        key = component_type.lower()
        if key not in registry:
            raise ValueError(f"Unknown {self._component_cls.__name__} type: {component_type}")
        return self.add(registry[key](**kwargs))

    def get(self, tag: int) -> Optional[TComponent]:
        """Look up a current integer-convertible component tag, returning None if absent.

        Args:
            tag (int): Local component registry key, not a model node/cell tag.
        """
        return self._items.get(int(tag))

    def get_all(self) -> Dict[int, TComponent]:
        """Return a shallow registry snapshot with original component objects."""
        return dict(self._items)

    def remove(self, tag: int) -> None:
        """Detach one component and compact surviving registry tags.

        Args:
            tag (int): Current tag; absent entries are ignored.

        Analyses retaining the detached object are not repaired or removed.
        Registry edits do not reconfigure an already running solver.
        """
        component = self._items.pop(int(tag), None)
        if component is not None:
            component.tag = None
            component._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach all family components and clear their assigned tags.

        The class-wide constructor map is retained. Existing Analysis objects
        can still hold references to detached components.
        """
        for component in list(self._items.values()):
            component.tag = None
            component._owner = None
        self._items.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive component-tag origin and retag current objects.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. Cached integer references may become stale.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def get_available_types(self) -> list[str]:
        """Return current class-wide constructor keys for this component family.

        These are type names accepted by create(), not the tags of registered
        instances or a probe of features compiled into the installed solver.
        """
        registry: Dict[str, Type[TComponent]] = getattr(self._component_cls, self._registry_attr)
        return list(registry.keys())

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._items, self._start_tag)


__all__ = ["TaggedComponentManager"]
