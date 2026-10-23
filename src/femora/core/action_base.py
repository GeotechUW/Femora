# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod


class Action(ABC):
    """Extension contract for a deferred Tcl command in a model process.

    Ordinary scripts should use ``model.actions``. Subclass this base when
    implementing a reusable command not covered by those factories; implement
    ``to_tcl()`` without launching the solver. ProcessManager retains actions
    directly rather than through a manager-owned weak reference.
    """

    __doc_controls__ = {"summary": True, "members": ["to_tcl"]}

    @abstractmethod
    def to_tcl(self) -> str:
        """Return the Tcl text inserted at this action's process position.

        Returns:
            str: Command text, potentially containing multiple lines. Rendering
            a command must not be confused with executing its solver effects.
        """
        raise NotImplementedError("Subclasses must implement the 'to_tcl' method.")
