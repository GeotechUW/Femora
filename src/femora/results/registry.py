# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Reader registration and format dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Union

from .base import ResultReader
from .exceptions import ResultFormatError


ReaderFactory = Callable[..., ResultReader]


class ResultReaderRegistry:
    """Advanced dispatch table mapping format names and suffixes to readers.

    The shared reader_registry already contains VTKHDF. Create a separate
    instance only when a tool needs its own format registrations; pass it as
    open_results(registry=...) to avoid modifying shared dispatch behavior.

    Example:
        ```python
        from femora.results.registry import ResultReaderRegistry
        from femora.results.readers import VTKHDFResultReader
        from femora.results import open_results

        registry = ResultReaderRegistry()
        registry.register("vtkhdf", VTKHDFResultReader, suffixes=".vtkhdf")
        with open_results("results/response0.vtkhdf", registry=registry) as results:
            print(results.number_of_steps)
        ```
    """

    __doc_controls__ = {"members": [
        "register", "create", "registered_formats", "registered_suffixes",
    ]}

    def __init__(self) -> None:
        self._named_factories: Dict[str, ReaderFactory] = {}
        self._factories: Dict[str, ReaderFactory] = {}

    def register(
        self,
        name: str,
        factory: ReaderFactory,
        *,
        suffixes: Union[str, Iterable[str]] = (),
        replace: bool = False,
    ) -> None:
        """Register a factory without opening or converting a file.

        Args:
            name: Case-insensitive format name used by explicit format dispatch.
            factory: Callable accepting a path and any reader-specific options,
                returning a ResultReader.
            suffixes: Suffix string or iterable. A missing leading dot is added.
            replace: Permit replacing conflicting names and suffix mappings.

        Raises:
            ValueError: Name/suffix conflicts exist and replace is False.
        """
        normalized_name = name.lower()
        if isinstance(suffixes, str):
            suffixes = [suffixes]
        normalized_suffixes = []
        for suffix in suffixes:
            normalized = suffix.lower()
            normalized_suffixes.append(
                normalized if normalized.startswith(".") else f".{normalized}"
            )

        if normalized_name in self._named_factories and not replace:
            raise ValueError(f"A result reader named '{normalized_name}' is registered")
        conflicts = [
            suffix
            for suffix in normalized_suffixes
            if suffix in self._factories and not replace
        ]
        if conflicts:
            raise ValueError(f"A result reader is already registered for {conflicts[0]}")

        self._named_factories[normalized_name] = factory
        for suffix in normalized_suffixes:
            self._factories[suffix] = factory

    def create(
        self,
        path: Union[str, Path],
        *,
        format: Optional[str] = None,
        **options: Any,
    ) -> ResultReader:
        """Instantiate a reader by explicit format name or file suffix.

        Args:
            path: Recorder path; concrete readers check file existence/layout.
            format: Registered name, or None to dispatch by the path suffix.
            **options: Keyword options forwarded unchanged to the factory.

        Returns:
            ResultReader: New instance. The caller owns its resources and must close it.

        Raises:
            ResultFormatError: No matching reader factory is registered.
        """
        resolved = Path(path)
        factory = (
            self._named_factories.get(format.lower())
            if format is not None
            else self._factories.get(resolved.suffix.lower())
        )
        if factory is None:
            if format is not None:
                raise ResultFormatError(f"No result reader named '{format}' is registered")
            raise ResultFormatError(
                f"No result reader is registered for '{resolved.suffix or resolved.name}'"
            )
        return factory(resolved, **options)

    @property
    def registered_formats(self) -> tuple[str, ...]:
        """Return registered reader names."""
        return tuple(sorted(self._named_factories))

    @property
    def registered_suffixes(self) -> tuple[str, ...]:
        """Return registered result suffixes."""
        return tuple(sorted(self._factories))


reader_registry = ResultReaderRegistry()
