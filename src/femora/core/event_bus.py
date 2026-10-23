# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from collections import defaultdict
from enum import Enum, auto
from typing import Callable, Dict, List


class FemoraEvent(Enum):
    """Lifecycle signals emitted by Femora runtime subsystems.

    These enum values describe *when* a callback is being invoked. They are
    not ordinary modeling commands. Instead, they mark important stages in the
    runtime lifecycle so advanced components can react at the right time.

    The most important practical events are:

    - `PRE_ASSEMBLE`: emitted before the final assembled mesh is built
    - `POST_ASSEMBLE`: emitted after the final assembled mesh exists
    - `RESOLVE_CORE_CONFLICTS`: emitted after assembly when partition/core
      ownership updates may need follow-up work
    - `PRE_EXPORT` and `POST_EXPORT`: emitted around export-time workflows

    More specialized events such as `EMBEDDED_BEAM_SOLID_TCL` are used by
    advanced exporters and interface-specific integrations.
    """

    __doc_controls__ = {"members": []}

    PRE_ASSEMBLE = auto()
    POST_ASSEMBLE = auto()
    PRE_EXPORT = auto()
    POST_EXPORT = auto()
    RESOLVE_CORE_CONFLICTS = auto()
    EMBEDDED_BEAM_SOLID_TCL = auto()
    INTERFACE_ELEMENTS_TCL = auto()
    EMBEDDED_BEAM_CONTACT_TCL = auto()


class ModelEventBus:
    """Per-model publish/subscribe bus owned by a Model.

    A [`Model`][femora.core.model.Model] creates one `ModelEventBus` and
    exposes it through `model.events`. Managers and advanced components use
    that bus to coordinate lifecycle work without tightly coupling themselves
    to one another.

    Callbacks are registered per [`FemoraEvent`][femora.core.event_bus.FemoraEvent]
    and are invoked with keyword-argument payload data supplied by the emitter.

    Example:
        ```python
        from femora.core.model import Model
        from femora.components.event.event_bus import FemoraEvent

        model = Model()

        def on_post_assemble(**payload):
            assembled_mesh = payload.get("assembled_mesh")
            if assembled_mesh is not None:
                print(assembled_mesh.n_points)

        model.events.subscribe(FemoraEvent.POST_ASSEMBLE, on_post_assemble)
        ```
    """

    __doc_controls__ = {"summary": True, "members": ["subscribe", "unsubscribe", "clear"]}

    def __init__(self) -> None:
        """Initialize an empty per-model subscriber registry."""
        self._subscribers: Dict[FemoraEvent, List[Callable]] = defaultdict(list)

    def subscribe(self, event: FemoraEvent, callback: Callable) -> None:
        """Register a callback for one lifecycle event.

        If the callback is already subscribed to the same event, it is not
        added a second time.

        Args:
            event: Lifecycle event to listen for.
            callback: Callable invoked when `event` is emitted. The callback
                receives keyword arguments from the emitter.

        Callbacks execute synchronously in subscription order and are retained
        strongly. Exceptions propagate to the emitter, potentially interrupting
        assembly/export. Use flexible keyword payload handling when appropriate.
        """
        if callback not in self._subscribers[event]:
            self._subscribers[event].append(callback)

    def unsubscribe(self, event: FemoraEvent, callback: Callable) -> None:
        """Remove a previously registered callback from one event.

        Args:
            event: Lifecycle event previously used during subscription.
            callback: Callback to remove.
        """
        subscribers = self._subscribers[event]
        if callback in subscribers:
            subscribers.remove(callback)

    def emit(self, event: FemoraEvent, **payload) -> None:
        """Dispatch one lifecycle event to its current subscribers.

        The bus iterates over a snapshot of the subscriber list so callbacks
        can safely unsubscribe or adjust registrations during dispatch without
        corrupting the iteration order.

        Args:
            event: Lifecycle event being emitted.
            **payload (Any): Keyword arguments forwarded directly to each callback.
                Emitters commonly provide objects such as `assembled_mesh`.
        """
        for callback in list(self._subscribers[event]):
            callback(**payload)

    def clear(self) -> None:
        """Remove all subscribers, including model-internal lifecycle handlers.

        Prefer unsubscribing a particular user callback instead of clearing an
        active model's bus. Model.clear_model re-establishes its built-in hooks
        as part of coordinated clearing; this method alone does not do that.
        """
        self._subscribers.clear()


class EventBus:
    """Legacy process-global compatibility wrapper around `ModelEventBus`.

    This class exists mainly to preserve older code paths and tests that still
    expect a process-global event bus. New code should prefer the model-owned
    [`ModelEventBus`][femora.core.event_bus.ModelEventBus] exposed through
    `model.events`.

    Under the hood, this wrapper forwards operations to an internal
    `ModelEventBus` instance while preserving compatibility with older code
    that mutates `_subscribers` directly.
    """

    __doc_controls__ = {"members": []}

    _bus = ModelEventBus()
    _subscribers = _bus._subscribers

    @classmethod
    def _sync_bus(cls) -> None:
        """Synchronize the wrapper bus with the public compatibility storage."""
        # Preserve compatibility if tests or old code replace _subscribers directly.
        cls._bus._subscribers = cls._subscribers

    @classmethod
    def subscribe(cls, event: FemoraEvent, callback: Callable) -> None:
        """Register a callback through the legacy compatibility wrapper."""
        cls._sync_bus()
        cls._bus.subscribe(event, callback)

    @classmethod
    def unsubscribe(cls, event: FemoraEvent, callback: Callable) -> None:
        """Remove a callback through the legacy compatibility wrapper."""
        cls._sync_bus()
        cls._bus.unsubscribe(event, callback)

    @classmethod
    def emit(cls, event: FemoraEvent, **payload) -> None:
        """Emit one lifecycle event through the legacy compatibility wrapper."""
        cls._sync_bus()
        cls._bus.emit(event, **payload)
