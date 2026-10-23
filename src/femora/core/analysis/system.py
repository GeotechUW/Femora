# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, Type

from femora.core.analysis_component_base import AnalysisComponent


class System(AnalysisComponent):
    """Extension base for linear equation-solver definitions.

    Concrete subclasses render a system command; they do not install native
    solver libraries. Ordinary construction uses ``model.analysis.system``.
    """

    __doc_controls__ = {"summary": True, "members": ["register_system"]}

    _systems: Dict[str, Type["System"]] = {}

    def __init__(self, system_type: str) -> None:
        """Create a System base instance.

        Args:
            system_type: The type name of the system solver.
        """
        super().__init__()
        self.system_type = system_type

    @staticmethod
    def register_system(name: str, system_class: Type["System"]) -> None:
        """Register a new solver system class.

        Args:
            name: Lowercase registry name.
            system_class: The System class type to register.
        """
        System._systems[name.lower()] = system_class


__all__ = ["System"]
