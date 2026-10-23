# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Sequence

if TYPE_CHECKING:
    from femora.core.ground_motion_manager import GroundMotionManager
    from femora.core.time_series_manager import TimeSeriesManager

from femora.components.pattern.h5drm_pattern import H5DRMPattern
from femora.components.pattern.multiple_support import MultipleSupportPattern
from femora.components.pattern.plain_pattern import PlainPattern
from femora.components.pattern.uniform_excitation import UniformExcitation
from femora.core.pattern_base import Pattern
from femora.core.tagging import CompactRetagPolicy
from femora.core.time_series_base import TimeSeries

if TYPE_CHECKING:
    from femora.core.model import Model


class PatternManager:
    """Local manager for ``Pattern`` lifecycle and tag assignment.

    The manager is intentionally not a singleton. Each instance owns an
    independent pattern tag space for one model context.

    Use ``model.pattern`` to register a loading definition, then add the pattern
    to ``model.process`` at the point where it should become active in Tcl.
    Registration alone does not schedule activation. Time-series and imposed
    motion dependencies must belong to this Model.

    Example:
        ```python
        from femora import Model

        model = Model()
        series = model.time_series.constant()
        gravity = model.pattern.plain(series)
        gravity.add_load.node(node_tag=1, values=[0.0, 0.0, -10.0])
        model.process.add_step(gravity, "Apply gravity")
        assert model.pattern.get(gravity.tag) is gravity
        ```

    This defines loading only, not a stable/solvable domain. Uniform excitation,
    imposed support motions, and DRM have different physical conventions; do
    not interchange their recorded acceleration interpretations. Consult each
    concrete pattern and recorder before adding ground motion in postprocessing.

    Removing/clearing a pattern edits Python registration, not the active solver.
    Use an appropriate process action for solver-side load-pattern removal.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "plain",
            "uniform_excitation",
            "multiple_support",
            "h5drm",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(
        self,
        mesh_maker: Model,
        time_series_manager: "TimeSeriesManager | None" = None,
        ground_motion_manager: "GroundMotionManager | None" = None,
    ) -> None:
        """Create an empty manager with pattern tags starting at ``1``."""
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._patterns: Dict[int, Pattern] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Pattern]()
        self._time_series_manager = time_series_manager
        self._ground_motion_manager = ground_motion_manager

    def add(self, pattern: Pattern) -> Pattern:
        """Add an existing pattern and assign a tag if needed.

        Args:
            pattern: Unmanaged or already-managed ``Pattern`` instance.

        Returns:
            The same ``pattern`` instance after it is stored by this manager.

        Raises:
            TypeError: If ``pattern`` is not a ``Pattern`` instance.
            ValueError: If its preassigned tag conflicts with a different
                object already managed here.
        """
        if not isinstance(pattern, Pattern):
            raise TypeError("pattern must be a Pattern instance")
        if pattern._owner is None:
            pattern._owner = self
        elif pattern._owner is not self:
            raise ValueError("pattern already belongs to another manager")
        self._validate_dependencies(pattern)
        try:
            pattern.tag = self._tagging.assign_tag(
                self._patterns,
                pattern,
                self._start_tag,
            )
        except ValueError as exc:
            raise ValueError(f"Pattern tag {pattern.tag} already exists") from exc
        self._patterns[pattern.tag] = pattern
        self._sync_attached_load_tags(pattern)
        return pattern

    def get(self, tag: int) -> Optional[Pattern]:
        """Return the pattern with ``tag`` if it exists.

        Args:
            tag: Pattern tag to look up.

        Returns:
            The matching ``Pattern`` instance, or ``None``.
        """
        return self._patterns.get(tag)

    def get_all(self) -> Dict[int, Pattern]:
        """Return a shallow copy of all managed patterns keyed by tag."""
        return dict(self._patterns)

    def remove(self, tag: int) -> None:
        """Remove a managed pattern and compact the remaining tags.

        Args:
            tag: Tag of the pattern to remove. Missing tags are ignored.
        """
        pattern = self._patterns.pop(tag, None)
        if pattern is not None:
            pattern.tag = None
            pattern._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Remove all patterns and clear their assigned tags."""
        for pattern in self._patterns.values():
            pattern.tag = None
            pattern._owner = None
        self._patterns.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the first tag used by this manager and retag existing patterns.

        Args:
            start_tag: Positive integer for the first assigned pattern tag.

        Raises:
            ValueError: If ``start_tag`` is less than ``1``.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def uniform_excitation(
        self,
        dof: int,
        time_series: TimeSeries,
        vel0: float = 0.0,
        factor: float = 1.0,
    ) -> UniformExcitation:
        """Create and manage a ``UniformExcitation`` pattern.

        Args:
            dof: 1-based DOF direction for the uniform excitation.
            time_series: Managed acceleration ``TimeSeries``.
            vel0: Initial velocity.
            factor: Scale factor applied to the time series.

        Returns:
            Managed ``UniformExcitation`` instance.
        """
        return self.add(UniformExcitation(dof, time_series, vel0, factor))  # type: ignore[return-value]

    def h5drm(
        self,
        filepath: str,
        factor: float,
        crd_scale: float,
        distance_tolerance: float,
        do_coordinate_transformation: int,
        transform_matrix: Optional[Sequence[float]] = None,
        origin: Optional[Sequence[float]] = None,
        *,
        T00: float | None = None,
        T01: float | None = None,
        T02: float | None = None,
        T10: float | None = None,
        T11: float | None = None,
        T12: float | None = None,
        T20: float | None = None,
        T21: float | None = None,
        T22: float | None = None,
        x00: float | None = None,
        x01: float | None = None,
        x02: float | None = None,
    ) -> H5DRMPattern:
        """Create and manage an ``H5DRMPattern``.

        Args:
            filepath: Path to the H5DRM dataset file.
            factor: Scale factor for DRM forces and displacements.
            crd_scale: Coordinate scale factor for the DRM dataset.
            distance_tolerance: Node matching tolerance.
            do_coordinate_transformation: ``0`` or ``1`` flag for coordinate
                transformation.
            transform_matrix: Optional 9-value transformation matrix. If not
                provided, use the named ``T00`` through ``T22`` parameters.
            origin: Optional 3-value transformed origin. If not provided,
                use the named ``x00`` through ``x02`` parameters.
            T00: Compatibility matrix entry, row 0 column 0.
            T01: Compatibility matrix entry, row 0 column 1.
            T02: Compatibility matrix entry, row 0 column 2.
            T10: Compatibility matrix entry, row 1 column 0.
            T11: Compatibility matrix entry, row 1 column 1.
            T12: Compatibility matrix entry, row 1 column 2.
            T20: Compatibility matrix entry, row 2 column 0.
            T21: Compatibility matrix entry, row 2 column 1.
            T22: Compatibility matrix entry, row 2 column 2.
            x00: Compatibility transformed-origin x coordinate.
            x01: Compatibility transformed-origin y coordinate.
            x02: Compatibility transformed-origin z coordinate.

        Returns:
            Managed ``H5DRMPattern`` instance.
        """
        entries = {
            key: value
            for key, value in {
                "T00": T00,
                "T01": T01,
                "T02": T02,
                "T10": T10,
                "T11": T11,
                "T12": T12,
                "T20": T20,
                "T21": T21,
                "T22": T22,
                "x00": x00,
                "x01": x01,
                "x02": x02,
            }.items()
            if value is not None
        }
        return self.add(
            H5DRMPattern(
                filepath=filepath,
                factor=factor,
                crd_scale=crd_scale,
                distance_tolerance=distance_tolerance,
                do_coordinate_transformation=do_coordinate_transformation,
                transform_matrix=transform_matrix,
                origin=origin,
                **entries,
            )
        )  # type: ignore[return-value]

    def plain(self, time_series: TimeSeries, factor: float = 1.0) -> PlainPattern:
        """Create and manage a ``PlainPattern``.

        Args:
            time_series: Managed ``TimeSeries`` referenced by the pattern.
            factor: Optional scale factor for all loads in the pattern.

        Returns:
            Managed ``PlainPattern`` instance.
        """
        return self.add(PlainPattern(time_series, factor))  # type: ignore[return-value]

    def multiple_support(self) -> MultipleSupportPattern:
        """Create and manage a ``MultipleSupportPattern``.

        Returns:
            Managed empty ``MultipleSupportPattern`` instance.
        """
        return self.add(MultipleSupportPattern())  # type: ignore[return-value]

    def _next_available_tag(self) -> int:
        """Return the next unused pattern tag in this manager's tag space."""
        return self._tagging.next_available_tag(self._patterns, self._start_tag)

    def _reassign_tags(self) -> None:
        """Retag all managed patterns from ``_start_tag`` in tag order."""
        self._tagging.reassign_tags(self._patterns, self._start_tag)
        for pattern in self._patterns.values():
            self._sync_attached_load_tags(pattern)

    def _sync_attached_load_tags(self, pattern: Pattern) -> None:
        """Keep loads attached to a plain pattern aligned with its current tag."""
        get_loads = getattr(pattern, "get_loads", None)
        if get_loads is None:
            return
        for load in get_loads():
            load.pattern_tag = pattern.tag

    def _validate_dependencies(self, pattern: Pattern) -> None:
        """Ensure a pattern only references dependencies from the local context."""
        time_series = getattr(pattern, "time_series", None)
        if time_series is not None:
            if time_series.tag is None or time_series._owner is None:
                raise ValueError("Pattern references an unmanaged TimeSeries")
            owner_manager = time_series._owner
            owner_mesh_maker = getattr(owner_manager, "_mesh_maker", None)
            if owner_mesh_maker is not self._mesh_maker:
                raise ValueError("Pattern references a TimeSeries from another Model")
            if (
                self._time_series_manager is not None
                and owner_manager is not self._time_series_manager
            ):
                raise ValueError("Pattern references a TimeSeries from another manager")

        get_imposed_motions = getattr(pattern, "get_imposed_motions", None)
        if get_imposed_motions is None:
            return
        for imposed_motion in get_imposed_motions():
            ground_motion = imposed_motion.ground_motion
            if ground_motion.tag is None or ground_motion._owner is None:
                raise ValueError("Pattern references an unmanaged GroundMotion")
            owner_manager = ground_motion._owner
            owner_mesh_maker = getattr(owner_manager, "_mesh_maker", None)
            if owner_mesh_maker is not self._mesh_maker:
                raise ValueError("Pattern references a GroundMotion from another Model")
            if (
                self._ground_motion_manager is not None
                and owner_manager is not self._ground_motion_manager
            ):
                raise ValueError("Pattern references a GroundMotion from another manager")
