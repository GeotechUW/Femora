"""---
icon: material/vector-triangle
---

Element component package for Femora.

This package contains runtime finite-element definitions that are created
through [ElementManager][femora.core.element_manager.ElementManager] and
exported to OpenSees Tcl as ``element`` commands. Components are grouped into
beam, brick, quadrilateral, and special-purpose families.

Normal runtime usage should go through a [Model][femora.core.model.Model]
instance and its element manager entry points, such as
``model.element.beam.*``, ``model.element.brick.*``, ``model.element.quad.*``,
and ``model.element.special.*``.
"""

from femora.core.element_base import Element
from .ssp_brick import SSPbrickElement
from .ssp_quad import SSPQuadElement
from .std_brick import stdBrickElement
from .pml_3d import PML3DElement
from .asd_embedded_node import ASDEmbeddedNodeElement3D
from .embedded_node_contact import EmbeddedNodeContact3D
from .zero_length_contact import ZeroLengthContactASDimplex
from .disp_beam_column import DispBeamColumnElement
from .force_beam_column import ForceBeamColumnElement
from .elastic_beam_column import ElasticBeamColumnElement
from .ghost_node import GhostNodeElement
from .truss import TrussElement
