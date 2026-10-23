# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, Optional

from femora.components.transformation.transformation import (
    GeometricTransformation2D,
    GeometricTransformation3D,
)
from femora.core.tagging import CompactRetagPolicy
from femora.core.transformation_base import GeometricTransformation

if TYPE_CHECKING:
    from femora.core.model import Model


class TransformationManager:
    """Define beam coordinate transformations through ``model.transformation``.

    Factories return registered transformation objects for beam-column element
    definitions. These are solver coordinate/kinematic definitions, not spatial
    transformations that move mesh points. The latter belong to
    ``model.spatial_transform``.

    Example:
        ```python
        from femora import Model

        model = Model()
        transform = model.transformation.transformation3d("Linear", 0, 0, 1)
        assert model.transformation.get(transform.tag) is transform
        assert transform.dimension == 3
        ```

    Note:
        Choose the 3D orientation vector with respect to the eventual beam axis;
        it must not be parallel to that axis. Creating a transformation alone
        cannot validate this against a beam mesh that does not yet exist.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "transformation2d",
            "transformation3d",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        """Create an empty transformation manager with tags starting at ``1``."""
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "transformation", None)
        if isinstance(existing_manager, TransformationManager):
            raise ValueError("mesh_maker already owns a transformation manager")
        self._mesh_maker = mesh_maker
        self._transformations: Dict[int, GeometricTransformation] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[GeometricTransformation]()

    def __len__(self) -> int:
        """Return the number of managed transformations."""
        return len(self._transformations)

    def __iter__(self) -> Iterator[GeometricTransformation]:
        """Iterate over managed transformations in tag order."""
        return iter(self._transformations.values())

    def add(self, transformation: GeometricTransformation) -> GeometricTransformation:
        """Add an existing transformation and assign a tag if needed.

        Args:
            transformation: Unmanaged or already-managed transformation.

        Returns:
            The same transformation after it is stored by this manager.
        """
        if not isinstance(transformation, GeometricTransformation):
            raise TypeError("transformation must be a GeometricTransformation instance")
        if transformation._owner is None:
            transformation._owner = self
        elif transformation._owner is not self:
            raise ValueError("transformation already belongs to another manager")

        try:
            transformation.tag = self._tagging.assign_tag(
                self._transformations,
                transformation,
                self._start_tag,
            )
        except ValueError as exc:
            raise ValueError(f"Transformation tag {transformation.tag} already exists") from exc
        self._transformations[transformation.tag] = transformation
        return transformation

    def get(self, tag: int) -> Optional[GeometricTransformation]:
        """Look up an integer registry tag, returning None when absent.

        Args:
            tag (int): Current tag, converted through ``int(tag)``. Conversion
                errors propagate; transformation names are not supported.
        """
        return self._transformations.get(int(tag))

    def get_all(self) -> Dict[int, GeometricTransformation]:
        """Return a shallow copy of all managed transformations keyed by tag."""
        return dict(self._transformations)

    def remove(self, tag: int) -> None:
        """Detach a transformation and compact surviving registry tags.

        Args:
            tag (int): Current integer tag; absent tags are ignored.

        Warning:
            Elements referencing the detached object are not repaired or removed.
            Cached integer tags can become stale after compaction.
        """
        transformation = self._transformations.pop(int(tag), None)
        if transformation is not None:
            transformation.tag = None
            transformation._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Detach all transformations and clear their tags, retaining elements.

        This edits Python definitions only. It neither deletes files nor emits
        solver commands. Rebuild dependent model definitions before exporting.
        """
        for transformation in self._transformations.values():
            transformation.tag = None
            transformation._owner = None
        self._transformations.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive registry origin and retag existing transformations.

        Args:
            start_tag (int): First tag validated by the tagging policy.

        Raises:
            ValueError: The origin is invalid. Existing object tags may change
                on success; stored integer references are not updated for you.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def transformation2d(
        self,
        transf_type: str,
        d_xi: float = 0.0,
        d_yi: float = 0.0,
        d_xj: float = 0.0,
        d_yj: float = 0.0,
        description: str = "",
    ) -> GeometricTransformation2D:
        """Create and register a planar beam coordinate transformation.

        Args:
            transf_type (str): Solver transformation type validated by the component.
            d_xi (float): Global x joint offset at end i, in length units.
            d_yi (float): Global y joint offset at end i.
            d_xj (float): Global x joint offset at end j.
            d_yj (float): Global y joint offset at end j.
            description (str): Optional Tcl comment text.

        Returns:
            transformation (GeometricTransformation2D): Registered definition
                ready for an appropriate beam element. Constructor errors propagate.
        """
        return self.add(
            GeometricTransformation2D(
                transf_type=transf_type,
                d_xi=d_xi,
                d_yi=d_yi,
                d_xj=d_xj,
                d_yj=d_yj,
                description=description,
            )
        )  # type: ignore[return-value]

    def transformation3d(
        self,
        transf_type: str,
        vecxz_x: float | str,
        vecxz_y: float | str,
        vecxz_z: float | str,
        d_xi: float | str = 0.0,
        d_yi: float | str = 0.0,
        d_zi: float | str = 0.0,
        d_xj: float | str = 0.0,
        d_yj: float | str = 0.0,
        d_zj: float | str = 0.0,
        description: str = "",
    ) -> GeometricTransformation3D:
        """Create and register a spatial beam coordinate transformation.

        Args:
            transf_type (str): Solver transformation type validated by the component.
            vecxz_x (float | str): Global x component of the local x-z plane vector.
            vecxz_y (float | str): Global y component of that vector.
            vecxz_z (float | str): Global z component of that vector.
            d_xi (float | str): Global x joint offset at end i, in length units.
            d_yi (float | str): Global y joint offset at end i.
            d_zi (float | str): Global z joint offset at end i.
            d_xj (float | str): Global x joint offset at end j.
            d_yj (float | str): Global y joint offset at end j.
            d_zj (float | str): Global z joint offset at end j.
            description (str): Optional Tcl comment text.

        Returns:
            transformation (GeometricTransformation3D): Registered definition.
                Numeric and string forms follow the concrete component's rules;
                this factory does not evaluate Tcl expressions or inspect mesh axes.
        """
        return self.add(
            GeometricTransformation3D(
                transf_type=transf_type,
                vecxz_x=vecxz_x,
                vecxz_y=vecxz_y,
                vecxz_z=vecxz_z,
                d_xi=d_xi,
                d_yi=d_yi,
                d_zi=d_zi,
                d_xj=d_xj,
                d_yj=d_yj,
                d_zj=d_zj,
                description=description,
            )
        )  # type: ignore[return-value]

    def _next_available_tag(self) -> int:
        """Return the next unused tag in this manager's local tag space."""
        return self._tagging.next_available_tag(self._transformations, self._start_tag)

    def _reassign_tags(self) -> None:
        """Retag all managed transformations from ``_start_tag`` in tag order."""
        self._tagging.reassign_tags(self._transformations, self._start_tag)


__all__ = [
    "TransformationManager",
    "GeometricTransformation",
    "GeometricTransformation2D",
    "GeometricTransformation3D",
]
