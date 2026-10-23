# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Exceptions raised by the Femora results API."""


class ResultError(RuntimeError):
    """Base exception for result access and post-processing failures."""

    __doc_controls__ = {"members": []}


class UnsupportedResultOperation(ResultError):
    """A reader capability or a required structural response is unavailable.

    Check available_point_responses/available_cell_responses and the original
    recorder configuration. Postprocessing cannot recover an unrecorded field.
    Plain missing-field reader queries may instead raise KeyError.
    """

    __doc_controls__ = {"members": []}


class ResultFormatError(ResultError):
    """Recorded layout, partition copies, or structural identities are inconsistent.

    Check that files belong to the same completed run and that building metadata
    comes from the same assembled model. Building history queries also raise
    this exception for NaN/infinity; generic raw reader queries do not perform
    an automatic finite-value check.
    """

    __doc_controls__ = {"members": []}
