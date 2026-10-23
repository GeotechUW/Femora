# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from femora.core.tagging import TaggedObject


class Damping(TaggedObject, ABC):
    """Extension base for model-owned damping definitions.

    Args:
        user_name (str | None): Optional label; registration generates a unique
            default when the placeholder name is used.

    Concrete subclasses implement solver-specific rendering. Prefer factories
    on ``model.damping`` and associate the returned object with a region.
    """

    __doc_controls__ = {"summary": True, "members": ["name", "remove", "to_tcl"]}

    def __init__(self, user_name: Optional[str] = None) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None
        self.user_name = user_name or "UnnamedDamping"

    @property
    def name(self) -> str:
        """Display name derived as damping<tag> when tagged, otherwise user_name.

        This is not always the unique user label stored by the manager and can
        change when the registry retags objects.
        """
        if self.tag is not None:
            return f"damping{self.tag}"
        return self.user_name

    def remove(self) -> None:
        """Ask the owning manager to detach this object, if one is available.

        Unmanaged objects are ignored. Region references and exported scripts
        are not rewritten; surviving registry tags can change.
        """
        if self._owner is not None and hasattr(self._owner, "remove"):
            self._owner.remove(self.tag)

    def __str__(self) -> str:
        tag_str = str(self.tag) if self.tag is not None else "unmanaged"
        res = f"Damping Class:\t{self.__class__.__name__}"
        res += f"\n\tName: {self.name}"
        res += f"\n\tTag: {tag_str}"
        return res

    @abstractmethod
    def to_tcl(self) -> str:
        """Render damping syntax according to the concrete component contract.

        Returns:
            command (str): Subclass-generated Tcl. Some damping families require
                region/export integration; rendering is not solver execution.
        """
        pass
