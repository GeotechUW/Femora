# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, List, Type

from femora.core.analysis_component_base import AnalysisComponent


class Integrator(AnalysisComponent):
    """Extension base for static and transient integration command definitions.

    Concrete classes implement Tcl rendering and inherit the appropriate static
    or transient family marker. Use ``model.analysis.integrator`` in model scripts.
    """

    __doc_controls__ = {"summary": True, "members": ["register_integrator"]}

    _integrators: Dict[str, Type["Integrator"]] = {}

    def __init__(self, integrator_type: str) -> None:
        """Create an Integrator base instance.

        Args:
            integrator_type: The type name of the integrator.
        """
        super().__init__()
        self.integrator_type = integrator_type

    @staticmethod
    def register_integrator(name: str, integrator_class: Type["Integrator"]) -> None:
        """Register a new integrator class.

        Args:
            name: Lowercase registry name.
            integrator_class: The Integrator class type to register.
        """
        Integrator._integrators[name.lower()] = integrator_class


class StaticIntegrator(Integrator):
    """Base class for static integrators, used in static analysis."""

    __doc_controls__ = {"summary": True, "members": ["get_static_types"]}

    def __init__(self, integrator_type: str) -> None:
        """Create a StaticIntegrator base instance.

        Args:
            integrator_type: The type name of the static integrator.
        """
        super().__init__(integrator_type)

    @staticmethod
    def get_static_types() -> List[str]:
        """Get available static integrator types.

        Returns:
            A list of registered static integrator names.
        """
        return [
            t for t, cls in Integrator._integrators.items() if issubclass(cls, StaticIntegrator)
        ]


class TransientIntegrator(Integrator):
    """Base class for transient integrators, used in dynamic analysis."""

    __doc_controls__ = {"summary": True, "members": ["get_transient_types"]}

    def __init__(self, integrator_type: str) -> None:
        """Create a TransientIntegrator base instance.

        Args:
            integrator_type: The type name of the transient integrator.
        """
        super().__init__(integrator_type)

    @staticmethod
    def get_transient_types() -> List[str]:
        """Get available transient integrator types.

        Returns:
            A list of registered transient integrator names.
        """
        return [
            t for t, cls in Integrator._integrators.items() if issubclass(cls, TransientIntegrator)
        ]


__all__ = ["Integrator", "StaticIntegrator", "TransientIntegrator"]
