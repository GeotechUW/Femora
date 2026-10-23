# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import Optional
import warnings

import numpy as np

from femora.core.element_base import Element
from femora.core.meshpart_base import MeshPart


class LineMeshPart(MeshPart):
    """Extension base for concrete line mesh parts and line-mass bookkeeping.

    Normal construction goes through ``model.meshpart.line``. Subclasses inherit
    the MeshPart contract and share density resolution and rotational-mass
    helpers. This base does not itself generate a line mesh. Density and
    mass-per-length inputs are alternatives, not additive mass contributions.
    """

    __doc_controls__ = {"summary": True, "members": ["is_elemnt_compatible"]}

    _compatible_elements = ["DispBeamColumn", "ForceBeamColumn", "ElasticBeamColumn", "NonlinearBeamColumn"]

    def _resolve_density(
        self,
        *,
        density: Optional[float],
        mass_per_length: Optional[float],
    ) -> float:
        if density is not None and mass_per_length is not None:
            raise ValueError("Use either density or mass_per_length, not both")

        if density is None and mass_per_length is None:
            resolved_density = 0.0
        elif density is not None:
            resolved_density = float(density)
        else:
            area, _, _, _ = self._get_section_mass_properties()
            mpl = float(mass_per_length)
            if mpl < 0.0:
                raise ValueError("mass_per_length must be non-negative")
            warnings.warn(
                "'mass_per_length' on line meshparts is kept for compatibility and "
                "may be deprecated in the future. Prefer 'density'; Femora converts "
                "'mass_per_length' to density using the section area.",
                FutureWarning,
                stacklevel=3,
            )
            resolved_density = mpl / area

        if resolved_density < 0.0:
            raise ValueError("density must be non-negative")

        element_mass = float(self.element.get_mass_per_length())
        if resolved_density > 0.0 and element_mass > 0.0:
            warnings.warn(
                f"Line meshpart '{self.user_name}' has meshpart density and its element "
                f"also has massDens={element_mass}. Femora will export nodal mass "
                "from the meshpart and element -mass from the beam element. These "
                "masses are additive in OpenSees and may double-count inertia.",
                RuntimeWarning,
                stacklevel=3,
            )

        return resolved_density

    def _get_section_mass_properties(self) -> tuple[float, float, float, float]:
        section = getattr(self.element, '_section', None)
        if section is None:
            raise ValueError("Line meshpart mass requires the element to have a section")

        required = ("get_area", "get_Iy", "get_Iz")
        missing = [name for name in required if not hasattr(section, name)]
        if missing:
            raise ValueError(
                "Line meshpart mass requires section methods: "
                + ", ".join(required)
            )

        area = float(section.get_area())
        if area <= 0.0:
            raise ValueError("Line meshpart mass requires a positive section area")

        iy = float(section.get_Iy())
        iz = float(section.get_Iz())
        # Nodal rotational mass needs the polar mass moment of area, not the
        # section's OpenSees torsional stiffness/constant parameter.
        polar = iy + iz
        return area, iy, iz, polar

    def _line_rotational_mass(
        self,
        *,
        direction: np.ndarray,
        length: float,
        area: float,
        iy: float,
        iz: float,
        j: float,
    ) -> tuple[float, float, float]:
        m_rot = self.density * area * length / 2.0 * (length**2) / 4.0
        m_rx, m_ry, m_rz = m_rot, m_rot, m_rot

        m_rot_torsion = self.density * j * length / 2.0
        m_rot_iy = self.density * iy * length / 2.0
        m_rot_iz = self.density * iz * length / 2.0

        direction_norm = float(np.linalg.norm(direction))
        if direction_norm <= 0.0:
            return m_rx, m_ry, m_rz
        dir_norm = direction / direction_norm
        transf = getattr(self.element, '_transformation', None)
        if transf and hasattr(transf, 'vecxz_x'):
            x_axis = dir_norm
            vecxz = np.array([transf.vecxz_x, transf.vecxz_y, transf.vecxz_z], dtype=float)
            vecxz_norm = np.linalg.norm(vecxz)
            vecxz = vecxz / vecxz_norm if vecxz_norm > 1e-12 else np.array([0.0, 0.0, 1.0])

            y_axis = np.cross(vecxz, x_axis)
            y_axis_norm = np.linalg.norm(y_axis)
            y_axis = y_axis / y_axis_norm if y_axis_norm > 1e-12 else np.array([0.0, 1.0, 0.0])

            z_axis = np.cross(x_axis, y_axis)
            z_axis_norm = np.linalg.norm(z_axis)
            z_axis = z_axis / z_axis_norm if z_axis_norm > 1e-12 else np.array([0.0, 0.0, 1.0])

            m_rx = (x_axis[0]**2)*m_rot_torsion + (y_axis[0]**2)*m_rot_iy + (z_axis[0]**2)*m_rot_iz
            m_ry = (x_axis[1]**2)*m_rot_torsion + (y_axis[1]**2)*m_rot_iy + (z_axis[1]**2)*m_rot_iz
            m_rz = (x_axis[2]**2)*m_rot_torsion + (y_axis[2]**2)*m_rot_iy + (z_axis[2]**2)*m_rot_iz
        else:
            if abs(dir_norm[2]) >= max(abs(dir_norm[0]), abs(dir_norm[1])):
                m_rx, m_ry, m_rz = m_rot_iz, m_rot_iy, m_rot_torsion
            elif abs(dir_norm[0]) >= max(abs(dir_norm[1]), abs(dir_norm[2])):
                m_rx, m_ry, m_rz = m_rot_torsion, m_rot_iy, m_rot_iz
            else:
                m_rx, m_ry, m_rz = m_rot_iy, m_rot_torsion, m_rot_iz

        return m_rx, m_ry, m_rz

    @classmethod
    def is_elemnt_compatible(cls, element: str) -> bool:
        """Test a type name against the line family's case-insensitive allowlist.

        Args:
            element (str): Element formulation name, not an element object or tag.

        Returns:
            compatible (bool): Membership in the supported type-name list.
                Material compatibility and geometric validity are not tested.
        """
        return element.lower() in [elem.lower() for elem in cls._compatible_elements]


__all__ = ["LineMeshPart"]
