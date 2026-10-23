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
    """Configure solver analyses through ``model.analysis``.

    Attributes:
        constraint (ConstraintHandlerManager): Enforcement method for domain constraints.
        numberer (NumbererManager): Cached equation-ordering definitions.
        system (SystemManager): Linear equation solver definitions.
        algorithm (AlgorithmManager): Solution algorithm definitions.
        test (TestManager): Convergence test definitions.
        integrator (IntegratorManager): Static/load or transient/time integration definitions.

    Factories return registered Analysis objects; add them to ``model.process``
    to schedule their solver commands. They do not run a solver in Python.
    Analysis constraint handlers differ from domain constraints created through
    ``model.constraint``. All solution choices must suit the model, MPI build,
    integrator, and physical problem; registration cannot establish that suitability.

    Example:
        ```python
        from femora import Model

        model = Model()
        gravity = model.analysis.static(
            name="gravity",
            constraint_handler=model.analysis.constraint.transformation(),
            numberer=model.analysis.numberer.rcm(),
            system=model.analysis.system.bandgeneral(),
            algorithm=model.analysis.algorithm.newton(),
            test=model.analysis.test.normdispincr(tol=1e-8, max_iter=30),
            integrator=model.analysis.integrator.loadcontrol(incr=0.1),
            num_steps=10,
        )
        model.process.add_step(gravity, "Equilibrate gravity")
        assert model.analysis.get("gravity") is gravity
        ```

    This configures a sequence, not a complete supported/loaded domain. Explicit
    transient schemes require stability and mass checks; retry limits and
    convergence tolerances are not substitutes for those checks.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "static",
            "transient",
            "variable_transient",
            "default_transient",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
            "update_constraint_handler",
            "update_numberer",
            "update_system",
            "update_algorithm",
            "update_test",
            "update_integrator",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
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
        """Register an analysis with a unique name and local tag.

        Args:
            analysis (Analysis): Unmanaged object or one already owned here.

        Returns:
            analysis (Analysis): Original registered object.

        Raises:
            TypeError: Input is not an Analysis.
            ValueError: Duplicate name, conflicting tag, or foreign ownership.
        """
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
        initialize: bool = False,
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
            initialize: Run OpenSees ``initialize`` before the first step.

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
                initialize=initialize,
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
        """Create a convenience transient configuration with overridable defaults.

        Args:
            username (str): Suffix for the name ``defaultTransient_<username>``.
            dt (float): Initial analysis time increment in model time units.
            num_steps (int | None): Requested steps, exclusive with final_time.
            final_time (float | None): Requested end time, exclusive with num_steps.
            options (dict | None): Overrides for numberer, integrator, system, test,
                algorithm, constraint_handler, max_retries, num_sublevels, num_substeps.

        Returns:
            analysis (Analysis): Registered transient definition. Defaults include
                ParallelRCM, Newmark(0.5, 0.25), Mumps, EnergyIncr(1e-3, 20, 2),
                ModifiedNewton with factor_once, Transformation, and 10 retries.

        Raises:
            ValueError: Both/neither duration selectors are supplied, or construction
                or registration validation fails.

        Note:
            This convenience configuration is not a calibration recommendation.
            Default factory expressions are evaluated even when an options key
            overrides their result, so additional stack objects may be registered.
        """
        if (num_steps is None and final_time is None) or (
            num_steps is not None and final_time is not None
        ):
            raise ValueError("Exactly one of num_steps or final_time must be provided")

        options = options or {}
        analysis_name = f"defaultTransient_{username}"
        numberer = options.get("numberer", self.numberer.parallelrcm())
        integrator = options.get("integrator", self.integrator.newmark(gamma=0.5, beta=0.25))
        system = options.get("system", self.system.mumps(icntl14=400, icntl7=7))
        test = options.get("test", self.test.energyincr(tol=1e-3, max_iter=20, print_flag=2))
        algorithm = options.get("algorithm", self.algorithm.modifiednewton(factor_once=True))
        constraint_handler = options.get("constraint_handler", self.constraint.transformation())
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
        """Resolve an analysis by tag, name, or direct object.

        Args:
            identifier (int | str | Analysis): Integer tag, exact name followed by
                a case-insensitive fallback, or an Analysis object passed unchanged.

        Raises:
            KeyError: Tag/name is absent.
            TypeError: Identifier type is unsupported.

        Direct object input is not an ownership validation operation.
        """
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
        """Return a shallow tag-to-analysis snapshot with shared definitions."""
        return dict(self._analyses)

    def remove(self, identifier: Union[int, str, Analysis]) -> None:
        """Detach the resolved analysis and compact remaining registry tags.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().

        Missing lookup keys raise KeyError. Process steps and stack component
        registries are not removed or rewritten, and no solver command executes.
        """
        analysis = self.get(identifier)
        self._analyses.pop(analysis.tag, None)
        self._names.pop(analysis.name, None)
        analysis.tag = None
        analysis._owner = None
        self._reassign_tags()

    def clear(self) -> None:
        """Detach analyses and clear all owned solution-component collections.

        Process steps, mesh geometry, and output files are retained. Clear or
        rebuild the process before exporting references to removed analyses.
        """
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
        """Set the positive analysis-tag origin and retag registered analyses.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. Stack component and solver node tags are unchanged.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def update_constraint_handler(
        self, identifier: Union[int, str, Analysis], constraint_handler: ConstraintHandler
    ) -> None:
        """Replace the resolved analysis's constraint-handler reference.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            constraint_handler (ConstraintHandler): New solution-stack component.

        This direct assignment does not execute the solver or validate compatibility.
        """
        self.get(identifier).constraint_handler = constraint_handler

    def update_numberer(self, identifier: Union[int, str, Analysis], numberer: Numberer) -> None:
        """Replace a definition's equation-ordering reference without running it.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            numberer (Numberer): Replacement numberer; compatibility is not validated here.
        """
        self.get(identifier).numberer = numberer

    def update_system(self, identifier: Union[int, str, Analysis], system: System) -> None:
        """Replace a definition's linear-system reference without solving equations.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            system (System): Replacement system; build/MPI compatibility remains required.
        """
        self.get(identifier).system = system

    def update_algorithm(self, identifier: Union[int, str, Analysis], algorithm: Algorithm) -> None:
        """Replace a definition's algorithm reference without solver execution.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            algorithm (Algorithm): Replacement algorithm; compatibility is not validated here.
        """
        self.get(identifier).algorithm = algorithm

    def update_test(self, identifier: Union[int, str, Analysis], test: Test) -> None:
        """Replace a definition's convergence-test reference.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            test (Test): Replacement test. This does not recheck a previously run solution.
        """
        self.get(identifier).test = test

    def update_integrator(
        self, identifier: Union[int, str, Analysis], integrator: Integrator
    ) -> None:
        """Replace an integrator while checking static/transient family compatibility.

        Args:
            identifier (int | str | Analysis): Reference accepted by get().
            integrator (Integrator): Replacement integration component.

        Raises:
            ValueError: A Static analysis receives a non-static integrator or a
                transient analysis receives a non-transient integrator.

        This family check does not verify time-step stability or model mass suitability.
        """
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
