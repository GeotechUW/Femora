# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class SPConstraint(ABC):
    """Extension contract for a single-point solver constraint.

    Args:
        node_tag (int): Solver node tag, not a PyVista point index.
        dofs (list[int]): Concrete constraint's fixity/DOF data.

    The base stores references without validating solver nodes. Register a
    concrete constraint through ``model.constraint.sp`` to obtain model ownership.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    def __init__(self, node_tag: int, dofs: List[int]) -> None:
        self.node_tag = node_tag
        self.dofs = dofs
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None

    @abstractmethod
    def to_tcl(self) -> str:
        """Render the concrete SP command without executing it.

        Returns:
            command (str): Tcl supplied by the subclass. Node existence and
                solver enforcement are not established by rendering alone.
        """
        raise NotImplementedError


class MPConstraint(ABC):
    """Extension contract for retained/constrained-node kinematic coupling.

    Args:
        master_node (int): Retained solver node tag.
        slave_nodes (list[int]): Constrained solver node tags.

    The base stores node references, not geometric searches or solver equations.
    Concrete subclasses define DOFs and Tcl syntax; register them through the
    model's MP constraint manager.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    def __init__(self, master_node: int, slave_nodes: List[int]) -> None:
        self.master_node = master_node
        self.slave_nodes = slave_nodes
        self.tag: Optional[int] = None
        self._owner: Optional[object] = None

    @abstractmethod
    def to_tcl(self) -> str:
        """Render the concrete MP coupling command or command sequence.

        Returns:
            command (str): Subclass-generated Tcl. A compatible analysis
                constraint handler must still enforce it in the solver.
        """
        raise NotImplementedError


__all__ = ["SPConstraint", "MPConstraint"]
