# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

import weakref
from abc import ABC, abstractmethod
from typing import Any, Optional

from femora.core.damping_base import Damping


class RegionBase(ABC):
    """Extension base for defining regions in a model.

    Region objects do not self-register and do not assign their own tags.
    A RegionManager owns lifecycle operations, tag assignment, removal,
    and retagging for a local model context.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "tag",
            "name",
            "damping",
            "set_damping",
            "to_tcl",
            "get_type",
        ],
    }

    def __init__(self, user_name: str = None, damping: Damping = None) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[Any] = None
        self.user_name = user_name or "Unnamed"
        self._damping = weakref.ref(damping) if damping else None
        self.active = True

    @property
    def tag(self) -> Optional[int]:
        """Current manager-assigned region tag, or None while unmanaged.

        Tag zero is reserved for the model's global region. Do not manually
        assign tags to bypass registration or overwrite registry ownership.
        """
        return self._tag if hasattr(self, "_tag") else None

    @tag.setter
    def tag(self, value: Optional[int]) -> None:
        """Store a tag for manager lifecycle operations without registry validation."""
        self._tag = value

    @property
    def name(self) -> str:
        """User label stored on this region, not a generated solver node group."""
        return self.user_name

    @property
    def damping(self) -> Optional[Damping]:
        """Associated damping object, or None when unassigned or collected.

        The region holds a weak reference. Keep damping registered with its
        model manager so that its definition remains alive and exportable.
        """
        return self._damping() if self._damping else None

    @damping.setter
    def damping(self, value: Optional[Damping]) -> None:
        """Replace the weak association with a Damping object or None.

        Raises:
            TypeError: A non-None value is not a Damping instance.
        """
        if value is not None and not isinstance(value, Damping):
            raise TypeError("damping must be an instance of Damping")
        self._damping = weakref.ref(value) if value else None

    @damping.deleter
    def damping(self) -> None:
        """Clear the damping association without deleting its registered object."""
        self._damping = None

    def set_damping(self, damping_instance: Damping) -> None:
        """Assign damping through the validated damping property.

        Args:
            damping_instance (Damping): Definition to associate with this region.

        Shared regions affect all their consumers; this method neither creates
        a private copy nor updates files already exported to the solver.
        """
        self.damping = damping_instance

    def __str__(self) -> str:
        type_name = self.get_type()
        res = "Region class"
        res += f"\n\tTag: {self.tag}"
        res += f"\n\tName: {self.name}"
        res += f"\n\tType: {type_name}"
        res += f"\n\tActive: {self.active}"
        res += (
            f"\n\tDamping: " + ("\n\t" + str(self.damping)).replace("\n", "\n\t")
            if self.damping
            else "\n\tDamping: None"
        )
        return res

    @abstractmethod
    def to_tcl(self) -> str:
        """Render the concrete region's solver definition without executing it.

        Returns:
            command (str): Subclass-defined Tcl requiring appropriate export
                context and registry identity.
        """
        pass

    @staticmethod
    @abstractmethod
    def get_type() -> str:
        """Return the concrete family label used for type reporting/default names.

        Returns:
            label (str): Region kind supplied by the concrete subclass.
        """
        pass
