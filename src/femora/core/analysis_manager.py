# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Union

from femora.components.analysis.analysis import Analysis
from femora.core.analysis.algorithm import Algorithm
from femora.core.analysis.algorithm_manager import AlgorithmManager
from femora.core.analysis.constraint_handler import ConstraintHandler
from femora.core.analysis.constraint_handler_manager import ConstraintHandlerManager
from femora.core.analysis.integrator import Integrator, StaticIntegrator, TransientIntegrator
from femora.core.analysis.integrator_manager import IntegratorManager
from femora.core.analysis.numberer import Numberer
from femora.core.analysis.system import System
from femora.core.analysis.system_manager import SystemManager
from femora.core.analysis.test import Test
from femora.core.analysis.test_manager import TestManager
from femora.core.numberer_manager import NumbererManager
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model


class AnalysisManager:
    """Manager-owned analysis stack for one Model model."""

    def __init__(self, mesh_maker: Model):
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "analysis", None)
        if isinstance(existing_manager, AnalysisManager):
            raise ValueError("mesh_maker already owns an analysis manager")

        self._mesh_maker = mesh_maker
        mesh_maker.analysis = self
        self._analyses: Dict[int, Analysis] = {}
        self._names: Dict[str, Analysis] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Analysis]()

        self.test = TestManager(self)
        self.constraint = ConstraintHandlerManager(self)
        self.numberer = NumbererManager(self)
        self.system = SystemManager(self)
        self.algorithm = AlgorithmManager(self)
        self.integrator = IntegratorManager(self)

    def add(self, analysis: Analysis) -> Analysis:
        if not isinstance(analysis, Analysis):
            raise TypeError("analysis must be an Analysis instance")
        if analysis.name in self._names and self._names[analysis.name] is not analysis:
            raise ValueError(f"Analysis name '{analysis.name}' is already in use")
        if analysis._owner is None:
            analysis._owner = self
        elif analysis._owner is not self:
            raise ValueError("analysis already belongs to another manager")
        try:
            analysis.tag = self._tagging.assign_tag(self._analyses, analysis, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Analysis tag {analysis.tag} already exists") from exc
        self._analyses[analysis.tag] = analysis
        self._names[analysis.name] = analysis
        return analysis

    def static(
        self,
        name: str,
        constraint_handler: ConstraintHandler,
        numberer: Numberer,
        system: System,
        algorithm: Algorithm,
        test: Test,
        integrator: StaticIntegrator,
        num_steps: int,
        max_retries: int = 10,
    ) -> Analysis:
        """Create and register a static Analysis.

        Args:
            name: Unique analysis name.
            constraint_handler: Constraint handler for boundary-condition enforcement.
            numberer: Degree-of-freedom numberer.
            system: Linear solver system.
            algorithm: Nonlinear solution algorithm.
            test: Convergence test.
            integrator: Static integrator.
            num_steps: Number of static analysis steps.
            max_retries: Same-step retries before reporting failure.

        Returns:
            The registered Analysis instance.
        """
        return self.add(
            Analysis(
                name=name,
                analysis_type="Static",
                constraint_handler=constraint_handler,
                numberer=numberer,
                system=system,
                algorithm=algorithm,
                test=test,
                integrator=integrator,
                num_steps=num_steps,
                max_retries=max_retries,
            )
        )

    def transient(
        self,
        name: str,
        constraint_handler: ConstraintHandler,
        numberer: Numberer,
        system: System,
        algorithm: Algorithm,
        test: Test,
        integrator: TransientIntegrator,
        dt: float | None = None,
        num_steps: int | None = None,
        final_time: float | None = None,
        dt_min: float | None = None,
        dt_max: float | None = None,
        num_sublevels: int | None = None,
        num_substeps: int | None = None,
        max_retries: int = 10,
    ) -> Analysis:
        """Create and register a transient Analysis.

        Args:
            name: Unique analysis name.
            constraint_handler: Constraint handler for boundary-condition enforcement.
            numberer: Degree-of-freedom numberer.
            system: Linear solver system.
            algorithm: Nonlinear solution algorithm.
            test: Convergence test.
            integrator: Transient integrator.
            dt: Constant time-step increment. Required unless both dt_min and dt_max
                are provided.
            num_steps: Optional number of transient steps.
            final_time: Optional end time. Exactly one of `num_steps` or `final_time`
                must be provided.
            dt_min: Optional first time step for a linear time-step ramp.
            dt_max: Optional last time step for a linear time-step ramp.
            num_sublevels: Optional transient sublevel count for retry logic.
            num_substeps: Optional transient substep count for retry logic.
            max_retries: Same-step retries before substepping or failure.

        Returns:
            The registered Analysis instance.
        """
        return self.add(
            Analysis(
                name=name,
                analysis_type="Transient",
                constraint_handler=constraint_handler,
                numberer=numberer,
                system=system,
                algorithm=algorithm,
                test=test,
                integrator=integrator,
                num_steps=num_steps,
                final_time=final_time,
                dt=dt,
                dt_min=dt_min,
                dt_max=dt_max,
                num_sublevels=num_sublevels,
                num_substeps=num_substeps,
                max_retries=max_retries,
            )
        )

    def variable_transient(
        self,
        name: str,
        constraint_handler: ConstraintHandler,
        numberer: Numberer,
        system: System,
        algorithm: Algorithm,
        test: Test,
        integrator: TransientIntegrator,
        dt: float,
        dt_min: float,
        dt_max: float,
        jd: int,
        num_steps: int | None = None,
        final_time: float | None = None,
        num_sublevels: int | None = None,
        num_substeps: int | None = None,
        max_retries: int = 10,
    ) -> Analysis:
        """Create and register a variable-transient Analysis.

        Args:
            name: Unique analysis name.
            constraint_handler: Constraint handler for boundary-condition enforcement.
            numberer: Degree-of-freedom numberer.
            system: Linear solver system.
            algorithm: Nonlinear solution algorithm.
            test: Convergence test.
            integrator: Transient integrator.
            dt: Initial time-step increment.
            dt_min: Minimum allowable time step.
            dt_max: Maximum allowable time step.
            jd: Desired number of iterations per step.
            num_steps: Optional number of transient steps.
            final_time: Optional end time. Exactly one of `num_steps` or `final_time`
                must be provided.
            num_sublevels: Optional transient sublevel count for retry logic.
            num_substeps: Optional transient substep count for retry logic.
            max_retries: Same-step retries before substepping or failure.

        Returns:
            The registered Analysis instance.
        """
        return self.add(
            Analysis(
                name=name,
                analysis_type="VariableTransient",
                constraint_handler=constraint_handler,
                numberer=numberer,
                system=system,
                algorithm=algorithm,
                test=test,
                integrator=integrator,
                num_steps=num_steps,
                final_time=final_time,
                dt=dt,
                dt_min=dt_min,
                dt_max=dt_max,
                jd=jd,
                num_sublevels=num_sublevels,
                num_substeps=num_substeps,
                max_retries=max_retries,
            )
        )

    def default_transient(
        self,
        username: str,
        dt: float,
        num_steps: int | None = None,
        final_time: float | None = None,
        options: dict | None = None,
    ) -> Analysis:
        if (num_steps is None and final_time is None) or (
            num_steps is not None and final_time is not None
        ):
            raise ValueError("Exactly one of num_steps or final_time must be provided")

        options = options or {}
        analysis_name = f"defaultTransient_{username}"
        numberer = options.get("numberer", self.numberer.parallelrcm())
        integrator = options.get(
            "integrator", self.integrator.newmark(gamma=0.5, beta=0.25)
        )
        system = options.get("system", self.system.mumps(icntl14=400, icntl7=7))
        test = options.get(
            "test", self.test.energyincr(tol=1e-3, max_iter=20, print_flag=2)
        )
        algorithm = options.get(
            "algorithm", self.algorithm.modifiednewton(factor_once=True)
        )
        constraint_handler = options.get(
            "constraint_handler", self.constraint.transformation()
        )
        max_retries = options.get("max_retries", 10)
        num_sublevels = options.get("num_sublevels")
        num_substeps = options.get("num_substeps")
        return self.add(
            Analysis(
                analysis_name,
                "Transient",
                constraint_handler,
                numberer,
                system,
                algorithm,
                test,
                integrator,
                num_steps=num_steps,
                final_time=final_time,
                dt=dt,
                max_retries=max_retries,
                num_sublevels=num_sublevels,
                num_substeps=num_substeps,
            )
        )

    def get(self, identifier: Union[int, str, Analysis]) -> Analysis:
        if isinstance(identifier, int):
            analysis = self._analyses.get(identifier)
            if analysis is None:
                raise KeyError(f"No analysis found with tag {identifier}")
            return analysis
        if isinstance(identifier, str):
            analysis = self._names.get(identifier)
            if analysis is None:
                for item in self._analyses.values():
                    if item.name.lower() == identifier.lower():
                        return item
                raise KeyError(f"No analysis found with name '{identifier}'")
            return analysis
        if isinstance(identifier, Analysis):
            return identifier
        raise TypeError(
            f"Identifier must be an int (tag), str (name), or Analysis instance, not {type(identifier)}"
        )

    def get_all(self) -> Dict[int, Analysis]:
        return dict(self._analyses)

    def remove(self, identifier: Union[int, str, Analysis]) -> None:
        analysis = self.get(identifier)
        self._analyses.pop(analysis.tag, None)
        self._names.pop(analysis.name, None)
        analysis.tag = None
        analysis._owner = None
        self._reassign_tags()

    def clear(self) -> None:
        for analysis in list(self._analyses.values()):
            analysis.tag = None
            analysis._owner = None
        self._analyses.clear()
        self._names.clear()
        self.test.clear()
        self.constraint.clear()
        self.numberer.clear()
        self.system.clear()
        self.algorithm.clear()
        self.integrator.clear()

    def set_tag_start(self, start_tag: int) -> None:
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def update_constraint_handler(
        self, identifier: Union[int, str, Analysis], constraint_handler: ConstraintHandler
    ) -> None:
        self.get(identifier).constraint_handler = constraint_handler

    def update_numberer(self, identifier: Union[int, str, Analysis], numberer: Numberer) -> None:
        self.get(identifier).numberer = numberer

    def update_system(self, identifier: Union[int, str, Analysis], system: System) -> None:
        self.get(identifier).system = system

    def update_algorithm(self, identifier: Union[int, str, Analysis], algorithm: Algorithm) -> None:
        self.get(identifier).algorithm = algorithm

    def update_test(self, identifier: Union[int, str, Analysis], test: Test) -> None:
        self.get(identifier).test = test

    def update_integrator(self, identifier: Union[int, str, Analysis], integrator: Integrator) -> None:
        analysis = self.get(identifier)
        if analysis.analysis_type == "Static" and not isinstance(integrator, StaticIntegrator):
            raise ValueError(
                f"Static analysis requires a static integrator. {integrator.integrator_type} is not compatible."
            )
        if analysis.analysis_type in ["Transient", "VariableTransient"] and not isinstance(
            integrator, TransientIntegrator
        ):
            raise ValueError(
                f"Transient analysis requires a transient integrator. {integrator.integrator_type} is not compatible."
            )
        analysis.integrator = integrator

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._analyses, self._start_tag)
        self._names = {analysis.name: analysis for analysis in self._analyses.values()}


__all__ = ["AnalysisManager"]
