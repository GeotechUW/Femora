# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

import pytest

from femora.components.analysis.analysis import Analysis
from femora.core.model import Model
from femora.core.analysis_manager import AnalysisManager


@pytest.fixture
def mesh_maker():
    mk = Model()
    mk.clear_model()
    return mk


def _build_transient_stack(am: AnalysisManager):
    handler = am.constraint.plain()
    numberer = am.numberer.parallelrcm()
    system = am.system.bandgeneral()
    algorithm = am.algorithm.newton()
    test = am.test.normunbalance(tol=1e-6, max_iter=25)
    integrator = am.integrator.newmark(gamma=0.5, beta=0.25)
    return handler, numberer, system, algorithm, test, integrator


def test_analysis_manager_model_owned(mesh_maker):
    assert isinstance(mesh_maker.analysis, AnalysisManager)
    assert mesh_maker.analysis._mesh_maker is mesh_maker


def test_duplicate_analysis_manager_rejected(mesh_maker):
    with pytest.raises(ValueError, match="already owns an analysis manager"):
        AnalysisManager(mesh_maker)


def test_components_are_manager_scoped(mesh_maker):
    am = mesh_maker.analysis
    system = am.system.bandgeneral()
    assert system.tag == 1
    assert system._owner is am.system


def test_unmanaged_analysis_has_no_tag(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)
    analysis = Analysis(
        "raw",
        "Transient",
        handler,
        numberer,
        system,
        algorithm,
        test,
        integrator,
        num_steps=5,
        dt=0.01,
    )
    assert analysis.tag is None
    assert analysis._owner is None


def test_add_analysis_tags_and_tcl(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)
    analysis = am.add(
        Analysis(
            "TransientRun",
            "Transient",
            handler,
            numberer,
            system,
            algorithm,
            test,
            integrator,
            num_steps=10,
            dt=0.01,
        )
    )
    assert analysis.tag == 1
    assert analysis._owner is am
    tcl = analysis.to_tcl()
    assert "analysis Transient" in tcl
    assert "constraints Plain" in tcl
    assert tcl.index("test NormUnbalance") < tcl.index("algorithm Newton")
    assert "while {$Ok != 0 && $FemoraRetry < 10}" in tcl
    assert "FemoraAnalyzeTransientStep 0.01 0" in tcl
    assert "FEMORA_PROGRESS|START|TransientRun|$FemoraAnalysisTotal" in tcl
    assert "if {$Ok != 0}" in tcl
    assert "FEMORA_PROGRESS|UPDATE|TransientRun" in tcl
    assert "wipeAnalysis" in tcl


def test_transient_analysis_supports_linear_dt_ramp(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)

    analysis = am.transient(
        name="RampedTransient",
        constraint_handler=handler,
        numberer=numberer,
        system=system,
        algorithm=algorithm,
        test=test,
        integrator=integrator,
        num_steps=10,
        dt_min=0.001,
        dt_max=0.1,
    )

    tcl = analysis.to_tcl()
    assert "set dt_min 0.001" in tcl
    assert "set dt_max 0.1" in tcl
    assert "double($AnalysisStep)/($numSteps-1)*($dt_max-$dt_min)" in tcl
    assert "set Ok [FemoraAnalyzeTransientStep $dt 0]" in tcl


def test_transient_analysis_exports_optional_substep_recovery(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)

    analysis = am.transient(
        name="RecoveringTransient",
        constraint_handler=handler,
        numberer=numberer,
        system=system,
        algorithm=algorithm,
        test=test,
        integrator=integrator,
        num_steps=2,
        dt=0.01,
        max_retries=3,
        num_sublevels=2,
        num_substeps=4,
    )

    tcl = analysis.to_tcl()
    assert "while {$Ok != 0 && $FemoraRetry < 3}" in tcl
    assert "if {$level >= 2}" in tcl
    assert "$dt / double(4)" in tcl
    assert "$FemoraSubstep < 4" in tcl


def test_final_time_analysis_reports_physical_time(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)

    analysis = am.transient(
        name="TimeBasedTransient",
        constraint_handler=handler,
        numberer=numberer,
        system=system,
        algorithm=algorithm,
        test=test,
        integrator=integrator,
        final_time=4.0,
        dt=0.01,
    )

    tcl = analysis.to_tcl()
    assert "FEMORA_PROGRESS|START|TimeBasedTransient|4.0|s|[getTime]" in tcl
    assert "FEMORA_PROGRESS|UPDATE|TimeBasedTransient|[getTime]|4.0|s" in tcl


def test_transient_dt_ramp_requires_complete_range(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)

    with pytest.raises(ValueError, match="both dt_min and dt_max"):
        am.transient(
            name="BadRamp",
            constraint_handler=handler,
            numberer=numberer,
            system=system,
            algorithm=algorithm,
            test=test,
            integrator=integrator,
            num_steps=10,
            dt_min=0.001,
        )


def test_transient_dt_ramp_rejects_dt_ambiguity(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)

    with pytest.raises(ValueError, match="either dt or dt_min/dt_max"):
        am.transient(
            name="AmbiguousRamp",
            constraint_handler=handler,
            numberer=numberer,
            system=system,
            algorithm=algorithm,
            test=test,
            integrator=integrator,
            dt=0.01,
            num_steps=10,
            dt_min=0.001,
            dt_max=0.1,
        )


def test_direct_submanager_api(mesh_maker):
    am = mesh_maker.analysis
    assert "Plain" in am.constraint.plain().to_tcl()
    assert "ParallelRCM" in am.numberer.parallelrcm().to_tcl()
    assert "Mumps" in am.system.mumps(icntl14=10).to_tcl()
    assert "ModifiedNewton" in am.algorithm.modifiednewton(factor_once=True).to_tcl()
    assert "EnergyIncr" in am.test.energyincr(tol=1e-3, max_iter=5).to_tcl()
    assert "Newmark" in am.integrator.newmark(gamma=0.6, beta=0.3).to_tcl()


def test_clear_model_resets_analysis(mesh_maker):
    am = mesh_maker.analysis
    handler, numberer, system, algorithm, test, integrator = _build_transient_stack(am)
    am.add(
        Analysis(
            "a",
            "Transient",
            handler,
            numberer,
            system,
            algorithm,
            test,
            integrator,
            num_steps=1,
            dt=0.01,
        )
    )
    am.system.mumps()
    assert len(am.get_all()) == 1
    assert len(am.system.get_all()) >= 1
    mesh_maker.clear_model()
    assert len(mesh_maker.analysis.get_all()) == 0
    assert len(mesh_maker.analysis.system.get_all()) == 0


def test_submanager_clear(mesh_maker):
    am = mesh_maker.analysis
    am.algorithm.newton()
    am.clear()
    assert len(am.algorithm.get_all()) == 0
    assert len(am.get_all()) == 0
