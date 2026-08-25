# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from typing import Optional

from femora.core.analysis.algorithm import Algorithm
from femora.core.analysis.constraint_handler import ConstraintHandler
from femora.core.analysis.integrator import Integrator, StaticIntegrator, TransientIntegrator
from femora.core.analysis.numberer import Numberer
from femora.core.analysis.system import System
from femora.core.analysis.test import Test
from femora.core.analysis_component_base import AnalysisComponent


class Analysis(AnalysisComponent):
    """Main class for managing an OpenSees structural analysis.

    Analysis combines six modular components (constraint handler, DOF numberer,
    system solver, solution algorithm, convergence test, and integrator) to define
    how a static or transient dynamic finite element simulation is performed. It
    manages Static, Transient, or VariableTransient analysis loops.

    Tcl form:
        ``analysis <Static|Transient|VariableTransient>``

    Example:
        ```python
        from femora.core.model import Model
        from femora.components.analysis.analysis import Analysis

        model = Model()

        # Create required analysis components first
        handler = model.analysis.constraint.transformation()
        numberer = model.analysis.numberer.rcm()
        system = model.analysis.system.bandgeneral()
        algorithm = model.analysis.algorithm.newton()
        test = model.analysis.test.normunbalance(tol=1e-6, max_iter=100)
        integrator = model.analysis.integrator.loadcontrol(incr=0.1)

        # Construct and add the static analysis
        analysis = model.analysis.add(
            Analysis(
                name="Pushover",
                analysis_type="Static",
                constraint_handler=handler,
                numberer=numberer,
                system=system,
                algorithm=algorithm,
                test=test,
                integrator=integrator,
                num_steps=10,
            )
        )
        print(analysis.tag)
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(
        self,
        name: str,
        analysis_type: str,
        constraint_handler: ConstraintHandler,
        numberer: Numberer,
        system: System,
        algorithm: Algorithm,
        test: Test,
        integrator: Integrator,
        num_steps: Optional[int] = None,
        final_time: Optional[float] = None,
        dt: Optional[float] = None,
        dt_min: Optional[float] = None,
        dt_max: Optional[float] = None,
        jd: Optional[int] = None,
        num_sublevels: Optional[int] = None,
        num_substeps: Optional[int] = None,
    ):
        """Initializes the Analysis with all required components.

        This method validates component compatibility and analysis parameters
        before creating the analysis object.

        Args:
            name: Name of the analysis for identification. Must be unique.
            analysis_type: Type of analysis. Must be one of "Static", "Transient",
                or "VariableTransient".
            constraint_handler: The constraint handler for enforcing boundary conditions.
            numberer: The DOF numberer for mapping equation numbers.
            system: The system solver for solving linear matrix equations.
            algorithm: The non-linear iterative solution algorithm.
            test: The convergence test check.
            integrator: The integrator. Must be compatible with analysis_type
                (StaticIntegrator for Static, TransientIntegrator for Transient/VariableTransient).
            num_steps: Number of analysis steps. Required for Static, optional for
                others (mutually exclusive with final_time).
            final_time: Final analysis time. Optional for Transient/VariableTransient
                (mutually exclusive with num_steps).
            dt: Constant time step increment. Required for Transient unless both
                dt_min and dt_max are provided. Required for VariableTransient.
            dt_min: Minimum/first time step. For Transient, providing both dt_min
                and dt_max creates a linear time-step ramp over num_steps. Required
                for VariableTransient.
            dt_max: Maximum/last time step. For Transient, providing both dt_min
                and dt_max creates a linear time-step ramp over num_steps. Required
                for VariableTransient.
            jd: Number of iterations desired at each step. Required for VariableTransient.
            num_sublevels: Number of sublevels for transient analysis failure recovery.
            num_substeps: Number of substeps to try at each sublevel.

        Raises:
            ValueError: If integrator type is incompatible with analysis type,
                or if parameters are inconsistent, or if analysis_type is invalid.
        """
        super().__init__()
        self.name = name
        self.analysis_type = analysis_type

        # Validate analysis type
        if analysis_type not in ["Static", "Transient", "VariableTransient"]:
            raise ValueError(f"Unknown analysis type: {analysis_type}. Must be 'Static', 'Transient', or 'VariableTransient'.")

        # Set all components
        self.constraint_handler = constraint_handler
        self.numberer = numberer
        self.system = system
        self.algorithm = algorithm
        self.test = test

        # Validate integrator compatibility
        if analysis_type == "Static" and not isinstance(integrator, StaticIntegrator):
            raise ValueError(f"Static analysis requires a static integrator. {integrator.integrator_type} is not compatible.")

        elif analysis_type in ["Transient", "VariableTransient"] and not isinstance(integrator, TransientIntegrator):
            raise ValueError(f"Transient analysis requires a transient integrator. {integrator.integrator_type} is not compatible.")

        self.integrator = integrator

        # Validate and set analysis parameters
        if analysis_type == "Static":
            if num_steps is None:
                raise ValueError("Static analysis requires num_steps parameter.")
            if final_time is not None:
                raise ValueError("Static analysis does not use final_time parameter.")
        else:  # Transient or VariableTransient
            if num_steps is None and final_time is None:
                raise ValueError("Transient analysis requires either num_steps or final_time parameter.")
            if num_steps is not None and final_time is not None:
                raise ValueError("Only one of num_steps or final_time should be provided, not both.")

        self.num_steps = num_steps
        self.final_time = final_time

        has_dt_range = dt_min is not None or dt_max is not None
        if analysis_type == "Transient":
            if has_dt_range and (dt_min is None or dt_max is None):
                raise ValueError("Transient analysis requires both dt_min and dt_max when using a time-step ramp.")
            if has_dt_range and dt is not None:
                raise ValueError("Use either dt or dt_min/dt_max for Transient analysis, not both.")
            if has_dt_range and final_time is not None:
                raise ValueError("Transient dt_min/dt_max ramp requires num_steps, not final_time.")
            if not has_dt_range and dt is None:
                raise ValueError("Transient analysis requires dt, or both dt_min and dt_max.")

        if analysis_type == "VariableTransient":
            if dt is None:
                raise ValueError("VariableTransient analysis requires a time step (dt).")
            if dt_min is None or dt_max is None:
                raise ValueError("VariableTransient analysis requires dt_min and dt_max parameters.")
            if jd is None:
                raise ValueError("VariableTransient analysis requires jd parameter (desired iterations per step).")

        if dt is not None and dt <= 0.0:
            raise ValueError("dt must be positive.")
        if dt_min is not None and dt_min <= 0.0:
            raise ValueError("dt_min must be positive.")
        if dt_max is not None and dt_max <= 0.0:
            raise ValueError("dt_max must be positive.")

        self.dt = dt
        self.dt_min = dt_min
        self.dt_max = dt_max
        self.jd = jd

        # Optional sublevel parameters (only applicable to Transient analyses)
        if analysis_type == "Static" and (num_sublevels is not None or num_substeps is not None):
            raise ValueError("num_sublevels and num_substeps are only applicable to Transient analysis.")

        if (num_sublevels is not None and num_substeps is None) or (num_sublevels is None and num_substeps is not None):
            raise ValueError("Both num_sublevels and num_substeps must be provided if either is specified.")

        self.num_sublevels = num_sublevels
        self.num_substeps = num_substeps

    def to_tcl(self) -> str:
        """Render this analysis configuration as OpenSees Tcl commands.

        This method generates the complete TCL script for setting up and
        running the analysis, including all component definitions and the
        analysis loop.

        Returns:
            The TCL command string.
        """
        progress_name = self.name.replace("|", "/").replace("\n", " ")

        # Generate TCL commands for each component
        commands = []
        commands.append("if {$pid == 0} {" + f'puts [string repeat "=" 120] ' + "}")
        commands.append("if {$pid == 0} {" + f'puts "Starting analysis : {self.name}"' + "}")
        commands.append(commands[0])
        commands.append(self.constraint_handler.to_tcl())
        commands.append(self.numberer.to_tcl())
        commands.append(self.system.to_tcl())
        commands.append(self.algorithm.to_tcl())
        commands.append(self.test.to_tcl())
        commands.append(self.integrator.to_tcl())

        # Add analysis command
        commands.append(f"analysis {self.analysis_type}")

        if self.final_time is not None:
            total_steps = (
                f"[expr {{max(1, int(ceil(({self.final_time} - [getTime]) "
                f"/ {self.dt})))}}]"
            )
        else:
            total_steps = str(self.num_steps)

        commands.extend(
            [
                "set FemoraAnalysisStep 0",
                f"set FemoraAnalysisTotal {total_steps}",
                "set FemoraProgressStride [expr {max(1, int(ceil(double($FemoraAnalysisTotal) / 1000.0)))}]",
                f'if {{$pid == 0}} {{puts "FEMORA_PROGRESS|START|{progress_name}|$FemoraAnalysisTotal"; flush stdout}}',
            ]
        )

        # Run one increment at a time so failures and progress remain observable.
        if self.analysis_type == "Static":
            commands.append("while {$FemoraAnalysisStep < $FemoraAnalysisTotal} {")
            commands.append("\tset Ok [analyze 1]")
            commands.extend(self._step_status_commands(progress_name))
            commands.append("}")
        elif self.analysis_type in ["Transient", "VariableTransient"]:
            if self.final_time is not None:
                commands.append("while {[getTime] < %f} {" % self.final_time)
                commands.append(f"\tset Ok [analyze 1 {self.dt}]")
                commands.extend(self._step_status_commands(progress_name))
                commands.append("}")
            elif self.analysis_type == "Transient" and self.dt_min is not None and self.dt_max is not None:
                commands.append(f"set numSteps {self.num_steps}")
                commands.append(f"set dt_min {self.dt_min}")
                commands.append(f"set dt_max {self.dt_max}")
                commands.append("for {set AnalysisStep 0} {$AnalysisStep < $numSteps} {incr AnalysisStep} {")
                commands.append("\tif {$numSteps == 1} {")
                commands.append("\t\tset dt $dt_min")
                commands.append("\t} else {")
                commands.append("\t\tset dt [expr {$dt_min + double($AnalysisStep)/($numSteps-1)*($dt_max-$dt_min)}]")
                commands.append("\t}")
                commands.append("\tset Ok [analyze 1 $dt]")
                commands.extend(self._step_status_commands(progress_name))
                commands.append("}")
            else:
                commands.append("while {$FemoraAnalysisStep < $FemoraAnalysisTotal} {")
                commands.append(f"\tset Ok [analyze 1 {self.dt}]")
                commands.extend(self._step_status_commands(progress_name))
                commands.append("}")

        # wipe analysis command
        commands.append("wipeAnalysis")

        return "\n".join(commands)

    @staticmethod
    def _step_status_commands(progress_name: str) -> list[str]:
        """Return Tcl commands that report progress and stop on failed steps."""
        return [
            "\tif {$Ok != 0} {",
            f'\t\tif {{$pid == 0}} {{puts stderr "FEMORA_PROGRESS|ERROR|{progress_name}|[expr {{$FemoraAnalysisStep + 1}}]|$Ok"; flush stderr}}',
            f'\t\terror "Femora analysis \'{progress_name}\' failed at step [expr {{$FemoraAnalysisStep + 1}}] with code $Ok"',
            "\t}",
            "\tincr FemoraAnalysisStep",
            "\tif {$pid == 0 && (($FemoraAnalysisStep % $FemoraProgressStride) == 0 || $FemoraAnalysisStep == $FemoraAnalysisTotal)} {",
            f'\t\tputs "FEMORA_PROGRESS|UPDATE|{progress_name}|$FemoraAnalysisStep|$FemoraAnalysisTotal"',
            "\t\tflush stdout",
            "\t}",
        ]


__all__ = ["Analysis", "AnalysisManager"]


def __getattr__(name: str):
    if name == "AnalysisManager":
        from femora.core.analysis_manager import AnalysisManager

        return AnalysisManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
