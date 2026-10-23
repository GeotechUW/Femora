# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""---
title: File Readers
icon: material/file-table-outline
---

Built-in recorder-format readers. Most users should call
[open_results()][femora.results.result_set.open_results], which selects a reader
from the file suffix. Use [VTKHDFResultReader][femora.results.readers.vtkhdf.VTKHDFResultReader]
directly when working with a single partition's frame arrays or writing a
format-specific tool. Reader indices are local mesh indices, not OpenSees tags.
"""

from .vtkhdf import VTKHDFResultReader

__all__ = ["VTKHDFResultReader"]
