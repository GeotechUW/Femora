# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Sequence, Union

from femora.components.time_series import (
    ConstantTimeSeries,
    LinearTimeSeries,
    PathTimeSeries,
    PulseTimeSeries,
    RampTimeSeries,
    RectangularTimeSeries,
    TriangularTimeSeries,
    TrigTimeSeries,
)
from femora.core.tagging import CompactRetagPolicy
from femora.core.time_series_base import TimeSeries

if TYPE_CHECKING:
    from femora.core.model import Model


class TimeSeriesManager:
    """Local manager for ``TimeSeries`` lifecycle and tag assignment.

    The manager is intentionally not a singleton. Each instance owns an
    independent tag space so future model or ``Model`` instances can keep
    their own time-series collections.

    Access factories through ``model.time_series``. A time series defines a
    scalar function of solver domain time; it is not an analysis time step,
    recorder interval, or a command that advances the domain clock. Patterns
    and ground motions reference these definitions to apply them to loading.

    Example:
        ```python
        from femora import Model

        model = Model()
        history = model.time_series.path(dt=0.01, values=[0.0, 1.0, 0.0])
        pattern = model.pattern.uniform_excitation(dof=1, time_series=history)
        model.process.add_step(pattern, "Apply excitation")
        assert model.time_series.get(history.tag) is history
        ```

    Use consistent time/amplitude units and stage file-backed histories where
    the solver can read them. Creation does not resample a record, check solver
    time-step stability, or ensure compatible duration. Removal/start-tag changes
    can invalidate dependency tags; rebuild affected patterns/ground motions.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "constant",
            "linear",
            "trig",
            "ramp",
            "triangular",
            "rectangular",
            "pulse",
            "path",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        """Create an empty manager with tags starting at ``1``."""
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        self._mesh_maker = mesh_maker
        self._time_series: Dict[int, TimeSeries] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[TimeSeries]()

    def add(self, time_series: TimeSeries) -> TimeSeries:
        """Add an existing time series and assign a tag if needed.

        Args:
            time_series: Unmanaged or already-managed ``TimeSeries`` instance.

        Returns:
            The same ``time_series`` instance after it is stored by this manager.

        Raises:
            TypeError: If ``time_series`` is not a ``TimeSeries`` instance.
            ValueError: If its preassigned tag conflicts with a different
                object already managed here.
        """
        if not isinstance(time_series, TimeSeries):
            raise TypeError("time_series must be a TimeSeries instance")
        if time_series._owner is None:
            time_series._owner = self
        elif time_series._owner is not self:
            raise ValueError("time_series already belongs to another manager")
        try:
            time_series.tag = self._tagging.assign_tag(
                self._time_series,
                time_series,
                self._start_tag,
            )
        except ValueError as exc:
            raise ValueError(f"TimeSeries tag {time_series.tag} already exists") from exc
        self._time_series[time_series.tag] = time_series
        return time_series

    def get(self, tag: int) -> Optional[TimeSeries]:
        """Return the time series with ``tag`` if it exists.

        Args:
            tag: Time-series tag to look up.

        Returns:
            The matching ``TimeSeries`` instance, or ``None``.
        """
        return self._time_series.get(tag)

    __len__ = lambda self: len(self._time_series)

    __iter__ = lambda self: iter(self._time_series.values())

    def get_all(self) -> Dict[int, TimeSeries]:
        """Return a shallow copy of all managed time series keyed by tag."""
        return dict(self._time_series)

    def remove(self, tag: int) -> None:
        """Remove a managed time series and compact the remaining tags.

        Args:
            tag: Tag of the time series to remove. Missing tags are ignored.
        """
        time_series = self._time_series.pop(tag, None)
        if time_series is not None:
            time_series.tag = None
            time_series._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Remove all time series and clear their assigned tags."""
        for time_series in self._time_series.values():
            time_series.tag = None
            time_series._owner = None
        self._time_series.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the first tag used by this manager and retag existing objects.

        Args:
            start_tag: Positive integer for the first assigned tag.

        Raises:
            ValueError: If ``start_tag`` is less than ``1``.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def constant(self, factor: float = 1.0) -> ConstantTimeSeries:
        """Create and manage a ``ConstantTimeSeries``.

        Args:
            factor: Constant scale factor.

        Returns:
            Managed ``ConstantTimeSeries`` instance.
        """
        return self.add(ConstantTimeSeries(factor=factor))  # type: ignore[return-value]

    def linear(self, factor: float = 1.0) -> LinearTimeSeries:
        """Create and manage a ``LinearTimeSeries``.

        Args:
            factor: Linear scale factor.

        Returns:
            Managed ``LinearTimeSeries`` instance.
        """
        return self.add(LinearTimeSeries(factor=factor))  # type: ignore[return-value]

    def trig(
        self,
        tStart: float = 0.0,
        tEnd: float = 1.0,
        period: float = 1.0,
        factor: float = 1.0,
        shift: float = 0.0,
    ) -> TrigTimeSeries:
        """Create and manage a ``TrigTimeSeries``.

        Args:
            tStart: Start time of the trigonometric series.
            tEnd: End time of the trigonometric series.
            period: Period of the sinusoidal cycle.
            factor: Load factor amplitude.
            shift: Phase shift.

        Returns:
            Managed ``TrigTimeSeries`` instance.
        """
        return self.add(TrigTimeSeries(tStart, tEnd, period, factor, shift))  # type: ignore[return-value]

    def ramp(
        self,
        tStart: float = 0.0,
        tRamp: float = 1.0,
        smoothness: float = 0.0,
        offset: float = 0.0,
        cFactor: float = 1.0,
    ) -> RampTimeSeries:
        """Create and manage a ``RampTimeSeries``.

        Args:
            tStart: Start time of the ramp.
            tRamp: Duration of the ramp.
            smoothness: Smoothness value between ``0`` and ``1``.
            offset: Vertical offset.
            cFactor: Load factor scale.

        Returns:
            Managed ``RampTimeSeries`` instance.
        """
        return self.add(RampTimeSeries(tStart, tRamp, smoothness, offset, cFactor))  # type: ignore[return-value]

    def triangular(
        self,
        tStart: float = 0.0,
        tEnd: float = 1.0,
        period: float = 1.0,
        factor: float = 1.0,
        shift: float = 0.0,
    ) -> TriangularTimeSeries:
        """Create and manage a ``TriangularTimeSeries``.

        Args:
            tStart: Start time of the triangular wave.
            tEnd: End time of the triangular wave.
            period: Wave period.
            factor: Load factor amplitude.
            shift: Phase shift.

        Returns:
            Managed ``TriangularTimeSeries`` instance.
        """
        return self.add(TriangularTimeSeries(tStart, tEnd, period, factor, shift))  # type: ignore[return-value]

    def rectangular(
        self,
        tStart: float = 0.0,
        tEnd: float = 1.0,
        period: float = 1.0,
        factor: float = 1.0,
        shift: float = 0.0,
    ) -> RectangularTimeSeries:
        """Create and manage a ``RectangularTimeSeries``.

        Args:
            tStart: Start time of the rectangular wave.
            tEnd: End time of the rectangular wave.
            period: Wave period.
            factor: Load factor amplitude.
            shift: Phase shift.

        Returns:
            Managed ``RectangularTimeSeries`` instance.
        """
        return self.add(RectangularTimeSeries(tStart, tEnd, period, factor, shift))  # type: ignore[return-value]

    def pulse(
        self,
        tStart: float = 0.0,
        tEnd: float = 1.0,
        period: float = 1.0,
        width: float = 0.5,
        factor: float = 1.0,
        shift: float = 0.0,
    ) -> PulseTimeSeries:
        """Create and manage a ``PulseTimeSeries``.

        Args:
            tStart: Start time of the pulse series.
            tEnd: End time of the pulse series.
            period: Pulse period.
            width: Pulse width as a fraction of the period.
            factor: Load factor amplitude.
            shift: Phase shift.

        Returns:
            Managed ``PulseTimeSeries`` instance.
        """
        return self.add(PulseTimeSeries(tStart, tEnd, period, width, factor, shift))  # type: ignore[return-value]

    def path(
        self,
        dt: Optional[float] = None,
        values: Optional[Union[str, Sequence[float]]] = None,
        filePath: Optional[str] = None,
        factor: float = 1.0,
        useLast: bool = False,
        prependZero: bool = False,
        startTime: float = 0.0,
        time: Optional[Union[str, Sequence[float]]] = None,
        fileTime: Optional[str] = None,
    ) -> PathTimeSeries:
        """Create and manage a ``PathTimeSeries``.

        Args:
            dt: Constant time step. Mutually exclusive with ``time`` and
                ``fileTime``.
            values: Inline path values as a sequence or comma-separated string.
                Mutually exclusive with ``filePath``.
            filePath: File containing path values. Mutually exclusive with
                ``values``.
            factor: Scale factor applied to the path values.
            useLast: Whether OpenSees should hold the last value after the path
                ends.
            prependZero: Whether OpenSees should prepend a zero value.
            startTime: Time offset for the path.
            time: Inline time values. Mutually exclusive with ``dt`` and
                ``fileTime``.
            fileTime: File containing time values. Mutually exclusive with
                ``dt`` and ``time``.

        Returns:
            Managed ``PathTimeSeries`` instance.
        """
        return self.add(
            PathTimeSeries(
                dt=dt,
                values=values,
                filePath=filePath,
                factor=factor,
                useLast=useLast,
                prependZero=prependZero,
                startTime=startTime,
                time=time,
                fileTime=fileTime,
            )
        )  # type: ignore[return-value]

    def _next_available_tag(self) -> int:
        """Return the next unused tag in this manager's local tag space."""
        return self._tagging.next_available_tag(self._time_series, self._start_tag)

    def _reassign_tags(self) -> None:
        """Retag all managed time series from ``_start_tag`` in tag order."""
        self._tagging.reassign_tags(self._time_series, self._start_tag)
