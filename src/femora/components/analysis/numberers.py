# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from femora.core.analysis.numberer import Numberer


class PlainNumberer(Numberer):
    """Plain degree-of-freedom (DOF) numberer.

    PlainNumberer assigns equation numbers to nodes in the order they were
    defined in the model input, without any optimization.

    Tcl form:
        ``numberer Plain``

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        numberer = model.analysis.numberer.plain()
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(self) -> None:
        """Create a Plain degree-of-freedom numberer."""
        super().__init__()

    def to_tcl(self) -> str:
        """Render this numberer as an OpenSees Tcl command.

        Returns:
            The Tcl command string.
        """
        return "numberer Plain"


class RCMNumberer(Numberer):
    """Reverse Cuthill-McKee (RCM) degree-of-freedom numberer.

    RCMNumberer uses the Reverse Cuthill-McKee algorithm to optimize nodal numbering,
    reducing the bandwidth of the system equations and accelerating solver time.

    Tcl form:
        ``numberer RCM``

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        numberer = model.analysis.numberer.rcm()
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(self) -> None:
        """Create an RCM degree-of-freedom numberer."""
        super().__init__()

    def to_tcl(self) -> str:
        """Render this numberer as an OpenSees Tcl command.

        Returns:
            The Tcl command string.
        """
        return "numberer RCM"


class AMDNumberer(Numberer):
    """Approximate Minimum Degree (AMD) degree-of-freedom numberer.

    AMDNumberer uses the Approximate Minimum Degree ordering algorithm to minimize
    fill-in of the sparse system stiffness matrix.

    Tcl form:
        ``numberer AMD``

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        numberer = model.analysis.numberer.amd()
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(self) -> None:
        """Create an AMD degree-of-freedom numberer."""
        super().__init__()

    def to_tcl(self) -> str:
        """Render this numberer as an OpenSees Tcl command.

        Returns:
            The Tcl command string.
        """
        return "numberer AMD"


class ParallelRCMNumberer(Numberer):
    """Parallel Reverse Cuthill-McKee degree-of-freedom numberer.

    ParallelRCMNumberer is the parallel version of the RCM node numbering algorithm,
    suited for multi-processor simulations.

    Tcl form:
        ``numberer ParallelRCM``

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        numberer = model.analysis.numberer.parallelrcm()
        ```
    """

    __doc_controls__ = {
        "show_docstring_attributes": True,
        "members": ["__init__"],
    }

    def __init__(self) -> None:
        """Create a ParallelRCM degree-of-freedom numberer."""
        super().__init__()

    def to_tcl(self) -> str:
        """Render this numberer as an OpenSees Tcl command.

        Returns:
            The Tcl command string.
        """
        return "numberer ParallelRCM"


class ParallelPlainNumberer(Numberer):
    """Parallel plain numbering (``numberer ParallelPlain``)."""

    def __init__(self) -> None:
        super().__init__()

    def to_tcl(self) -> str:
        return "numberer ParallelPlain"


Numberer.register_numberer("plain", PlainNumberer)
Numberer.register_numberer("rcm", RCMNumberer)
Numberer.register_numberer("amd", AMDNumberer)
Numberer.register_numberer("parallelrcm", ParallelRCMNumberer)
Numberer.register_numberer("parallelplain", ParallelPlainNumberer)
