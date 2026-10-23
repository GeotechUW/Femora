# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Union

if TYPE_CHECKING:
    from femora.core.time_series_manager import TimeSeriesManager

from femora.components.ground_motion.interpolated_ground_motion import InterpolatedGroundMotion
from femora.components.ground_motion.plain_ground_motion import PlainGroundMotion
from femora.core.ground_motion_base import GroundMotion
from femora.core.tagging import CompactRetagPolicy
from femora.core.time_series_base import TimeSeries

if TYPE_CHECKING:
    from femora.core.model import Model


class GroundMotionManager:
    """Manager for a local collection of ground motions.

    The manager is responsible for ground-motion lifecycle and numbering:
    adding instances, assigning tags, looking up objects, deleting objects, and
    retagging after removals or tag-start changes. It is intentionally not a
    singleton. Each ``GroundMotionManager`` instance owns an independent tag
    space, which allows future model or ``Model`` instances to keep local
    ground-motion collections.

    Concrete ground-motion classes validate and render themselves, while this
    manager controls ownership. Prefer factory methods such as ``plain(...)``
    and ``interpolated(...)`` for normal use; use ``add(...)`` when an instance
    has already been constructed manually.

    Use ``model.ground_motion``. Time-series dependencies must be registered
    with the same Model; interpolated motions must reference motions owned by
    this manager. A ground-motion object is not a UniformExcitation pattern:
    use it with the imposed-motion operations of a MultipleSupport pattern.
    Deleting dependencies or retagging them does not repair a running solver.

    Example:
        ```python
        from femora.core.model import Model

        model = Model()
        accel = model.time_series.path(dt=0.01, values=[0.0, 1.0, 0.0])
        disp = model.time_series.path(dt=0.01, values=[0.0, 0.001, 0.0])

        gm = model.ground_motion.plain(accel=accel, disp=disp)
        print(gm.tag)      # 1
        print(gm.to_tcl()) # groundMotion 1 Plain -accel ... -disp ...
        ```
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "plain",
            "interpolated",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(
        self, mesh_maker: Model, time_series_manager: "TimeSeriesManager | None" = None
    ) -> None:
        """Create an empty ground-motion manager with tags starting at 1."""
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._ground_motions: Dict[int, GroundMotion] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[GroundMotion]()
        self._time_series_manager = time_series_manager

    def __len__(self) -> int:
        """Return the number of managed ground motions."""
        return len(self._ground_motions)

    def __iter__(self) -> Iterator[GroundMotion]:
        """Iterate over managed ground motions in tag order."""
        return iter(self._ground_motions.values())

    def add(self, ground_motion: GroundMotion) -> GroundMotion:
        """Add a ground motion instance and assign its local tag.

        Args:
            ground_motion: Unmanaged ``GroundMotion`` instance to store.

        Returns:
            The same ground-motion instance, now tagged and managed.

        Raises:
            TypeError: If ``ground_motion`` is not a ``GroundMotion``.
            ValueError: If ``ground_motion`` belongs to another manager or its
                preassigned tag conflicts with another object managed here.
        """
        if not isinstance(ground_motion, GroundMotion):
            raise TypeError("ground_motion must be a GroundMotion instance")
        if ground_motion._owner is None:
            ground_motion._owner = self
        elif ground_motion._owner is not self:
            raise ValueError("ground_motion already belongs to another manager")

        self._validate_dependencies(ground_motion)

        try:
            ground_motion.tag = self._tagging.assign_tag(
                self._ground_motions,
                ground_motion,
                self._start_tag,
            )
        except ValueError as exc:
            raise ValueError(f"GroundMotion tag {ground_motion.tag} already exists") from exc
        self._ground_motions[ground_motion.tag] = ground_motion
        return ground_motion

    def plain(
        self,
        accel: Optional[TimeSeries] = None,
        vel: Optional[TimeSeries] = None,
        disp: Optional[TimeSeries] = None,
        integrator: Optional[str] = None,
        integrator_args: Optional[List[Union[int, float, str]]] = None,
        factor: float = 1.0,
    ) -> PlainGroundMotion:
        """Create, tag, and store a ``PlainGroundMotion``.

        Args:
            accel: Acceleration time series. Optional if ``vel`` or ``disp`` is
                provided.
            vel: Velocity time series. Optional if ``accel`` or ``disp`` is
                provided.
            disp: Displacement time series. Optional if ``accel`` or ``vel`` is
                provided.
            integrator: Optional OpenSees integration method, such as
                ``"Trapezoidal"`` or ``"Simpson"``.
            integrator_args: Optional arguments appended after ``integrator`` in
                the ``-int`` option.
            factor: Constant scale factor for the ground motion.

        Returns:
            The managed ``PlainGroundMotion`` instance.
        """
        ground_motion = PlainGroundMotion(
            accel=accel,
            vel=vel,
            disp=disp,
            integrator=integrator,
            integrator_args=integrator_args,
            factor=factor,
        )
        self.add(ground_motion)
        return ground_motion

    def interpolated(
        self,
        ground_motions: List[GroundMotion],
        factors: List[float],
    ) -> InterpolatedGroundMotion:
        """Create, tag, and store an ``InterpolatedGroundMotion``.

        Args:
            ground_motions: Ground motions to combine. Each item must be a
                ``GroundMotion`` instance.
            factors: Interpolation factors. Must have the same length as
                ``ground_motions``.

        Returns:
            The managed ``InterpolatedGroundMotion`` instance.
        """
        ground_motion = InterpolatedGroundMotion(
            ground_motions=ground_motions,
            factors=factors,
        )
        self.add(ground_motion)
        return ground_motion

    def get(self, tag: int) -> GroundMotion:
        """Return a managed ground motion by tag.

        Args:
            tag: Ground-motion tag in this manager's local tag space.

        Raises:
            KeyError: If no ground motion exists with ``tag``.
        """
        tag = int(tag)
        if tag not in self._ground_motions:
            raise KeyError(f"No ground motion found with tag {tag}")
        return self._ground_motions[tag]

    def get_all(self) -> Dict[int, GroundMotion]:
        """Return a copy of all managed ground motions keyed by tag."""
        return self._ground_motions.copy()

    def remove(self, tag: int) -> None:
        """Remove a ground motion and retag remaining instances.

        Args:
            tag: Ground-motion tag to remove. Missing tags are ignored.
        """
        tag = int(tag)
        if tag in self._ground_motions:
            removed = self._ground_motions.pop(tag)
            removed.tag = None
            removed._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Remove all ground motions and clear their assigned tags."""
        for ground_motion in self._ground_motions.values():
            ground_motion.tag = None
            ground_motion._owner = None
        self._ground_motions.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the first tag and retag existing ground motions.

        Args:
            start_tag: First tag to use for this manager. Must be positive.

        Raises:
            ValueError: If ``start_tag`` is less than 1.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _next_available_tag(self) -> int:
        """Return the next unused tag in this manager's local tag space."""
        return self._tagging.next_available_tag(self._ground_motions, self._start_tag)

    def _reassign_tags(self) -> None:
        """Retag all managed ground motions from ``_start_tag`` in tag order."""
        self._tagging.reassign_tags(self._ground_motions, self._start_tag)

    def _validate_dependencies(self, ground_motion: GroundMotion) -> None:
        """Ensure a ground motion only references local managed dependencies."""
        for time_series in (
            getattr(ground_motion, "accel", None),
            getattr(ground_motion, "vel", None),
            getattr(ground_motion, "disp", None),
        ):
            if time_series is None:
                continue
            if time_series.tag is None or time_series._owner is None:
                raise ValueError("GroundMotion references an unmanaged TimeSeries")
            owner_manager = time_series._owner
            owner_mesh_maker = getattr(owner_manager, "_mesh_maker", None)
            if owner_mesh_maker is not self._mesh_maker:
                raise ValueError("GroundMotion references a TimeSeries from another Model")
            if (
                self._time_series_manager is not None
                and owner_manager is not self._time_series_manager
            ):
                raise ValueError("GroundMotion references a TimeSeries from another manager")

        for dependency in getattr(ground_motion, "ground_motions", []):
            if dependency.tag is None or dependency._owner is None:
                raise ValueError("GroundMotion references an unmanaged GroundMotion")
            owner_manager = dependency._owner
            owner_mesh_maker = getattr(owner_manager, "_mesh_maker", None)
            if owner_mesh_maker is not self._mesh_maker:
                raise ValueError("GroundMotion references a GroundMotion from another Model")
            if owner_manager is not self:
                raise ValueError("GroundMotion references a GroundMotion from another manager")


__all__ = [
    "GroundMotion",
    "GroundMotionManager",
    "PlainGroundMotion",
    "InterpolatedGroundMotion",
]
