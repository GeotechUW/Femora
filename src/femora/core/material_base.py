# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class Material(ABC):
    """Abstract base class for manager-owned OpenSees material objects.

    Material instances do not self-register and do not assign their own tags.
    A :class:`~femora.core.material_manager.MaterialManager` owns lifecycle
    operations, tag assignment, removal, and retagging for a local model context.

    Args:
        material_type: OpenSees material category (e.g. ``'nDMaterial'``).
        material_name: Concrete OpenSees material name (e.g. ``'ElasticIsotropic'``).
        user_name: User-specified label for this material instance.

    Attributes:
        tag: Manager-assigned OpenSees material tag.  Remains ``None`` until
            this object is added to a :class:`~femora.core.material_manager.MaterialManager`.
        user_name (str): Label used by the manager's name lookup.
        params (dict[str, Any]): Concrete component parameter storage.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "to_tcl",
            "updateMaterialStage",
            "set_parameter",
            "get_param",
        ],
    }

    def __init__(self, material_type: str, material_name: str, user_name: str) -> None:
        self.tag: Optional[int] = None
        self._owner: object | None = None
        self.material_type = material_type
        self.material_name = material_name
        self.user_name = user_name
        self.params: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Tag helpers
    # ------------------------------------------------------------------

    def _require_tag(self) -> int:
        """Return the assigned tag, or raise if this material is unmanaged."""
        if self.tag is None:
            raise ValueError(
                f"Material '{self.user_name}' must be added to a MaterialManager "
                "before rendering TCL."
            )
        return self.tag

    @abstractmethod
    def to_tcl(self) -> str:
        """Render a material definition without executing it.

        Returns:
            str: Concrete solver definition using the assigned material tag.

        Note:
            Subclasses implement this contract. Register the material before
            rendering; concrete implementations commonly require a tag.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Optional overrides
    # ------------------------------------------------------------------

    def updateMaterialStage(self, state: str) -> str:
        """Optionally render a stage transition for a constitutive model.

        Args:
            state (str): Stage selector interpreted by the concrete material.

        Returns:
            str: Empty string in this base implementation. Stage-capable
            subclasses override this hook; arbitrary materials are not converted.
        """
        return ""

    def set_parameter(
        self,
        parameter_name: str,
        new_value: Union[float, int, str, None] = None,
        element_tags: Optional[List[int]] = None,
    ) -> str:
        """Optionally render a material-specific parameter update.

        Args:
            parameter_name (str): Solver parameter name.
            new_value (float | int | str | None): Optional new value.
            element_tags (list[int] | None): Element targets for the command.

        Returns:
            str: Empty string in this base implementation. Concrete overrides
            determine supported parameters and command syntax.
        """
        return ""

    def get_param(self, key: str) -> Any:
        """Read a value from the concrete material's parameter dictionary.

        Args:
            key (str): Exact parameter key; no alias normalization is applied.

        Returns:
            Any: Stored value, without copying it.

        Raises:
            KeyError: The key is absent from ``params``.
        """
        return self.params[key]

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"tag={self.tag}, "
            f"type={self.material_type}, "
            f"name={self.material_name}, "
            f"user_name={self.user_name!r})"
        )

    def __str__(self) -> str:
        tag = self.tag if self.tag is not None else "unmanaged"
        return (
            f"{self.material_type} {self.material_name} "
            f"(Tag: {tag}, user_name: {self.user_name!r})"
        )


__all__ = ["Material"]
