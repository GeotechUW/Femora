# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Union, Type, cast

from femora.core.tagging import CompactRetagPolicy
from femora.core.section_base import Section

if TYPE_CHECKING:
    from femora.core.model import Model
    from femora.core.material_base import Material
    from femora.components.section.fiber._base import LayerBase, PatchBase
    from femora.components.section.fiber.element import FiberElement
    from femora.components.section.beam.elastic import ElasticSection
    from femora.components.section.beam.uniaxial import UniaxialSection
    from femora.components.section.beam.wf2d import WFSection2d
    from femora.components.section.composite.aggregator import AggregatorSection
    from femora.components.section.composite.parallel import ParallelSection
    from femora.components.section.fiber.section import FiberSection
    from femora.components.section.fiber.rc import RCSection
    from femora.components.section.shell.elastic_membrane_plate import ElasticMembranePlateSection
    from femora.components.section.shell.plate_fiber import PlateFiberSection
    from femora.components.section.special.bidirectional import BidirectionalSection
    from femora.components.section.special.isolator2spring import Isolator2SpringSection


class _BeamSectionNamespace:
    """Beam-section factory namespace bound to a SectionManager."""

    def __init__(self, manager: "SectionManager") -> None:
        self._manager = manager

    def elastic(
        self,
        user_name: str = "Unnamed",
        *,
        E: float,
        A: float,
        Iz: float,
        Iy: float | None = None,
        G: float | None = None,
        J: float | None = None,
    ) -> ElasticSection:
        """Create an ElasticSection with validated geometric properties.

        Args:
            user_name: User-specified name for the section.
            E: Young's modulus.
            A: Cross-sectional area.
            Iz: Second moment of area about the local z-axis.
            Iy: Optional second moment of area about the local y-axis (for 3D).
            G: Optional shear modulus (for 3D).
            J: Optional torsional constant (for 3D).

        Raises:
            ValueError: If parameters are not numeric or if essential values
                (E, A, Iz) are non-positive.

        Returns:
            section (ElasticSection): Registered section using the owning Model context.
        """
        return cast(
            "ElasticSection",
            self._manager.create_section(
                "Elastic", user_name=user_name, E=E, A=A, Iz=Iz, Iy=Iy, G=G, J=J
            ),
        )

    def uniaxial(
        self,
        user_name: str = "Unnamed",
        *,
        material: int | str | Material,
        response_code: str = "P",
    ) -> UniaxialSection:
        """Create a UniaxialSection with validated material and response code.

        Args:
            user_name: User-specified name for the section.
            material: Uniaxial material reference (object, tag, or name).
            response_code: Section response code. Must be one of:
                'P', 'Mz', 'My', 'Vy', 'Vz', 'T'.

        Raises:
            ValueError: If the response code is invalid or the material
                cannot be resolved.

        Returns:
            section (UniaxialSection): Registered section using the owning Model context.
        """
        return cast(
            "UniaxialSection",
            self._manager.create_section(
                "Uniaxial", user_name=user_name, material=material, response_code=response_code
            ),
        )

    def wf2d(
        self,
        user_name: str = "Unnamed",
        *,
        material: int | str | Material,
        d: float,
        tw: float,
        bf: float,
        tf: float,
        Nflweb: int,
        Nflflange: int,
    ) -> WFSection2d:
        """Create a WFSection2d with validated dimensions and discretization.

        Args:
            user_name: Unique identifier for the section.
            material: Uniaxial material reference for the entire section.
            d: Total section depth.
            tw: Web thickness.
            bf: Flange width.
            tf: Flange thickness.
            Nflweb: Number of fibers along the web depth.
            Nflflange: Number of fibers along each flange width.

        Raises:
            ValueError: If the material cannot be resolved, or if any dimension
                is non-positive, or if fiber counts are not positive integers.

        Returns:
            section (WFSection2d): Registered section using the owning Model context.
        """
        return cast(
            "WFSection2d",
            self._manager.create_section(
                "WFSection2d",
                user_name=user_name,
                material=material,
                d=d,
                tw=tw,
                bf=bf,
                tf=tf,
                Nflweb=Nflweb,
                Nflflange=Nflflange,
            ),
        )


