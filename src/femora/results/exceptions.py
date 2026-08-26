# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Exceptions raised by the Femora results API."""


class ResultError(RuntimeError):
    """Base exception for result access and post-processing failures."""


class UnsupportedResultOperation(ResultError):
    """Raised when a result format does not provide a requested capability."""


class ResultFormatError(ResultError):
    """Raised when a result file is missing required or consistent data."""

