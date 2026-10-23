# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, Type

from femora.core.analysis_component_base import AnalysisComponent


class Test(AnalysisComponent):
    """Base class for all OpenSees convergence tests.

    Convergence tests define the mathematical criteria used by solution
    algorithms to determine if equilibrium has been reached at each iteration.
    """

    __doc_controls__ = {"summary": True, "members": ["register_test"]}

    _tests: Dict[str, Type["Test"]] = {}

    def __init__(self, test_type: str) -> None:
        """Create a convergence test base instance.

        Args:
            test_type: The type name of the convergence test.
        """
        super().__init__()
        self.test_type = test_type

    @staticmethod
    def register_test(name: str, test_class: Type["Test"]) -> None:
        """Register a new convergence test class.

        Args:
            name: Lowercase registry name.
            test_class: The Test class type to register.
        """
        Test._tests[name.lower()] = test_class


__all__ = ["Test"]