class _CompositeSectionNamespace:
    """Composite-section factory namespace bound to a SectionManager."""

    def __init__(self, manager: "SectionManager") -> None:
        self._manager = manager

    def aggregator(
        self,
        user_name: str = "Unnamed",
        *,
        materials: dict[str, int | str | Material] | None = None,
        base_section: int | str | Section | None = None,
    ) -> AggregatorSection:
        """Create an AggregatorSection with validated materials and response codes.

        Args:
            user_name: User-specified name for the section.
            materials: Optional dictionary mapping section response codes (e.g., 'P', 'Mz')
                to uniaxial materials (object, tag, or name).
            base_section: Optional base section to be augmented (object, tag, or name).

        Raises:
            ValueError: If response codes are invalid or materials/sections
                cannot be resolved.

        Returns:
            section (AggregatorSection): Registered section using the owning Model context.
        """
        return cast(
            "AggregatorSection",
            self._manager.create_section(
                "Aggregator", user_name=user_name, materials=materials, base_section=base_section
            ),
        )

    def parallel(
        self, user_name: str = "Unnamed", *, sections: list[int | str | Section] | None = None
    ) -> ParallelSection:
        """Create a ParallelSection with validated constituent sections.

        Args:
            user_name: User-specified name for the section.
            sections: Optional list of constituent sections (objects, tags, or names).

        Raises:
            ValueError: If constituent sections cannot be resolved.

        Returns:
            section (ParallelSection): Registered section using the owning Model context.
        """
        return cast(
            "ParallelSection",
            self._manager.create_section("Parallel", user_name=user_name, sections=sections),
        )


class _FiberSectionNamespace:
    """Fiber-section factory namespace bound to a SectionManager."""

    def __init__(self, manager: "SectionManager") -> None:
        self._manager = manager

    def section(
        self,
        user_name: str = "Unnamed",
        *,
        GJ: float | None = None,
        components: list[FiberElement | PatchBase | LayerBase] | None = None,
    ) -> FiberSection:
        """Create a FiberSection with optional initial components.

        Args:
            user_name: Unique identifier for the section.
            GJ: Optional linear torsional stiffness constant. If provided,
                this stiffness is added to the section's torsional response.
            components: Optional list of pre-created fiber elements, patches,
                or layers to populate the section.

        Raises:
            ValueError: If GJ is not numeric or is non-positive.

        Returns:
            section (FiberSection): Registered section using the owning Model context.
        """
        return cast(
            "FiberSection",
            self._manager.create_section(
                "Fiber", user_name=user_name, GJ=GJ, components=components
            ),
        )

    def rc(
        self,
        user_name: str = "Unnamed",
        *,
        core_material: int | str | Material,
        cover_material: int | str | Material,
        steel_material: int | str | Material,
        d: float,
        b: float,
        cover_to_center_of_bar: float,
    ) -> RCSection:
        """Create an RCSection with validated materials and dimensions.

        Args:
            user_name: User-specified name for the section.
            core_material: Reference to the core concrete material.
            cover_material: Reference to the cover concrete material.
            steel_material: Reference to the reinforcement material.
            d: Total section depth.
            b: Total section width.
            cover_to_center_of_bar: Concrete cover to bar centers.

        Raises:
            ValueError: If materials cannot be resolved, if dimensions are not
                numeric, or if dimensions are non-positive.

        Returns:
            section (RCSection): Registered section using the owning Model context.
        """
        return cast(
            "RCSection",
            self._manager.create_section(
                "RC",
                user_name=user_name,
                core_material=core_material,
                cover_material=cover_material,
                steel_material=steel_material,
                d=d,
                b=b,
                cover_to_center_of_bar=cover_to_center_of_bar,
            ),
        )


