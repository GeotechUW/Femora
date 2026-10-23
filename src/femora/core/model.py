# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import numpy as np

if TYPE_CHECKING:
    import pyvista as pv

from femora.core.material_manager import MaterialManager
from femora.core.element_base import Element
from femora.core.element_manager import ElementManager
from femora.core.ground_motion_manager import GroundMotionManager
from femora.core.assembler import Assembler
from femora.core.damping_manager import DampingManager
from femora.core.region_manager import RegionManager
from femora.core.constraint_manager import ConstraintManager
from femora.core.load_manager import LoadManager
from femora.core.meshpart_manager import MeshPartManager
from femora.components.mesh import *
from femora.core.time_series_manager import TimeSeriesManager
from femora.core.analysis_manager import AnalysisManager
from femora.core.pattern_manager import PatternManager
from femora.core.recorder_manager import RecorderManager
from femora.core.process_manager import ProcessManager
from femora.core.transformation_manager import TransformationManager
from femora.core.interface_base import InterfaceManager
from femora.core.section_manager import SectionManager
from femora.core.mass_manager import MassManager
from femora.components.geometry_ops.spatial_transform_manager import SpatialTransformManager
from femora.core.mask_manager import MaskManager
from femora.core.action_manager import ActionManager
from femora.core.event_bus import ModelEventBus
from femora.core.part_registry import FemoraPart, FemoraPartRegistry
from femora.core.group import GroupManager


