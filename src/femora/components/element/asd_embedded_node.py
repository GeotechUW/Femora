# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from typing import List, Optional

from femora.core.element_base import Element


class ASDEmbeddedNodeElement3D(Element):
    """Embedded-node constraint element for 3D solid domains.

    This element constrains one embedded node to a domain defined by four
    retained nodes forming a tetrahedral interpolation patch. It is intended for
    3D embedded-node coupling and is typically used together with the
    EmbeddedNode interface workflow in Femora.

    Tcl form:
        ``element ASDEmbeddedNodeElement <eleTag> <Cnode> <Rnode1> <Rnode2> <Rnode3> <Rnode4> [-rot] [-p] [-K K] [-KP KP]``

    Warning:
        This element is specialized for 3D embedded-node coupling and can be
        difficult to use correctly outside the intended interface workflow.

    Note:
        - Requires five nodes at export: one constrained node followed by four
          retained nodes.
        - Frictional contact is modeled by the separate
          ``EmbeddedNodeContact`` element.

    Attributes:
        rot: Whether rotational DOFs at the constrained node are constrained.
        p: Whether pressure DOFs are constrained.
        K: Optional penalty stiffness for displacement constraints.
        KP: Optional penalty stiffness for pressure constraints.

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        ele = model.element.special.asd_embedded_node(
            ndof=6,
            rot=True,
        )
        print(ele.tag)
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(
        self,
        ndof: int,
        rot: bool = False,
        p: bool = False,
        K: Optional[float] = None,
        KP: Optional[float] = None,
        **kwargs,
    ):
        """Create an ASDEmbeddedNodeElement3D with validated constraint options.

        Args:
            ndof: Number of DOFs per node. Must be 3, 4, or 6.
            rot: Whether to constrain rotational DOFs at the embedded node.
            p: Whether to constrain pressure DOFs.
            K: Optional user-defined penalty stiffness for displacement
                constraints.
            KP: Optional user-defined penalty stiffness for pressure
                constraints.
            **kwargs: Additional element parameters stored on the base element.

        Raises:
            ValueError: If ``ndof`` is unsupported.
        """
        if ndof not in [3, 4, 6]:
            raise ValueError(f"ASDEmbeddedNodeElement3D requires 3, 4, or 6 DOFs, but got {ndof}")

        contact_options = {
            "contact", "Kn", "Kt", "mu", "orient", "orient_map", "int_type"
        } & kwargs.keys()
        if contact_options:
            names = ", ".join(sorted(contact_options))
            raise TypeError(
                f"ASDEmbeddedNodeElement does not support contact options: {names}; "
                "use EmbeddedNodeContact instead"
            )

        self.rot = bool(rot)
        self.p = bool(p)
        self.K = float(K) if K is not None else None
        self.KP = float(KP) if KP is not None else None

        super().__init__("ASDEmbeddedNodeElement", ndof, material=None, **kwargs)

    def to_tcl(self, tag: int, nodes: List[int]) -> str:
        """Render the element as an OpenSees Tcl command.

        Args:
            tag: Assigned element tag.
            nodes: Five node tags ``[Cnode, Rnode1, Rnode2, Rnode3, Rnode4]``.

        Returns:
            str: Tcl ``element ASDEmbeddedNodeElement`` command for this element.

        Raises:
            ValueError: If ``nodes`` does not contain exactly five node tags.
        """
        if len(nodes) != 5:
            raise ValueError("ASDEmbeddedNodeElement3D requires 5 nodes (1 constrained, 4 retained)")

        nodes_str = " ".join(str(node) for node in nodes)
        cmd = f"element ASDEmbeddedNodeElement {tag} {nodes_str}"

        if self.rot:
            cmd += " -rot"
        if self.p:
            cmd += " -p"
        if self.K is not None:
            cmd += f" -K {self.K}"
        if self.KP is not None:
            cmd += f" -KP {self.KP}"

        return cmd
