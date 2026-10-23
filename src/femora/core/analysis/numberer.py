# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, List, Type

from femora.core.analysis_component_base import AnalysisComponent


class Numberer(AnalysisComponent):
    """Base class for OpenSees degree-of-freedom (DOF) numberers.

    Numberers map structural node and equation definitions to solver system indices.
    """

    __doc_controls__ = {"summary": True, "members": ["register_numberer", "get_available_types"]}

    _numberers: Dict[str, Type["Numberer"]] = {}

    def __init__(self) -> None:
        """Create a Numberer base instance."""
        super().__init__()

    @staticmethod
    def register_numberer(name: str, numberer_class: Type["Numberer"]) -> None:
        """Register a new numberer class.

        Args:
            name: Lowercase registry name.
            numberer_class: The Numberer class type to register.
        """
        Numberer._numberers[name.lower()] = numberer_class

    @staticmethod
    def get_available_types() -> List[str]:
        """Get available registered numberer type names.

        Returns:
            A list of registered numberer names.
        """
        return list(Numberer._numberers.keys())


__all__ = ["Numberer"]