class Model:
    """
    Own a model's definitions, mesh parts, assembly, and exported solver process.

    Each Model creates its own managers. Create definitions through those
    managers, assign them to mesh parts, assemble the parts, and export a solver
    script. Model construction and export do not launch OpenSees.

    Args:
        model_name (str | None): Default export basename, or None to require
            explicit filenames.
        model_path (str | None): Default export directory. Unknown configuration
            keywords are rejected instead of silently ignored.

    Attributes:
        assembled_mesh: Combined mesh after assembly, or None before assembly
            and after ``clear_model()``. Export and downstream operations use it.
        material: Material registry with ``nd`` and ``uniaxial`` factories.
        section: Beam, shell, fiber, and other section factories.
        transformation: Coordinate-transformation definitions for elements.
        element: Beam, brick, quad, and special element definitions.
        meshpart: Factories and registry for discretized component meshes.
        assembler: Section creation, mesh combination, and partitioning.
        interface: Connections between separate model components.
        constraint: Single-point and multipoint constraints through ``sp`` and ``mp``.
        mass: Nodal mass assignment helpers.
        damping: Damping definitions.
        region: Region definitions and damping association.
        group: Node and element selection groups.
        mask: Model selection masks.
        time_series: Loading time-function definitions.
        ground_motion: Ground-motion definitions referencing time series.
        load: Load definitions used by patterns.
        pattern: Load-pattern definitions.
        recorder: Solver response-output definitions.
        actions: Deferred solver commands.
        analysis: Static/transient analyses and solution-stack factories.
        process: Ordered solver operations included in the exported Tcl.
        events: Model-owned lifecycle notification bus.
        spatial_transform: Spatial mesh transformation service.

    Example:
        ```python
        from femora import Model

        model = Model(model_name="site", model_path="example_outputs/site")
        soil = model.material.nd.elastic_isotropic(
            user_name="soil", E=108000.0, nu=1.0 / 3.0, rho=1.8,
        )
        model.set_results_folder("results")
        assert model.material.get_by_name("soil") is soil
        assert model.assembled_mesh is None
        ```

    Note:
        Femora does not convert units. Choose a consistent system for geometry,
        material stiffness, density, loads, and time. A Model is not a Jobs
        Workflow and its process is not a remote execution scheduler.
    """

    __doc_controls__ = {
        "summary": True,
        "show_docstring_attributes": True,
        "members": [
            "set_model_info",
            "set_results_folder",
            "get_results_folder",
            "export_to_tcl",
            "export_to_vtk",
            "export_to_json",
            "print_info",
            "set_nodetag_start",
            "set_eletag_start",
            "set_start_core_tag",
            "get_max_ele_tag",
            "get_max_node_tag",
            "get_start_ele_tag",
            "get_start_node_tag",
            "get_femora_parts",
            "clear_model",
        ],
    }

    def __init__(self, *, model_name: str | None = None, model_path: str | None = None) -> None:
        """
        Initialize a Femora Model instance.

        Args:
            model_name: Name used for default exported filenames.
            model_path: Directory used for default exports.
        """
        self.model = None
        # Primary public assembled-mesh path for runtime, export, and downstream consumers.
        self.assembled_mesh: pv.UnstructuredGrid | None = None
        self.events = ModelEventBus()
        self._part_registry = FemoraPartRegistry()
        self.model_name = model_name
        self.model_path = model_path
        self._results_folder = ""
        self.material = MaterialManager(mesh_maker=self)
        self.element = ElementManager(mesh_maker=self)
        self.time_series = TimeSeriesManager(mesh_maker=self)
        self.ground_motion = GroundMotionManager(
            mesh_maker=self, time_series_manager=self.time_series
        )
        self.damping = DampingManager(mesh_maker=self)
        self.mass = MassManager(mesh_maker=self)
        self.region = RegionManager(mesh_maker=self)
        self.constraint = ConstraintManager(mesh_maker=self)
        self.load = LoadManager(mesh_maker=self)
        self.meshpart = MeshPartManager(mesh_maker=self)
        self.assembler = Assembler(mesh_maker=self)
        self.analysis = AnalysisManager(mesh_maker=self)
        self.pattern = PatternManager(
            mesh_maker=self,
            time_series_manager=self.time_series,
            ground_motion_manager=self.ground_motion,
        )
        self.group = GroupManager(mesh_maker=self)
        self.recorder = RecorderManager(mesh_maker=self)
        self.interface = InterfaceManager(mesh_maker=self)
        self.transformation = TransformationManager(mesh_maker=self)
        self.section = SectionManager(mesh_maker=self)
        self.actions = ActionManager(mesh_maker=self)
        self.mask = MaskManager(mesh_maker=self)
        self.spatial_transform = SpatialTransformManager()
        self.process = ProcessManager(mesh_maker=self)

        # Tag start controls for node and element IDs written to TCL
        # These control only exported OpenSees node/element tags (not Material/Element class tags)
        self._start_nodetag: int = 1
        self._start_ele_tag: int = 1
        self._start_core_tag: int = 0

        self._register_model_event_subscribers()

    def _register_model_event_subscribers(self) -> None:
        self.mass.register_events()
        self.mask.register_events()

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    def set_nodetag_start(self, start_tag: int) -> None:
        """
        Set the starting tag number for nodes in exported TCL.

        Args:
            start_tag (int): First node tag to use (must be >= 1)
        """
        if not isinstance(start_tag, int) or start_tag < 1:
            raise ValueError("Node tag start must be an integer >= 1")
        self._start_nodetag = start_tag

    def set_eletag_start(self, start_tag: int) -> None:
        """
        Set the starting tag number for elements in exported TCL.

        Args:
            start_tag (int): First element tag to use (must be >= 1)
        """
        if not isinstance(start_tag, int) or start_tag < 1:
            raise ValueError("Element tag start must be an integer >= 1")
        self._start_ele_tag = start_tag

    def set_start_core_tag(self, start_tag: int) -> None:
        """
        Set the starting tag number for cores in exported TCL.

        Args:
            start_tag (int): First core tag to use (must be >= 0)
        """
        if not isinstance(start_tag, int) or start_tag < 0:
            raise ValueError("Core tag start must be an integer >= 0")
        self._start_core_tag = start_tag

    def export_to_tcl(
        self,
        filename: str | None = None,
        progress_callback: Callable[..., None] | None = None,
        decimals: int = 5,
    ) -> bool:
        """
        Export the model to a TCL file

        Args:
            filename (str, optional): The filename to export to. If None,
                                     uses model_name in model_path
            progress_callback (callable, optional): Callback function to report progress.
                                                  If None, uses tqdm progress bar.
            decimals (int): Coordinate precision passed to the Tcl exporter.

        Returns:
            success (bool): True on success. Export/filesystem failures raise
                exceptions rather than returning False.

        Raises:
            ValueError: If no filename is provided and model_name/model_path are not set
        """
        from femora.io.export_tcl import export_to_tcl as _export_to_tcl

        return _export_to_tcl(
            self,
            filename=filename,
            progress_callback=progress_callback,
            decimals=decimals,
        )

    def export_to_vtk(
        self,
        filename: str | None = None,
        write_info_json: bool = False,
        indent: int = 2,
    ) -> bool:
        """
        Export the model to a vtk file

        Args:
            filename (str, optional): The filename to export to. If None,
                                    uses model_name in model_path
            write_info_json (bool, optional): When True, also write a
                                    lightweight sidecar JSON file.
            indent (int, optional): JSON indentation level for sidecar info.

        Returns:
            success (bool): True on success. Missing assembly and write errors
                raise exceptions rather than returning False.
        """
        from femora.io.export_vtk import export_to_vtk as _export_to_vtk

        return _export_to_vtk(
            self,
            filename=filename,
            write_info_json=write_info_json,
            indent=indent,
        )

    def export_to_json(self, filename: str | None = None, indent: int = 2) -> bool:
        """
        Export a lightweight structural snapshot of the model to JSON.

        Args:
            filename (str, optional): The filename to export to. If None,
                                    uses model_name in model_path
            indent (int, optional): JSON indentation level. Defaults to 2.

        Returns:
            success (bool): True if export was successful
        """
        from femora.io.export_json import export_to_json as _export_to_json

        return _export_to_json(self, filename=filename, indent=indent)

    def set_model_info(self, model_name: str | None = None, model_path: str | None = None) -> None:
        """
        Update model information

        Args:
            model_name (str, optional): New model name
            model_path (str, optional): New model path
        """
        if model_name is not None:
            self.model_name = model_name
        if model_path is not None:
            self.model_path = model_path

    def set_results_folder(self, folder_name: str) -> None:
        """
        Store the output-folder setting used during recorder/export generation.

        This setter stores the supplied value as-is. It does not create the
        directory, inspect permissions, or change Python's working directory.
        Relative paths are interpreted by the generated solver commands in
        their execution environment, not resolved by this setter.

        Args:
            folder_name (str): path to the results folder
        """
        self._results_folder = folder_name

    def get_results_folder(self) -> str:
        """
        Get the current results folder path

        Returns:
            folder (str): The path to the results folder
        """
        return self._results_folder if self._results_folder else ""

    def get_femora_parts(self) -> list[dict]:
        """Return a detached metadata snapshot of registered source parts.

        Returns:
            list[dict]: Source-part records used by VTK export. This is not a
            mesh-part registry or a replacement for ``model.meshpart.get_all()``.
        """
        return self._part_registry.get_all()

    def _register_femora_part(
        self,
        *,
        kind: str,
        name: str,
        source_tag: int | None = None,
    ) -> FemoraPart:
        return self._part_registry.get_or_create(
            kind=kind,
            name=name,
            source_tag=source_tag,
        )

    def _assign_femora_part_data(
        self,
        mesh,
        *,
        kind: str,
        name: str,
        source_tag: int | None = None,
    ) -> FemoraPart:
        part = self._register_femora_part(
            kind=kind,
            name=name,
            source_tag=source_tag,
        )
        mesh.cell_data["FemoraPartTag"] = np.full(mesh.n_cells, part.tag, dtype=np.int32)
        mesh.cell_data["FemoraPartKind"] = np.full(mesh.n_cells, part.kind_id, dtype=np.int16)
        return part

    def print_info(self) -> None:
        """Print final-mesh point/cell counts, or 'No mesh found'.

        This writes to stdout and returns None. It does not inspect convergence
        or validate the physical model.
        """

        if self.assembled_mesh is None:
            print("No mesh found")
        else:
            numpoints = self.assembled_mesh.n_points
            numcells = self.assembled_mesh.n_cells
            print(f"Number of nodes: {numpoints}")
            print(f"Number of elements: {numcells}")

    def get_max_ele_tag(self) -> int:
        """Compute the last sequential export element tag from the cell count.

        Returns:
            tag (int): Start tag plus cell count minus one, or -1 without assembly.
                This does not inspect arbitrary imported cell tags.
        """

        max_ele_tag = self.assembler.get_num_cells()

        if max_ele_tag < 0:
            return -1
        return max_ele_tag + self._start_ele_tag - 1

    def get_max_node_tag(self) -> int:
        """Compute the last sequential export node tag from the point count.

        Returns:
            tag (int): Start tag plus point count minus one, or -1 without assembly.
                This is not the number of free solver equations.
        """

        max_node_tag = self.assembler.get_num_points()

        if max_node_tag < 0:
            return -1
        return max_node_tag + self._start_nodetag - 1

    def get_start_ele_tag(self) -> int:
        """Return the first exported solver element tag.

        Returns:
            tag (int): Export origin, independent of element-definition registry tags.
        """
        return self._start_ele_tag

    def get_start_node_tag(self) -> int:
        """Return the first exported solver node tag.

        Returns:
            tag (int): Origin used when mapping zero-based assembled point indices.
        """
        return self._start_nodetag

    def clear_model(self) -> None:
        """
        Clear model definitions, assembled meshes, and ordered process steps.

        Managers are retained but emptied, export tag starts reset to their
        defaults, and built-in lifecycle subscriptions are re-established.
        Custom event subscriptions are removed. Model name, model path, and the
        results-folder setting are retained.

        This is destructive to the in-memory model. It does not delete exported
        files or results, stop a running solver, or emit a solver ``wipe``.
        Previously held component references may be detached or stale; rebuild
        definitions through the model's managers before assembling again.
        """
        self.model = None
        self.mass.unregister_events()
        self.mask.unregister_events()
        self.mask.clear()
        self.events.clear()
        self._part_registry.clear()
        self.assembled_mesh = None
        self.assembler.reset()
        self.material.clear()
        self.element.clear()
        self.damping.clear()
        self.damping.set_tag_start(1)
        self.mass.clear()
        self.region.clear()
        self.constraint.clear()
        self.constraint.set_tag_start(1)
        self.load.clear()
        self.load.set_tag_start(1)
        self.meshpart.clear()
        self.meshpart.set_tag_start(1)
        self.time_series.clear()
        self.ground_motion.clear()
        self.analysis.clear()
        self.pattern.clear()
        self.group.clear()
        self.recorder.clear()
        self.recorder.set_tag_start(1)
        self.process.clear()
        self.interface.clear()
        self.transformation.clear()
        self.section.clear()
        self.spatial_transform.clear()
        self.actions.clear()
        self.time_series.set_tag_start(1)
        self.ground_motion.set_tag_start(1)
        self.pattern.set_tag_start(1)
        self.transformation.set_tag_start(1)
        self.material.set_tag_start(1)
        self.section.set_tag_start(1)
        self.region.set_tag_start(1)
        self._start_nodetag = 1
        self._start_ele_tag = 1
        self._start_core_tag = 0
        self._register_model_event_subscribers()
