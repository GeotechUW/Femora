# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Dict, Type

from femora.core.analysis_component_base import AnalysisComponent


class ConstraintHandler(AnalysisComponent):
    """Extension base for solver constraint-enforcement definitions.

    This is not a domain SP/MP constraint. Subclasses implement the Tcl command
    contract; ordinary scripts use ``model.analysis.constraint`` factories.
    """

    __doc_controls__ = {"summary": True, "members": ["register_handler"]}

    _handlers: Dict[str, Type["ConstraintHandler"]] = {}

    def __init__(self, handler_type: str) -> None:
        super().__init__()
        self.handler_type = handler_type

    @staticmethod
    def register_handler(name: str, handler_class: Type["ConstraintHandler"]) -> None:
        """Install a class-wide handler factory key, replacing an existing key.

        Args:
            name (str): Case-insensitive registry key.
            handler_class (type[ConstraintHandler]): Concrete constructor.

        Registration does not validate subclass compatibility or modify instances.
        """
        ConstraintHandler._handlers[name.lower()] = handler_class


__all__ = ["ConstraintHandler"]
