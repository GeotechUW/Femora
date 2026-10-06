import pytest

from femora.components.element import EmbeddedNodeContact3D


def test_embedded_node_contact_renders_custom_command():
    element = EmbeddedNodeContact3D(
        ndof=3,
        Kn=1.0e8,
        Kt=2.0e8,
        mu=0.5,
        orient_map={10: [0.0, 1.0, 0.0]},
        int_type=1,
    )

    assert element.to_tcl(20, [10, 11, 12, 13, 14]) == (
        "element EmbeddedNodeContact 20 10 11 12 13 14 "
        "100000000.0 200000000.0 0.5 -orient 0.0 1.0 0.0 -intType 1"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"Kn": 0.0}, "Kn"),
        ({"Kt": -1.0}, "Kt"),
        ({"mu": -0.1}, "mu"),
        ({"int_type": 2}, "int_type"),
        ({"orient": [0.0, 0.0, 0.0]}, "zero vector"),
    ],
)
def test_embedded_node_contact_rejects_invalid_parameters(kwargs, message):
    parameters = {"ndof": 3, "Kn": 1.0, "Kt": 1.0, "mu": 0.5}
    parameters.update(kwargs)

    with pytest.raises(ValueError, match=message):
        EmbeddedNodeContact3D(**parameters)


def test_embedded_node_contact_requires_tetrahedron_nodes():
    element = EmbeddedNodeContact3D(ndof=3, Kn=1.0, Kt=1.0, mu=0.5)

    with pytest.raises(ValueError, match="requires 5 nodes"):
        element.to_tcl(1, [1, 2, 3, 4])
