# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""---
title: Visualization
icon: material/movie-open-outline
---

Create movies from existing recorder output with
[DeformationRenderer][femora.results.visualization.deformation.DeformationRenderer].
No solver is launched. Start with ResultSet.deformation_renderer(), configure
deformation, colors, and camera, then call write() while the result files are open.
The Results & Postprocessing overview contains a complete minimal movie example.
"""

from .deformation import DeformationRenderer

__all__ = ["DeformationRenderer"]