class _ShellSectionNamespace:
    """Shell-section factory namespace bound to a SectionManager."""

    def __init__(self, manager: "SectionManager") -> None:
        self._manager = manager

    def elastic_membrane_plate(
        self, user_name: str = "Unnamed", *, E: float, nu: float, h: float, rho: float
    ) -> ElasticMembranePlateSection:
        """Create an ElasticMembranePlateSection with validated constants.

        Args:
            user_name: Unique identifier for the section.
            E: Young's modulus of the shell material.
            nu: Poisson's ratio.
            h: Thickness of the shell.
            rho: Mass density (mass per unit volume).

        Raises:
            ValueError: If any parameter is not numeric, if E or h are
                non-positive, if nu is not in [0, 0.5), or if rho is negative.

        Returns:
            section (ElasticMembranePlateSection): Registered section using the owning Model context.
        """
        return cast(
            "ElasticMembranePlateSection",
            self._manager.create_section(
                "ElasticMembranePlateSection", user_name=user_name, E=E, nu=nu, h=h, rho=rho
            ),
        )

    def plate_fiber(
        self, user_name: str = "Unnamed", *, material: int | str | Material
    ) -> PlateFiberSection:
        """Create a PlateFiberSection with a validated nD material.

        Args:
            user_name: Unique identifier for the section.
            material: nD material reference (object, tag, or name).

        Raises:
            ValueError: If the material cannot be resolved, or if it is not
                recognized as an nDMaterial.

        Returns:
            section (PlateFiberSection): Registered section using the owning Model context.
        """
        return cast(
            "PlateFiberSection",
            self._manager.create_section("PlateFiber", user_name=user_name, material=material),
        )


class _SpecialSectionNamespace:
    """Special-section factory namespace bound to a SectionManager."""

    def __init__(self, manager: "SectionManager") -> None:
        self._manager = manager

    def bidirectional(
        self, user_name: str = "Unnamed", *, E: float, Fy: float, Hiso: float, Hkin: float
    ) -> BidirectionalSection:
        """Create a BidirectionalSection with validated parameters.

        Args:
            user_name: User-specified name for the section.
            E: Elastic modulus.
            Fy: Yield force.
            Hiso: Isotropic hardening modulus.
            Hkin: Kinematic hardening modulus.

        Raises:
            ValueError: If parameters are not numeric, if E or Fy are non-positive,
                or if hardening moduli are negative.

        Returns:
            section (BidirectionalSection): Registered section using the owning Model context.
        """
        return cast(
            "BidirectionalSection",
            self._manager.create_section(
                "Bidirectional", user_name=user_name, E=E, Fy=Fy, Hiso=Hiso, Hkin=Hkin
            ),
        )

    def isolator2spring(
        self,
        user_name: str = "Unnamed",
        *,
        tol: float,
        k1: float,
        Fy: float,
        k2: float,
        kv: float,
        hb: float,
        Pe: float,
        Po: float,
    ) -> Isolator2SpringSection:
        """Create an Isolator2SpringSection with validated parameters.

        Args:
            user_name: User-specified name for the section.
            tol: Tolerance.
            k1: Initial horizontal stiffness.
            Fy: Yield force.
            k2: Post-yield horizontal stiffness.
            kv: Vertical stiffness.
            hb: Bearing height.
            Pe: Buckling load.
            Po: Axial load.

        Raises:
            ValueError: If parameters are not numeric, if dimensions/stiffnesses
                are non-positive, or if loads are negative.

        Returns:
            section (Isolator2SpringSection): Registered section using the owning Model context.
        """
        return cast(
            "Isolator2SpringSection",
            self._manager.create_section(
                "Isolator2spring",
                user_name=user_name,
                tol=tol,
                k1=k1,
                Fy=Fy,
                k2=k2,
                kv=kv,
                hb=hb,
                Pe=Pe,
                Po=Po,
            ),
        )


