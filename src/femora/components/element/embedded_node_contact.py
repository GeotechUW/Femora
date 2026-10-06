# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

import math
from typing import List

from femora.core.element_base import Element


class EmbeddedNodeContact3D(Element):
    """Frictional contact between a node and a host tetrahedron.

    The constrained node is followed by the four nodes of the tetrahedron that
    contains it. The contact normal can be supplied per constrained node, which
    allows an interface builder to orient contact around a curved surface.
    """

    def __init__(
        self,
        ndof: int,
        Kn: float,
        Kt: float,
        mu: float,
        orient: list[float] | tuple[float, float, float] | None = None,
        orient_map: dict[int, list[float]] | None = None,
        int_type: int = 0,
        **kwargs,
    ) -> None:
        if ndof not in (3, 4, 6):
            raise ValueError("EmbeddedNodeContact3D requires 3, 4, or 6 DOFs")
        if not math.isfinite(Kn) or Kn <= 0.0:
            raise ValueError("Kn must be a positive finite number")
        if not math.isfinite(Kt) or Kt <= 0.0:
            raise ValueError("Kt must be a positive finite number")
        if not math.isfinite(mu) or mu < 0.0:
            raise ValueError("mu must be a non-negative finite number")
        if int_type not in (0, 1):
            raise ValueError("int_type must be 0 (implicit) or 1 (IMPL-EX)")

        self.Kn = float(Kn)
        self.Kt = float(Kt)
        self.mu = float(mu)
        self.orient = self._validate_orientation(orient) if orient is not None else None
        self.orient_map = {
            int(node): self._validate_orientation(direction)
            for node, direction in (orient_map or {}).items()
        }
        self.int_type = int(int_type)
        super().__init__("EmbeddedNodeContact", ndof, material=None, **kwargs)

    @staticmethod
    def _validate_orientation(direction) -> tuple[float, float, float]:
        if not isinstance(direction, (list, tuple)) or len(direction) != 3:
            raise ValueError("orient must contain three components")
        values = tuple(float(value) for value in direction)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("orient components must be finite")
        if math.sqrt(sum(value * value for value in values)) <= 1.0e-12:
            raise ValueError("orient cannot be the zero vector")
        return values

    def to_tcl(self, tag: int, nodes: List[int]) -> str:
        if len(nodes) != 5:
            raise ValueError(
                "EmbeddedNodeContact3D requires 5 nodes "
                "(1 constrained node and 4 retained nodes)"
            )

        command = (
            f"element EmbeddedNodeContact {tag} "
            f"{' '.join(str(node) for node in nodes)} "
            f"{self.Kn} {self.Kt} {self.mu}"
        )
        direction = self.orient_map.get(nodes[0], self.orient)
        if direction is not None:
            command += f" -orient {direction[0]} {direction[1]} {direction[2]}"
        command += f" -intType {self.int_type}"
        return command

