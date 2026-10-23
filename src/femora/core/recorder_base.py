# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Union

from femora.core.region_base import RegionBase


class Recorder(ABC):
    """Base class for OpenSees recorder commands.

    Recorder instances do not self-register. A :class:`RecorderManager` owns tag
    assignment and lifecycle for a single model context.

    Args:
        recorder_type (str): Concrete recorder type label.
        cores (int | list[int] | None): Optional MPI process IDs on which the
            generated Tcl command is enabled. None emits it without a rank guard.

    Subclasses implement ``_to_tcl_impl``. That hook renders recorder-specific
    syntax; the public ``to_tcl`` method adds a rank guard where requested.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    def __init__(
        self,
        recorder_type: str,
        cores: Optional[Union[int, List[int]]] = None,
    ) -> None:
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None
        self.recorder_type = recorder_type
        self.cores = cores

    @abstractmethod
    def _to_tcl_impl(self) -> str:
        pass

    def to_tcl(self) -> str:
        """Render the recorder command, optionally guarded by solver ``$pid``.

        Returns:
            command (str): Concrete Tcl, wrapped in a process-ID condition when
                cores is supplied. The execution environment must define ``pid``.

        Rendering does not open output files or allocate MPI ranks. Concrete
        implementation errors, including unresolved selections, propagate.
        """
        cmd = self._to_tcl_impl()
        if self.cores is not None:
            if isinstance(self.cores, int):
                core_list = [self.cores]
            else:
                core_list = self.cores
            if len(core_list) == 1:
                condition = f"$pid == {core_list[0]}"
            else:
                condition = f"$pid in {{{' '.join(map(str, core_list))}}}"
            indented_cmd = "\n".join(["\t" + line for line in cmd.split("\n")])
            return f"if {{{condition}}} {{\n{indented_cmd}\n}}"
        return cmd

    def _mesh_maker(self):
        if self._owner is not None:
            return getattr(self._owner, "_mesh_maker", None)
        return None

    def _resolve_regions(
        self,
        regions_input: Union[int, str, RegionBase, List[Union[int, str, RegionBase]]],
    ) -> List[int]:
        if regions_input is None:
            return []

        def resolve_one(item) -> int:
            if isinstance(item, int):
                return item
            if isinstance(item, RegionBase):
                if item.tag is None:
                    raise ValueError("RegionBase instance has no tag assigned")
                return item.tag
            if isinstance(item, str):
                mesh_maker = self._mesh_maker()
                if mesh_maker is None:
                    raise ValueError(
                        f"Cannot resolve region name '{item}' without a manager-owned recorder"
                    )
                for tag, region in mesh_maker.region.get_all().items():
                    if getattr(region, "name", None) == item:
                        return tag
                raise ValueError(f"Region with name '{item}' not found")
            raise TypeError("regions must contain ints, names, or RegionBase instances")

        tags: List[int] = []
        if isinstance(regions_input, (list, tuple)):
            for it in regions_input:
                tag = resolve_one(it)
                if tag not in tags:
                    tags.append(tag)
        else:
            tags = [resolve_one(regions_input)]
        return tags


__all__ = ["Recorder"]
