"""Calls that static analysis must reject; this file is never executed."""

from femora import Model


def check(model: Model) -> None:
    model.analysis.algorithm.modifiednewton(factor_onse=True)
    model.analysis.integrator.newmark(gamma=0.5, beta="wrong")
    model.material.nd.elastic_isotropic(E=1e5, nu=0.3, density_typo=1.8)
    model.recorder.vtkhdf(file_base_name="response", resp_types=["disp"], misspelled=True)
    model.section.beam.elastic(E=200e6, A=0.01, Iz=1e-4, unsupported=True)
    model.load.node(node_tag=1, values=[0.0, 0.0, -10.0], unsupported=True)
