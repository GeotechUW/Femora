# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Iterator, List, Optional

from femora.core.damping_base import Damping
from femora.core.tagging import CompactRetagPolicy

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.components.damping.dampings import FrequencyRayleighDamping
    from femora.components.damping.dampings import ModalDamping
    from femora.components.damping.dampings import RayleighDamping
    from femora.components.damping.dampings import SecantStiffnessProportional
    from femora.components.damping.dampings import UniformDamping


class DampingManager:
    """Define damping models through ``model.damping``.

    Factories construct and register damping definitions, assigning unique tags
    and generated names when no explicit name is supplied. Associate a definition
    with a region or mesh part separately; registration is not a global solver
    damping command and does not launch an analysis.

    Example:
        ```python
        from femora import Model

        model = Model()
        damping = model.damping.frequency_rayleigh(damping_factor=0.03, f1=3, f2=15)
        region = model.region.element(user_name="soil", damping=damping)
        assert region.damping is damping
        assert model.damping.get(damping.tag) is damping
        ```

    Note:
        Damping ratios are fractions, not percentages. Follow each concrete
        component's frequency and coefficient conventions. Combining damping
        sources requires physical calibration; successful creation does not
        establish an appropriate total damping or explicit stability limit.
    """

    __doc_controls__ = {
        "summary": True,
        "members": [
            "rayleigh",
            "modal",
            "frequency_rayleigh",
            "uniform",
            "secant_stiffness_proportional",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
            "get_available_types",
        ],
    }

    def __init__(self, mesh_maker: Model) -> None:
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")
        existing_manager = getattr(mesh_maker, "damping", None)
        if isinstance(existing_manager, DampingManager):
            raise ValueError("mesh_maker already owns a damping manager")

        self._mesh_maker = mesh_maker
        self._dampings: Dict[int, Damping] = {}
        self._names: Dict[str, Damping] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Damping]()

    def add(self, damping: Damping) -> Damping:
        """Register a damping object and assign its tag and default name.

        Args:
            damping (Damping): Unmanaged object or one already owned here.

        Returns:
            damping (Damping): Same object, retained by this manager.

        Raises:
            TypeError: Input is not a Damping.
            ValueError: Name/tag conflict or ownership by another manager.
        """
        if not isinstance(damping, Damping):
            raise TypeError("damping must be a Damping instance")
        if damping._owner is None:
            damping._owner = self
        elif damping._owner is not self:
            raise ValueError("damping already belongs to another manager")
        if damping.user_name == "UnnamedDamping":
            damping.user_name = self._generate_default_name(damping)
        existing_by_name = self._names.get(damping.user_name)
        if existing_by_name is not None and existing_by_name is not damping:
            raise ValueError(f"Damping name '{damping.user_name}' already exists in this manager")

        damping.tag = self._tagging.assign_tag(self._dampings, damping, self._start_tag)
        self._dampings[damping.tag] = damping
        self._names[damping.user_name] = damping
        return damping

    def rayleigh(
        self,
        *,
        alphaM: float = 0.0,
        betaK: float = 0.0,
        betaKInit: float = 0.0,
        betaKComm: float = 0.0,
        user_name: str | None = None,
    ) -> RayleighDamping:
        """Create a Rayleigh damping model.

        Args:
            alphaM: Mass-proportional damping factor.
            betaK: Current stiffness-proportional damping factor.
            betaKInit: Initial stiffness-proportional damping factor.
            betaKComm: Committed stiffness-proportional damping factor.
            user_name: Optional unique name for the damping object.

        Raises:
            ValueError: If any damping factor is negative or if all factors are zero.

        Returns:
            component (RayleighDamping): Registered definition; no solver is launched.
        """
        from femora.components.damping.dampings import RayleighDamping

        component = RayleighDamping(
            alphaM=alphaM,
            betaK=betaK,
            betaKInit=betaKInit,
            betaKComm=betaKComm,
            user_name=user_name,
        )
        self.add(component)
        return component

    def modal(
        self,
        *,
        numberofModes: int,
        damping_factors: Iterable[float] | str,
        user_name: str | None = None,
    ) -> ModalDamping:
        """Create a modal damping model.

        Args:
            numberofModes: Number of modes to apply damping to.
            damping_factors: Damping ratios (between 0.0 and 1.0) for each mode.
                Can be a list of floats or a comma-separated string.
            user_name: Optional unique name for the damping object.

        Raises:
            ValueError: If number of modes is invalid, or if the damping factors
                do not match the mode count, or are outside `[0.0, 1.0]`.

        Returns:
            component (ModalDamping): Registered definition; no solver is launched.
        """
        from femora.components.damping.dampings import ModalDamping

        component = ModalDamping(
            numberofModes=numberofModes, damping_factors=damping_factors, user_name=user_name
        )
        self.add(component)
        return component

    def frequency_rayleigh(
        self,
        *,
        damping_factor: float,
        f1: float = 0.2,
        f2: float = 20.0,
        user_name: str | None = None,
    ) -> FrequencyRayleighDamping:
        """Create a frequency-based Rayleigh damping model.

        Args:
            damping_factor: Target damping ratio (between 0.0 and 1.0).
            f1: First control frequency in Hz.
            f2: Second control frequency in Hz.
            user_name: Optional unique name for the damping object.

        Raises:
            ValueError: If frequencies are non-positive or if damping_factor is
                outside `[0.0, 1.0]`.

        Returns:
            component (FrequencyRayleighDamping): Registered definition; no solver is launched.
        """
        from femora.components.damping.dampings import FrequencyRayleighDamping

        component = FrequencyRayleighDamping(
            damping_factor=damping_factor, f1=f1, f2=f2, user_name=user_name
        )
        self.add(component)
        return component

    def uniform(
        self,
        *,
        dampingRatio: float,
        freql: float,
        freq2: float,
        Ta: float | None = None,
        Td: float | None = None,
        tsTagScaleFactorVsTime: int | None = None,
        user_name: str | None = None,
    ) -> UniformDamping:
        """Create a uniform damping model.

        Args:
            dampingRatio: Constant damping ratio (between 0.0 and 1.0).
            freql: Lower bound of the frequency range in Hz.
            freq2: Upper bound of the frequency range in Hz (must exceed `freql`).
            Ta: Optional activation time in seconds.
            Td: Optional deactivation time in seconds.
            tsTagScaleFactorVsTime: Optional time series tag for scaling damping.
            user_name: Optional unique name for the damping object.

        Raises:
            ValueError: If dampingRatio, freql, or freq2 parameters are invalid.

        Returns:
            component (UniformDamping): Registered definition; no solver is launched.
        """
        from femora.components.damping.dampings import UniformDamping

        component = UniformDamping(
            dampingRatio=dampingRatio,
            freql=freql,
            freq2=freq2,
            Ta=Ta,
            Td=Td,
            tsTagScaleFactorVsTime=tsTagScaleFactorVsTime,
            user_name=user_name,
        )
        self.add(component)
        return component

    def secant_stiffness_proportional(
        self,
        *,
        damping_factor: float,
        Ta: float | None = None,
        Td: float | None = None,
        tsTagScaleFactorVsTime: int | None = None,
        user_name: str | None = None,
    ) -> SecantStiffnessProportional:
        """Create a secant stiffness-proportional damping model.

        Args:
            damping_factor: Damping ratio proportional to secant stiffness (between 0.0 and 1.0).
            Ta: Optional activation time in seconds.
            Td: Optional deactivation time in seconds.
            tsTagScaleFactorVsTime: Optional time series tag for scaling damping.
            user_name: Optional unique name for the damping object.

        Raises:
            ValueError: If damping_factor is outside `[0.0, 1.0]`.

        Returns:
            component (SecantStiffnessProportional): Registered definition; no solver is launched.
        """
        from femora.components.damping.dampings import SecantStiffnessProportional

        component = SecantStiffnessProportional(
            damping_factor=damping_factor,
            Ta=Ta,
            Td=Td,
            tsTagScaleFactorVsTime=tsTagScaleFactorVsTime,
            user_name=user_name,
        )
        self.add(component)
        return component

    def get(self, tag: int) -> Optional[Damping]:
        """Return a damping definition by integer-convertible tag, or None.

        Args:
            tag (int): Registry key; conversion errors propagate.
        """
        return self._dampings.get(int(tag))

    def remove(self, tag: int) -> None:
        """Detach a damping definition and compact surviving registry tags.

        Args:
            tag (int): Current tag; missing entries are ignored.

        Regions are not rewritten. They hold weak references to damping objects,
        so an externally retained detached object can remain visible until released.
        Cached integer tags can become stale.
        """
        damping = self._dampings.pop(int(tag), None)
        if damping is not None:
            self._names.pop(damping.user_name, None)
            damping.tag = None
            damping._owner = None
            self._reassign_tags()

    def get_all(self) -> Dict[int, Damping]:
        """Return a shallow tag-to-definition snapshot with shared objects."""
        return dict(self._dampings)

    def clear(self) -> None:
        """Detach all damping objects and empty name/tag indices.

        Region assignments are not actively removed and no solver command is
        sent. Use coordinated model clearing when rebuilding the entire model.
        """
        for damping in list(self._dampings.values()):
            damping.tag = None
            damping._owner = None
        self._dampings.clear()
        self._names.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the positive damping-tag origin and retag existing definitions.

        Args:
            start_tag (int): Origin validated by the tagging policy.

        Raises:
            ValueError: Invalid origin. Exported files are not updated.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def _reassign_tags(self) -> None:
        self._tagging.reassign_tags(self._dampings, self._start_tag)
        self._names = {d.user_name: d for d in self._dampings.values()}

    def _generate_default_name(self, damping: Damping) -> str:
        base_name = damping.__class__.__name__
        if base_name not in self._names:
            return base_name

        index = 2
        while True:
            candidate = f"{base_name}_{index}"
            if candidate not in self._names:
                return candidate
            index += 1

    def get_available_types(self) -> List[str]:
        """Return human-readable damping family labels supported by this manager.

        Labels can contain spaces; they are not directly callable factory names.
        Use the explicitly documented methods to create a definition.
        """
        return [
            "rayleigh",
            "modal",
            "frequency rayleigh",
            "uniform",
            "secant stiffness proportional",
        ]

    def __len__(self) -> int:
        return len(self._dampings)

    def __iter__(self) -> Iterator[Damping]:
        return iter(self._dampings.values())
