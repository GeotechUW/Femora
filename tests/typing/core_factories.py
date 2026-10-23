"""Static-only editor contracts; no kernel or model execution is required."""

from typing import TYPE_CHECKING
from typing_extensions import assert_type

from femora import Model

if TYPE_CHECKING:
    from femora.components.analysis.numberers import ParallelRCMNumberer
    from femora.components.analysis.algorithms import ModifiedNewtonAlgorithm
    from femora.components.analysis.integrators import NewmarkIntegrator
    from femora.components.constraint.sp_constraints import FixConstraint
    from femora.components.element.disp_beam_column import DispBeamColumnElement
    from femora.components.element.std_brick import stdBrickElement
    from femora.components.interface.embedded_node_interface import EmbeddedNodeInterface
    from femora.components.load.node_load import NodeLoad
    from femora.components.material.nd.elastic_isotropic import ElasticIsotropicMaterial
    from femora.components.mesh.volume_meshparts import StructuredRectangular3D
    from femora.components.recorder.recorders import VTKHDFRecorder
    from femora.components.region.regions import ElementRegion
    from femora.components.section.beam.elastic import ElasticSection


def check(model: Model) -> None:
    assert_type(model.analysis.numberer.parallelrcm(), ParallelRCMNumberer)
    soil = model.material.nd.elastic_isotropic(user_name="soil", E=1e5, nu=0.3, rho=1.8)
    assert_type(soil, ElasticIsotropicMaterial)
    assert_type(model.element.brick.std(ndof=3, material=soil, lumped=True), stdBrickElement)
    assert_type(model.analysis.algorithm.modifiednewton(factor_once=True), ModifiedNewtonAlgorithm)
    assert_type(model.analysis.integrator.newmark(gamma=0.5, beta=0.25), NewmarkIntegrator)
    section = model.section.beam.elastic(user_name="beam", E=200e6, A=0.01, Iz=1e-4)
    assert_type(section, ElasticSection)
    transformation = model.transformation.transformation2d("Linear")
    assert_type(model.element.beam.disp(3, section, transformation), DispBeamColumnElement)
    brick = model.element.brick.std(3, soil.tag if soil.tag is not None else 1)
    assert_type(
        model.meshpart.volume.uniform_rectangular_grid(
            "soil",
            brick,
            x_min=0,
            x_max=1,
            y_min=0,
            y_max=1,
            z_min=-1,
            z_max=0,
            nx=1,
            ny=1,
            nz=1,
        ),
        StructuredRectangular3D,
    )
    assert_type(model.region.element(user_name="soil"), ElementRegion)
    assert_type(model.constraint.sp.fix(1, [1, 1, 1]), FixConstraint)
    assert_type(model.load.node(node_tag=1, values=[0.0, 0.0, -10.0]), NodeLoad)
    assert_type(
        model.recorder.vtkhdf(file_base_name="response", resp_types=["disp"]), VTKHDFRecorder
    )
    assert_type(model.recorder.pile_vtkhdf(["pile"], "piles"), VTKHDFRecorder)
    assert_type(
        model.interface.node_interface(name="cap", constrained_node="frame"), EmbeddedNodeInterface
    )
