# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union

from femora.core.recorder_base import Recorder
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.core.meshpart_base import MeshPart
    from femora.core.region_base import RegionBase
    from femora.core.group import ElementGroup
    from femora.components.interface.embedded_beam_solid_interface import EmbeddedBeamSolidInterface
    from femora.components.recorder.recorders import (
        NodeRecorder,
        DriftRecorder,
        VTKHDFRecorder,
        MPCORecorder,
        BeamForceRecorder,
        EmbeddedBeamSolidInterfaceRecorder,
    )


class RecorderManager:
    """Define solver output through ``model.recorder``.

    Factories register recorder objects. Add a recorder to ``model.process``
    before the analyses whose responses it should capture. Creation does not
    open response files or launch OpenSees. File naming, response vocabulary,
    output-folder integration, and solver-build support depend on the concrete
    recorder; VTKHDF and MPCO response names are not interchangeable.

    Example:
        ```python
        from femora import Model

        model = Model()
        recorder = model.recorder.vtkhdf(
            file_base_name="response.vtkhdf", resp_types=["disp", "vel", "accel"],
            delta_t=0.02,
        )
        model.process.add_step(recorder, "Begin response output")
        model.process.add_step(model.actions.remove_recorders(), "Close output")
        assert model.recorder.get(recorder.tag) is recorder
        ```

    Insert the actual analysis between those two process steps in a complete
    model. Recorder intervals control output sampling, not analysis time steps.
    Check acceleration basis and force-coordinate conventions before processing
    results. Rank-specific files are expected for distributed recorders.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "node",
            "drift",
            "vtkhdf",
            "mpco",
            "beam_force",
            "embedded_beam_solid_interface",
            "pile_mpco",
            "pile_vtkhdf",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "recorder", None)
        if isinstance(existing_manager, RecorderManager):
            raise ValueError("mesh_maker already owns a recorder manager")

        self._mesh_maker = mesh_maker
        mesh_maker.recorder = self
        self._recorders: Dict[int, Recorder] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Recorder]()

    def add(self, recorder: Recorder) -> Recorder:
        """Register a recorder and assign its model-local registry tag.

        Args:
            recorder (Recorder): Unmanaged object or one already owned here.

        Returns:
            recorder (Recorder): The same object, retained by this manager.

        Raises:
            TypeError: Input is not a Recorder.
            ValueError: Foreign ownership or conflicting registry tag.
        """
        if not isinstance(recorder, Recorder):
            raise TypeError("recorder must be a Recorder instance")
        if recorder._owner is None:
            recorder._owner = self
        elif recorder._owner is not self:
            raise ValueError("recorder already belongs to another manager")
        try:
            recorder.tag = self._tagging.assign_tag(self._recorders, recorder, self._start_tag)
        except ValueError as exc:
            raise ValueError(f"Recorder tag {recorder.tag} already exists") from exc
        self._recorders[recorder.tag] = recorder
        return recorder

    def node(
        self,
        *,
        dofs: list[int],
        resp_type: str,
        file_name: str | None = None,
        xml_file: str | None = None,
        binary_file: str | None = None,
        inet_addr: str | None = None,
        port: int | None = None,
        precision: int = 6,
        time_series: int | None = None,
        time: bool = False,
        delta_t: float | None = None,
        close_on_write: bool = False,
        nodes: list[int] | None = None,
        node_range: list[int] | tuple[int, int] | None = None,
        region: int | str | RegionBase | None = None,
        cores: int | list[int] | None = None,
    ) -> NodeRecorder:
        """Create a node recorder.

        Args:
            file_name: Optional file path for plain text output.
            xml_file: Optional file path for XML output.
            binary_file: Optional file path for binary output.
            inet_addr: Optional IP address for TCP output.
            port: Optional TCP port paired with inet_addr.
            precision: Number of significant digits (default: 6).
            time_series: Optional TimeSeries tag.
            time: If True, includes time in the first column.
            delta_t: Optional time step recording interval.
            close_on_write: If True, opens/closes the output file on each write.
            nodes: Optional list of node tags.
            node_range: Optional start and end tag `[start, end]`.
            region: Optional target region tag or name.
            dofs: List of active degrees of freedom (required).
            resp_type: Response type, e.g. `'disp'`, `'vel'`, `'accel'`, `'reaction'` (required).
            cores: Optional processor core ID(s) for MPI execution.

        Raises:
            ValueError: If output destination, node selection, DOFs, or response type
                validation fails.

        Returns:
            recorder (NodeRecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import NodeRecorder

        recorder = NodeRecorder(
            dofs=dofs,
            resp_type=resp_type,
            file_name=file_name,
            xml_file=xml_file,
            binary_file=binary_file,
            inet_addr=inet_addr,
            port=port,
            precision=precision,
            time_series=time_series,
            time=time,
            delta_t=delta_t,
            close_on_write=close_on_write,
            nodes=nodes,
            node_range=node_range,
            region=region,
            cores=cores,
        )
        self.add(recorder)
        return recorder

    def drift(
        self,
        *,
        file_name: str,
        i_nodes: list[int] | int,
        j_nodes: list[int] | int,
        dof: int,
        perp_dirn: int = 3,
        time: bool = False,
        delta_t: float | None = None,
        precision: int | None = None,
        cores: int | list[int] | None = None,
        core: int | None = None,
    ) -> DriftRecorder:
        """Create a drift recorder.

        Args:
            file_name: Output file name (required).
            i_nodes: List of bottom node tags (required).
            j_nodes: List of top node tags (required).
            dof: Target degree of freedom (1 to 6).
            perp_dirn: Perpendicular direction (1 to 3).
            time: If True, records simulation time.
            delta_t: Optional time step recording interval.
            precision: Optional number of significant digits.
            cores: Optional processor core ID(s) for MPI execution.
            core: Single-core compatibility alias used when ``cores`` is omitted.

        Raises:
            ValueError: If input validation fails.
            TypeError: If cores or node lists are invalid types.

        Returns:
            recorder (DriftRecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import DriftRecorder

        recorder = DriftRecorder(
            file_name=file_name,
            i_nodes=i_nodes,
            j_nodes=j_nodes,
            dof=dof,
            perp_dirn=perp_dirn,
            time=time,
            delta_t=delta_t,
            precision=precision,
            cores=cores,
            core=core,
        )
        self.add(recorder)
        return recorder

    def vtkhdf(
        self,
        *,
        file_base_name: str = "",
        resp_types: list[str] | None = None,
        delta_t: float | None = None,
        r_tol_dt: float | None = None,
        region: int | str | RegionBase | list[int | str | RegionBase] | None = None,
        regions: int | str | RegionBase | list[int | str | RegionBase] | None = None,
        group: ElementGroup | str | None = None,
        element_group: ElementGroup | str | None = None,
        cores: int | list[int] | None = None,
    ) -> VTKHDFRecorder:
        """Create a VTK HDF recorder.

        Args:
            file_base_name: Base name of the file to which output is sent (required).
            resp_types: Requested fields (required). Nodal fields are
                ``disp``, ``vel``, ``accel``. Element fields are
                ``force2D``, ``force3D``, ``localForce2D``, ``localForce3D``,
                ``stress2D3``, ``strain2D3``, ``stress3D6``, ``strain3D6``.
                Availability depends on the OpenSees recorder build and
                each element's implemented responses. Inspect the output
                datasets to confirm availability; some older binaries
                silently ignore force keywords. Continuum stress/strain
                fields are not substitutes for beam-fiber recorders.
            delta_t: Optional time interval for recording.
            r_tol_dt: Optional relative tolerance for time step matching.
            region: Optional region tag, name, or RegionBase instance used to restrict VTKHDF output to one region. If not specified, the entire model will be recorded.
            regions: Alias for ``region``; accepts one reference or a list.
                Do not combine it with ``region``.
            group: Optional ElementGroup or element group name used to restrict VTKHDF output.
            element_group: Alias for ``group``. Do not combine both names.
            cores: Optional processor core ID(s) for MPI execution.

        Raises:
            ValueError: If file_base_name or resp_types are not specified, or if
                invalid response types are supplied.

        Returns:
            recorder (VTKHDFRecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import VTKHDFRecorder

        if regions is not None and region is not None:
            raise ValueError("Use only one of region or regions")
        region = region if regions is None else regions
        if element_group is not None and group is not None:
            raise ValueError("Use only one of group or element_group")
        group = group if element_group is None else element_group
        selection = {}
        if region is not None:
            selection["region"] = region
        if group is not None:
            selection["group"] = group
        recorder = VTKHDFRecorder(
            file_base_name=file_base_name,
            resp_types=[] if resp_types is None else resp_types,
            delta_t=delta_t,
            r_tol_dt=r_tol_dt,
            cores=cores,
            **selection,
        )
        self.add(recorder)
        return recorder

    def mpco(
        self,
        *,
        file_name: str,
        node_responses: list[str] | None = None,
        element_responses: list[str] | None = None,
        node_sensitivities: list | None = None,
        regions: int | str | RegionBase | list[int | str | RegionBase] | None = None,
        groups: list[ElementGroup | str] | None = None,
        element_groups: list[ElementGroup | str] | None = None,
        delta_t: float | None = None,
        num_steps: int | None = None,
        cores: int | list[int] | None = None,
    ) -> MPCORecorder:
        """Create an MPCO recorder.

        Args:
            file_name: Output database file name (required).
            node_responses: Optional list of node response variables to record.
            element_responses: Optional list of element response variables.
            node_sensitivities: Optional list of node sensitivities.
            regions: Optional list of region tags or names to restrict recording to.
            groups: Optional list of ElementGroups or element group names used to restrict recording.
            element_groups: Alias for ``groups``. Do not combine both names.
            delta_t: Optional recording time step interval.
            num_steps: Optional recording step interval.
            cores: Optional processor core ID(s) for MPI execution.

        Raises:
            ValueError: If file_name is missing or parameters are conflicting.
            TypeError: If input parameter types are incorrect.

        Returns:
            recorder (MPCORecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import MPCORecorder

        if element_groups is not None and groups is not None:
            raise ValueError("Use only one of groups or element_groups")
        groups = groups if element_groups is None else element_groups
        recorder = MPCORecorder(
            file_name=file_name,
            node_responses=[] if node_responses is None else node_responses,
            element_responses=[] if element_responses is None else element_responses,
            node_sensitivities=[] if node_sensitivities is None else node_sensitivities,
            regions=[] if regions is None else regions,
            groups=[] if groups is None else groups,
            delta_t=delta_t,
            num_steps=num_steps,
            cores=cores,
        )
        self.add(recorder)
        return recorder

    def beam_force(
        self,
        *,
        meshparts: list[str | MeshPart] | None = None,
        force_type: str = "globalForce",
        file_prefix: str = "Beam",
        delta_t: float | None = None,
        include_time: bool = True,
        output_format: str = "file",
        precision: int | None = None,
        cores: int | list[int] | None = None,
    ) -> BeamForceRecorder:
        """Create a beam force recorder.

        Args:
            meshparts: Optional list of MeshPart identifiers (user_name strings
                or MeshPart instances). If omitted, all line mesh parts are used.
            force_type: Force system, either `'globalForce'` or `'localForce'`.
            file_prefix: Prefix for output files (default: `'Beam'`).
            delta_t: Optional time step recording interval.
            include_time: If True, includes time in columns (default: True).
            output_format: Output format, either `'file'`, `'xml'`, or `'binary'`.
            precision: Optional significant digits.
            cores: Optional processor core ID(s) for MPI execution.

        Raises:
            ValueError: If force_type or output_format are invalid.

        Returns:
            recorder (BeamForceRecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import BeamForceRecorder

        recorder = BeamForceRecorder(
            meshparts=[] if meshparts is None else meshparts,
            force_type=force_type,
            file_prefix=file_prefix,
            delta_t=delta_t,
            include_time=include_time,
            output_format=output_format,
            precision=precision,
            cores=cores,
        )
        self.add(recorder)
        return recorder

    def embedded_beam_solid_interface(
        self,
        *,
        interface: str | EmbeddedBeamSolidInterface | list[str | EmbeddedBeamSolidInterface],
        resp_type: str | list[str] | None = None,
        dt: float | None = None,
        cores: int | list[int] | None = None,
    ) -> EmbeddedBeamSolidInterfaceRecorder:
        """Create an embedded beam-solid interface recorder.

        Args:
            interface: The interface(s) to record. Can be an
                EmbeddedBeamSolidInterface instance, a string name, or a list
                of both.
            resp_type: The response type or list of response types to record.
            dt: Optional recording time step interval.
            cores: Optional processor core ID(s) for MPI execution.

        Raises:
            ValueError: If interface validation fails.
            TypeError: If resp_type is invalid.

        Returns:
            recorder (EmbeddedBeamSolidInterfaceRecorder): Registered definition; add it to model.process to activate output.
        """
        from femora.components.recorder.recorders import EmbeddedBeamSolidInterfaceRecorder

        options = {} if resp_type is None else {"resp_type": resp_type}
        recorder = EmbeddedBeamSolidInterfaceRecorder(
            interface=interface, dt=dt, cores=cores, **options
        )
        self.add(recorder)
        return recorder

    def get(self, tag: int) -> Optional[Recorder]:
        """Return a recorder by integer-convertible registry tag, or None.

        This lookup does not inspect output files or query active solver recorders.
        """
        return self._recorders.get(int(tag))

    def get_all(self) -> Dict[int, Recorder]:
        """Return a shallow registry snapshot with shared recorder objects."""
        return dict(self._recorders)

    def remove(self, tag: int) -> None:
        """Detach a definition and compact surviving registry tags.

        Args:
            tag (int): Current tag; absent entries are ignored.

        This does not close a running solver recorder, delete files, or remove
        references from the process. Use a process remove-recorders action for
        solver-side closure.
        """
        recorder = self._recorders.pop(int(tag), None)
        if recorder is not None:
            recorder.tag = None
            recorder._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach all recorder definitions without deleting response files.

        Existing process references are not rewritten, and running solver output
        is not stopped. This is a Python registry operation only.
        """
        for recorder in list(self._recorders.values()):
            recorder.tag = None
            recorder._owner = None
        self._recorders.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive recorder registry origin and retag definitions.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. This does not change partition IDs or
                rename existing output files.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._recorders, self._start_tag)

    def pile_mpco(
        self,
        meshparts: str | MeshPart | list[str | MeshPart] | tuple[str | MeshPart, ...],
        file_name: str,
        *,
        delta_t: Optional[float] = None,
        num_steps: Optional[int] = None,
        node_responses: Optional[List[str]] = None,
        element_responses: Optional[List[str]] = None,
        node_sensitivities: Optional[List] = None,
        line_cells_only: bool = True,
        region_name: str = "pile_mpco_region",
    ) -> MPCORecorder:
        """Register MPCO output restricted to selected assembled pile parts.

        Args:
            meshparts (str | MeshPart | Sequence): Part names/objects to select.
            file_name (str): MPCO output file base.
            delta_t (float | None): Output interval in model time units.
            num_steps (int | None): Step-based output control accepted by MPCORecorder.
            node_responses (list[str] | None): Defaults to displacement, velocity, acceleration.
            element_responses (list[str] | None): Defaults to force.
            node_sensitivities (list | None): Optional sensitivity requests.
            line_cells_only (bool): Restrict the group to recognized line cells.
            region_name (str): Preferred generated ElementGroup name.

        Returns:
            recorder (Recorder): Registered MPCORecorder with a generated element
                group and rank filter derived from selected cells' Core values.

        Raises:
            ValueError: Assembly, Core metadata, parts, or matching cells are missing.

        Rebuild the group/recorder if assembly changes. Creation adds a group but
        does not schedule output; add the returned recorder to the process.
        """
        from femora.components.recorder.recorders import MPCORecorder

        if node_responses is None:
            node_responses = ["displacement", "velocity", "acceleration"]
        if element_responses is None:
            element_responses = ["force"]

        pile_group, cores_arg = self._create_pile_element_group_for_meshparts(
            meshparts=meshparts,
            line_cells_only=line_cells_only,
            group_name=region_name,
            caller="pile_mpco",
        )

        component = MPCORecorder(
            file_name=file_name,
            node_responses=node_responses,
            element_responses=element_responses,
            node_sensitivities=node_sensitivities or [],
            element_groups=[pile_group],
            delta_t=delta_t,
            num_steps=num_steps,
            cores=cores_arg,
        )
        self.add(component)
        return component

    def pile_vtkhdf(
        self,
        meshparts: str | MeshPart | list[str | MeshPart] | tuple[str | MeshPart, ...],
        file_base_name: str,
        *,
        resp_types: Optional[List[str]] = None,
        delta_t: Optional[float] = None,
        r_tol_dt: Optional[float] = None,
        line_cells_only: bool = True,
        region_name: str = "pile_vtkhdf_region",
    ) -> VTKHDFRecorder:
        """Register VTKHDF output restricted to selected assembled pile parts.

        Args:
            meshparts (str | MeshPart | Sequence): Part names/objects to select.
            file_base_name (str): VTKHDF output base name.
            resp_types (list[str] | None): Defaults to disp, vel, accel, force3D,
                and localForce3D.
            delta_t (float | None): Output interval in model time units.
            r_tol_dt (float | None): Recorder sampling tolerance option.
            line_cells_only (bool): Restrict the generated group to line cells.
            region_name (str): Preferred generated ElementGroup name.

        Returns:
            recorder (Recorder): Registered VTKHDFRecorder with cell group and
                rank filter based on the current assembly.

        Raises:
            ValueError: Assembly, Core metadata, parts, or matching cells are missing.

        This selects beam/line piles, not automatically solid pile volumes when
        line_cells_only is True. Rebuild after changes in assembled cell order.
        """
        from femora.components.recorder.recorders import VTKHDFRecorder

        if resp_types is None:
            resp_types = ["disp", "vel", "accel", "force3D", "localForce3D"]

        pile_group, cores_arg = self._create_pile_element_group_for_meshparts(
            meshparts=meshparts,
            line_cells_only=line_cells_only,
            group_name=region_name,
            caller="pile_vtkhdf",
        )

        component = VTKHDFRecorder(
            file_base_name=file_base_name,
            resp_types=resp_types,
            delta_t=delta_t,
            r_tol_dt=r_tol_dt,
            element_group=pile_group,
            cores=cores_arg,
        )
        self.add(component)
        return component

    def _create_pile_element_group_for_meshparts(
        self,
        *,
        meshparts,
        line_cells_only: bool,
        group_name: str,
        caller: str,
    ):
        mm = self._mesh_maker
        mesh = self._mesh_maker.assembled_mesh
        if mesh is None:
            raise ValueError(f"{caller} requires an assembled mesh (call Assemble first).")

        cores_arr = mesh.cell_data.get("Core")
        if cores_arr is None:
            raise ValueError("Assembled mesh missing Core cell_data.")

        pile_group = mm.group.element.from_meshparts(
            name=group_name,
            meshparts=meshparts,
            line_cells_only=line_cells_only,
        )

        import numpy as np

        selected_cores = np.unique(cores_arr[pile_group.cell_indices])
        selected_cores = [
            int(c) for c in selected_cores if isinstance(c, (int, np.integer)) and int(c) >= 0
        ]
        cores_arg: Optional[Union[int, List[int]]] = None
        if selected_cores:
            cores_arg = selected_cores[0] if len(selected_cores) == 1 else selected_cores

        return pile_group, cores_arg


__all__ = ["RecorderManager"]
