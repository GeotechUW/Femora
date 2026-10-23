# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from femora.core.analysis_manager import AnalysisManager

from femora.components.analysis.constraint_handlers import (
    AutoConstraintHandler,
    LagrangeConstraintHandler,
    PenaltyConstraintHandler,
    PlainConstraintHandler,
    TransformationConstraintHandler,
)
from femora.core.analysis.constraint_handler import ConstraintHandler
from femora.core.tagged_component_manager import TaggedComponentManager


class ConstraintHandlerManager(TaggedComponentManager[ConstraintHandler]):
    """Create enforcement methods through ``model.analysis.constraint``.

    These definitions tell an analysis how to enforce existing SP/MP constraints;
    they do not create supports, diaphragms, or coupling relationships. Factories
    return registered handlers and forward keyword options to the concrete
    component constructor. Solver/matrix and constraint-topology compatibility
    must be checked for the full model.
    """

    __doc_controls__ = {
        "summary": True,
        "members": ["plain", "transformation", "penalty", "lagrange", "auto"],
    }

    def __init__(self, analysis_manager: "AnalysisManager") -> None:
        super().__init__(analysis_manager, ConstraintHandler, "_handlers")

    def plain(self) -> PlainConstraintHandler:
        """Create a Plain constraint handler.

        Returns:
            component (PlainConstraintHandler): Registered definition. Creating it does not run OpenSees.
        """
        component = PlainConstraintHandler()
        self.add(component)
        return component

    def transformation(self) -> TransformationConstraintHandler:
        """Create a Transformation constraint handler.

        Returns:
            component (TransformationConstraintHandler): Registered definition. Creating it does not run OpenSees.
        """
        component = TransformationConstraintHandler()
        self.add(component)
        return component

    def penalty(self, *, alpha_s: float, alpha_m: float) -> PenaltyConstraintHandler:
        """Create a Penalty constraint handler.

        Args:
            alpha_s: Penalty scale factor for single-point (SP) constraints.
            alpha_m: Penalty scale factor for multi-point (MP) constraints.

        Returns:
            component (PenaltyConstraintHandler): Registered definition. Creating it does not run OpenSees.
        """
        component = PenaltyConstraintHandler(alpha_s=alpha_s, alpha_m=alpha_m)
        self.add(component)
        return component

    def lagrange(self, *, alpha_s: float = 1.0, alpha_m: float = 1.0) -> LagrangeConstraintHandler:
        """Create a Lagrange constraint handler.

        Args:
            alpha_s: Scaling factor for single-point constraints.
            alpha_m: Scaling factor for multi-point constraints.

        Returns:
            component (LagrangeConstraintHandler): Registered definition. Creating it does not run OpenSees.
        """
        component = LagrangeConstraintHandler(alpha_s=alpha_s, alpha_m=alpha_m)
        self.add(component)
        return component

    def auto(
        self,
        *,
        verbose: bool = False,
        auto_penalty: float | None = None,
        user_penalty: float | None = None,
    ) -> AutoConstraintHandler:
        """Create an Auto constraint handler.

        Args:
            verbose: If True, outputs diagnostic selection steps.
            auto_penalty: Optional automatic penalty scaling value.
            user_penalty: Optional user override penalty value.

        Returns:
            component (AutoConstraintHandler): Registered definition. Creating it does not run OpenSees.
        """
        component = AutoConstraintHandler(
            verbose=verbose, auto_penalty=auto_penalty, user_penalty=user_penalty
        )
        self.add(component)
        return component


__all__ = ["ConstraintHandlerManager"]