class SectionManager:
    """Local manager for ``Section`` lifecycle and tag assignment.

    The manager is intentionally not a singleton. Each instance owns an
    independent tag space so Model instances keep their own section collections.
    Access it through ``model.section`` rather than constructing another manager.

    Attributes:
        beam: ``elastic``, ``uniaxial``, and ``wf2d`` section factories.
        composite: ``aggregator`` and ``parallel`` factories.
        fiber: ``section`` and ``rc`` factories.
        shell: ``elastic_membrane_plate`` and ``plate_fiber`` factories.
        special: ``bidirectional`` and ``isolator2spring`` factories.

    Each namespace accepts ``user_name`` and component-specific keyword options,
    forwarding them to ``create_section``. Concrete section parameters are
    documented in the Components section reference. All namespaces share this
    manager's registry and require unique section names.

    Example:
        ```python
        from femora import Model

        model = Model()
        section = model.section.beam.elastic(
            user_name="column", E=200e6, G=77e6, A=0.01,
            Iy=1e-4, Iz=1e-4, J=2e-4,
        )
        assert model.section.get("column") is section
        assert model.section.get(section.tag) is section
        ```

    Warning:
        Removing a section can retag survivors. Elements that reference removed
        sections are not repaired, and already exported solver files are unchanged.
    """

    __doc_controls__ = {
        "summary": True,
        "show_docstring_attributes": True,
        "members": [
            "create_section",
            "add",
            "get",
            "get_all",
            "remove",
            "clear",
            "set_tag_start",
            "resolve_material",
            "get_section_types",
            "register_section_type",
        ],
    }
    _section_types: Dict[str, Type[Section]] = {}
    _builtins_loaded = False

    def __init__(self, mesh_maker: Model) -> None:
        """Create an empty manager with tags starting at ``1``.

        Args:
            mesh_maker: The owning Model instance.

        Raises:
            TypeError: If mesh_maker is not a Model instance.
            RuntimeError: If the Model already owns a SectionManager.
        """
        from femora.core.model import Model as ModelClass

        if not isinstance(mesh_maker, ModelClass):
            raise TypeError("mesh_maker must be a Model instance")

        if hasattr(mesh_maker, "section") and mesh_maker.section is not None:
            if mesh_maker.section is not self:
                raise RuntimeError("Model already owns a SectionManager")

        self._mesh_maker = mesh_maker
        self._sections: Dict[int, Section] = {}
        self._names: Dict[str, Section] = {}
        self._start_tag = 1
        self._tagging = CompactRetagPolicy[Section]()
        self._ensure_builtin_section_types_loaded()
        self.beam = _BeamSectionNamespace(self)
        self.composite = _CompositeSectionNamespace(self)
        self.fiber = _FiberSectionNamespace(self)
        self.shell = _ShellSectionNamespace(self)
        self.special = _SpecialSectionNamespace(self)

    def add(self, section: Section) -> Section:
        """Add an existing section and assign a tag if needed.

        Args:
            section: Unmanaged or already-managed ``Section`` instance.

        Returns:
            The same ``section`` instance after it is stored by this manager.

        Raises:
            TypeError: If ``section`` is not a ``Section`` instance.
            ValueError: If its preassigned tag conflicts or name is duplicate.
        """
        if not isinstance(section, Section):
            raise TypeError("section must be a Section instance")

        if section.user_name in self._names and self._names[section.user_name] is not section:
            raise ValueError(f"Section name '{section.user_name}' already exists in this manager")

        if section._owner is None:
            section._owner = self
        elif section._owner is not self:
            raise ValueError("section already belongs to another manager")

        try:
            section.tag = self._tagging.assign_tag(
                self._sections,
                section,
                self._start_tag,
            )
        except ValueError as exc:
            raise ValueError(f"Section tag {section.tag} already exists") from exc

        self._sections[section.tag] = section
        self._names[section.user_name] = section
        return section

    def get(self, identifier: Union[int, str]) -> Optional[Section]:
        """Return the section with ``tag`` or ``user_name`` if it exists.

        Args:
            identifier: Section tag (int) or name (str) to look up.

        Returns:
            The matching ``Section`` instance, or ``None``.
        """
        if isinstance(identifier, int):
            return self._sections.get(identifier)
        return self._names.get(identifier)

    def get_all(self) -> Dict[int, Section]:
        """Return a shallow copy of all managed sections keyed by tag."""
        return dict(self._sections)

    def remove(self, identifier: Union[int, str]) -> None:
        """Remove a managed section and compact the remaining tags.

        Args:
            identifier: Tag or name of the section to remove. Missing sections are ignored.
        """
        section = self.get(identifier)
        if section is not None:
            self._sections.pop(section.tag, None)
            self._names.pop(section.user_name, None)
            section.tag = None
            section._owner = None
            self._reassign_tags()

    def clear(self) -> None:
        """Remove all sections and clear their assigned tags."""
        for section in self._sections.values():
            section.tag = None
            section._owner = None
        self._sections.clear()
        self._names.clear()

    def set_tag_start(self, start_tag: int) -> None:
        """Set the first tag used by this manager and retag existing objects.

        Args:
            start_tag: Positive integer for the first assigned tag.

        Raises:
            ValueError: If ``start_tag`` is less than ``1``.
        """
        self._start_tag = self._tagging.validate_start_tag(start_tag)
        self._reassign_tags()

    def create_section(self, section_type: str, user_name: str, **section_params: Any) -> Section:
        """Create and manage a section by type name using the manager factory map.

        This is the authoritative creation path for the active runtime. It ensures
        that the section is context-aware during its initialization so it can
        resolve materials and other dependencies without global state.

        Args:
            section_type: Registered section type name.
            user_name: Unique name for the section.
            **section_params (Any): Constructor arguments for the selected concrete class.

        Returns:
            Managed ``Section`` instance.

        Raises:
            KeyError: If ``section_type`` is not registered.
        """
        section_class = self._section_types.get(section_type)
        if section_class is None:
            raise KeyError(f"Section type '{section_type}' not registered")

        # Instantiate without calling __init__ yet to inject manager context
        section = section_class.__new__(section_class)
        section._owner = self
        section.__init__(user_name=user_name, **section_params)

        return self.add(section)

    def resolve_material(
        self, material_input: Union[int, str, Material, None]
    ) -> Optional[Material]:
        """Resolve a material using this manager's owning Model.

        Args:
            material_input (int | str | Material | None): Integer registry tag,
                exact material name, object, or None. Strings are names, not
                numeric tags, unlike the element material resolver.

        Returns:
            material (Material | None): Direct object unchanged, lookup result,
                or None for absent input or a missing name/tag. Objects are not
                registered or checked for cross-model ownership by this helper.

        Raises:
            TypeError: A non-string lookup value cannot be converted to an integer.
            ValueError: Integer conversion fails.
        """
        from femora.core.material_base import Material as MaterialClass

        if material_input is None:
            return None
        if isinstance(material_input, MaterialClass):
            return material_input
        if isinstance(material_input, str):
            return self._mesh_maker.material.get_by_name(material_input)
        return self._mesh_maker.material.get(int(material_input))

    def _reassign_tags(self) -> None:
        """Retag all managed sections from ``_start_tag`` in tag order."""
        self._tagging.reassign_tags(self._sections, self._start_tag)

    def __len__(self) -> int:
        return len(self._sections)

    def __iter__(self):
        return iter(self._sections.values())

    @classmethod
    def register_section_type(cls, name: str, section_class: Type[Section]) -> None:
        """Install a section constructor in the class-wide factory map.

        Args:
            name (str): Factory key used by ``create_section``.
            section_class (type[Section]): Constructor implementing the Section
                contract and accepting ``user_name`` plus its section parameters.

        Note:
            This is an extension operation shared across manager instances.
            Existing keys are replaced without subclass validation; existing
            section objects are not changed. Prefer built-in namespaces for
            ordinary model scripts.
        """
        cls._section_types[name] = section_class

    @classmethod
    def _ensure_builtin_section_types_loaded(cls) -> None:
        """Load bundled section families once so manager namespaces just work."""
        if cls._builtins_loaded:
            return
        import femora.components.section  # noqa: F401

        cls._builtins_loaded = True

    @classmethod
    def get_section_types(cls) -> list[str]:
        """Return a new list of keys in the class-wide section factory map.

        These are type names for ``create_section``, not user names of registered
        instances. Built-ins are loaded when a SectionManager is constructed.
        """
        return list(cls._section_types.keys())
