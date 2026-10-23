# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, Type

from femora.core.analysis_component_base import AnalysisComponent


class Algorithm(AnalysisComponent):
    """Extension base for solution algorithms registered by AlgorithmManager.

    Subclasses implement the AnalysisComponent Tcl contract. Ordinary scripts
    select algorithms through ``model.analysis.algorithm``.
    """

    __doc_controls__ = {"summary": True, "members": ["register_algorithm"]}

    _algorithms: Dict[str, Type["Algorithm"]] = {}

    def __init__(self, algorithm_type: str) -> None:
        super().__init__()
        self.algorithm_type = algorithm_type

    @staticmethod
    def register_algorithm(name: str, algorithm_class: Type["Algorithm"]) -> None:
        """Install a class-wide algorithm factory key, replacing an existing key.

        Args:
            name (str): Case-insensitive registry key.
            algorithm_class (type[Algorithm]): Concrete constructor supporting to_tcl().

        No subclass validation or update of existing instances is performed.
        """
        Algorithm._algorithms[name.lower()] = algorithm_class


__all__ = ["Algorithm"]
