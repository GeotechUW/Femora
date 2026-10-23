# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from femora.components.actions.action import (
    ExitAction,
    LoadConstAction,
    RemoveLoadPatternsAction,
    RemoveRecordersAction,
    ResetAction,
    SetMaterialParameterAction,
    SetTimeAction,
    TclAction,
    UpdateMaterialStageToElasticAction,
    UpdateMaterialStageToPlasticAction,
    WipeAction,
    WipeAnalysisAction,
)
from femora.core.material_base import Material

if TYPE_CHECKING:
    from femora.core.model import Model


class ActionManager:
    """Create solver commands through ``model.actions``.

    Factories return action objects; they do not execute OpenSees or modify its
    current state. Add an action to ``model.process`` to place its command in
    the exported script. The process retains action objects strongly.

    Example:
        ```python
        from femora import Model

        model = Model()
        model.process.add_step(model.actions.load_const(), "Hold gravity")
        model.process.add_step(model.actions.set_time(0.0), "Reset clock")
        print(model.process.to_tcl())
        ```

    See Also:
        [ProcessManager][femora.core.process_manager.ProcessManager] orders
        commands. Concrete action classes are documented under Components.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "wipe",
            "wipe_analysis",
            "reset",
            "load_const",
            "exit",
            "remove_recorders",
            "set_time",
            "tcl",
            "set_material_parameter",
            "update_material_stage_to_elastic",
            "update_material_stage_to_plastic",
            "remove_load_patterns",
        ],
    }

    def __init__(self, mesh_maker: "Model") -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker

    def wipe(self) -> WipeAction:
        """Return an action emitting ``wipe`` to destroy the solver domain.

        This does not clear the Python Model. Use ``model.clear_model()`` for
        that operation; use this action only at an appropriate script position.
        """
        return WipeAction()

    def wipe_analysis(self) -> WipeAnalysisAction:
        """Return an action emitting ``wipeAnalysis``.

        The solver analysis configuration is discarded, not the model domain.
        This factory itself performs no solver operation.
        """
        return WipeAnalysisAction()

    def reset(self) -> ResetAction:
        """Return an action emitting the OpenSees ``reset`` command.

        This is a solver-domain operation, not a workflow checkpoint or a
        Python Model reset. The command runs only when the Tcl is executed.
        """
        return ResetAction()

    def load_const(self) -> LoadConstAction:
        """Return an action emitting ``loadConst`` without a time argument.

        Freeze existing solver load patterns at their current factors. This
        action does not reset time; append ``set_time(0.0)`` when needed.
        """
        return LoadConstAction()

    def exit(self) -> ExitAction:
        """Return an action emitting ``exit`` to terminate the solver script.

        Commands placed after it will not execute. Creating the action does
        not terminate Python or launch a solver.
        """
        return ExitAction()

    def remove_recorders(self) -> RemoveRecordersAction:
        """Return an action emitting ``remove recorders``.

        When executed, this closes active solver recorders. It does not delete
        output files or remove recorder definitions from the Python manager.
        """
        return RemoveRecordersAction()

    def set_time(self, pseudo_time: float) -> SetTimeAction:
        """Create a command setting the solver domain clock.

        Args:
            pseudo_time (float): New domain time, in the model's time units.

        Returns:
            SetTimeAction: Deferred ``setTime`` command. No analysis is advanced.
        """
        return SetTimeAction(pseudo_time)

    def tcl(self, command: str) -> TclAction:
        """Wrap custom Tcl for insertion into the process.

        Args:
            command (str): Tcl text, including any required arguments or lines.

        Returns:
            TclAction: Deferred command. Femora does not validate its Tcl syntax
            or ensure that it is safe or compatible with all MPI ranks.
        """
        return TclAction(command)

    def set_material_parameter(
        self,
        material: Union[int, str, Material],
        parameter_name: str,
        parameter_value: Union[float, int, str, None] = None,
        element_tags: Union[list[int], None] = None,
    ) -> SetMaterialParameterAction:
        """Create a deferred material-parameter update.

        Args:
            material (int | str | Material): Registered material tag, name, or object.
            parameter_name (str): Parameter supported by the target material.
            parameter_value (float | int | str | None): Optional parameter value.
            element_tags (list[int] | None): Explicit target element tags; when
                omitted, the action resolves affected elements from the model.

        Returns:
            SetMaterialParameterAction: Model-aware command object. Parameter
            support is ultimately determined by the solver material/element.
        """
        return SetMaterialParameterAction(
            self._mesh_maker,
            material,
            parameter_name,
            parameter_value,
            element_tags,
        )

    def update_material_stage_to_elastic(self) -> UpdateMaterialStageToElasticAction:
        """Create a model-aware action selecting elastic material stage zero.

        Intended for stage-capable soil materials during initialization, not
        as a conversion of arbitrary materials into elastic material models.
        """
        return UpdateMaterialStageToElasticAction(self._mesh_maker)

    def update_material_stage_to_plastic(self) -> UpdateMaterialStageToPlasticAction:
        """Create a model-aware action selecting plastic material stage one.

        Place after elastic initialization and before re-equilibration when
        required by the constitutive model. This does not equilibrate gravity.
        """
        return UpdateMaterialStageToPlasticAction(self._mesh_maker)

    def remove_load_patterns(self) -> RemoveLoadPatternsAction:
        """Create an action removing the model's load patterns in the solver.

        The action uses the owning Model to produce commands. It does not
        clear the Python pattern manager when this factory is called.
        """
        return RemoveLoadPatternsAction(self._mesh_maker)

    def clear(self) -> None:
        """No-op; actions are stateless factories."""
        return None
