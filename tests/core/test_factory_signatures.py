"""Keep public built-in factories discoverable and aligned with components."""

import inspect
import ast
import importlib
from functools import lru_cache
from pathlib import Path
import typing

import pytest

from femora import Model


ANALYSIS_FAMILIES = ("algorithm", "constraint", "system", "test", "integrator")


def analysis_factories():
    model = Model()
    for family in ANALYSIS_FAMILIES:
        manager = getattr(model.analysis, family)
        for name in manager.__doc_controls__["members"]:
            if name.startswith("get_"):
                continue
            factory = getattr(manager, name)
            component = typing.get_type_hints(factory)["return"]
            yield family, name, factory, component


FACTORY_CASES = [(family, name) for family, name, _, _ in analysis_factories()]

BUILTIN_FAMILIES = {
    "analysis.numberer": ["plain", "rcm", "amd", "parallelrcm", "parallelplain"],
    "material.nd": [
        "elastic_isotropic",
        "j2_cyclic_bounding_surface",
        "drucker_prager",
        "linear_elastic_ggmax",
        "pressure_depend_multi_yield",
        "pressure_independ_multi_yield",
    ],
    "material.uniaxial": ["elastic", "steel01"],
    "element.beam": ["elastic", "disp", "force", "truss"],
    "element.brick": ["std", "pml3d", "ssp"],
    "element.quad": ["ssp"],
    "element.special": [
        "ghost_node",
        "asd_embedded_node",
        "embedded_node_contact",
        "zero_length_contact",
    ],
    "damping": [
        "rayleigh",
        "modal",
        "frequency_rayleigh",
        "uniform",
        "secant_stiffness_proportional",
    ],
    "load": ["node", "element", "sp"],
    "section.beam": ["elastic", "uniaxial", "wf2d"],
    "section.composite": ["aggregator", "parallel"],
    "section.fiber": ["section", "rc"],
    "section.shell": ["elastic_membrane_plate", "plate_fiber"],
    "section.special": ["bidirectional", "isolator2spring"],
    "recorder": [
        "node",
        "drift",
        "vtkhdf",
        "mpco",
        "beam_force",
        "embedded_beam_solid_interface",
        "pile_mpco",
        "pile_vtkhdf",
    ],
    "interface": ["beam_solid_interface", "node_interface"],
    "region": ["element", "node"],
    "constraint.sp": [
        "fix",
        "fix_x",
        "fix_y",
        "fix_z",
        "fix_macro_x_min",
        "fix_macro_x_max",
        "fix_macro_y_min",
        "fix_macro_y_max",
        "fix_macro_z_min",
        "fix_macro_z_max",
    ],
    "constraint.mp": ["equal_dof", "rigid_link", "rigid_diaphragm"],
    "meshpart.line": ["single_line", "structured_lines"],
    "meshpart.volume": [
        "uniform_rectangular_grid",
        "custom_rectangular_grid",
        "geometric_rectangular_grid",
    ],
    "meshpart.surface": ["circular_o_grid"],
    "meshpart.general": ["external_mesh", "composite"],
}
BUILTIN_CASES = [(path, name) for path, names in BUILTIN_FAMILIES.items() for name in names]


@lru_cache
def annotation_namespace(module_name):
    module = importlib.import_module(module_name)
    namespace = dict(vars(module))
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(("femora.", "pyvista"))
        ):
            source = importlib.import_module(node.module)
            for alias in node.names:
                if alias.name != "*":
                    namespace[alias.asname or alias.name] = getattr(source, alias.name)
    return namespace


def get_factory(path, name):
    namespace = Model()
    for item in path.split("."):
        namespace = getattr(namespace, item)
    method = getattr(namespace, name)
    return method if inspect.ismethod(method) else method.__call__


@pytest.mark.parametrize("path,name", BUILTIN_CASES)
def test_builtin_factories_have_explicit_typed_contracts(path, name):
    factory = get_factory(path, name)
    signature = inspect.signature(factory)
    hints = typing.get_type_hints(factory, localns=annotation_namespace(factory.__module__))
    assert inspect.isclass(hints["return"]), (path, name, hints)
    assert hints["return"].__module__.startswith("femora.components."), (path, name)
    for parameter in signature.parameters.values():
        assert parameter.kind not in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        assert parameter.name in hints, (path, name, parameter.name)


@pytest.mark.parametrize("path,name", BUILTIN_CASES)
def test_known_constructor_options_are_exposed(path, name):
    if name.startswith("pile_"):
        return  # These helpers select groups rather than mirror a constructor.
    factory = get_factory(path, name)
    component = typing.get_type_hints(factory, localns=annotation_namespace(factory.__module__))[
        "return"
    ]
    constructor = inspect.signature(component)
    for key, parameter in constructor.parameters.items():
        if (
            parameter.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            or key == "meshpart"
        ):
            continue
        assert key in inspect.signature(factory).parameters, (path, name, key)
    # Defaults remain aligned unless the pre-existing public API intentionally differs.
    for key, parameter in constructor.parameters.items():
        if key not in inspect.signature(factory).parameters:
            continue
        if (path, name, key) in {
            ("material.nd", "elastic_isotropic", "E"),
            ("material.nd", "elastic_isotropic", "nu"),
            ("material.uniaxial", "elastic", "E"),
            ("element.special", "ghost_node", "ndof"),
            ("recorder", "embedded_beam_solid_interface", "resp_type"),
        }:
            continue
        assert inspect.signature(factory).parameters[key].default == parameter.default, (
            path,
            name,
            key,
        )


@pytest.mark.parametrize("family,name", FACTORY_CASES)
def test_analysis_factory_signature_matches_component(family, name):
    factory = getattr(getattr(Model().analysis, family), name)
    signature = inspect.signature(factory)
    component = typing.get_type_hints(factory)["return"]
    constructor = inspect.signature(component)
    assert set(signature.parameters) == set(constructor.parameters)
    hints = typing.get_type_hints(factory)
    constructor_hints = typing.get_type_hints(component.__init__)
    for parameter in signature.parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == constructor.parameters[parameter.name].default
        assert hints[parameter.name] == constructor_hints[parameter.name]


@pytest.mark.parametrize("family,name", FACTORY_CASES)
def test_analysis_factory_forwards_and_registers_exact_object(family, name, monkeypatch):
    manager = getattr(Model().analysis, family)
    factory = getattr(manager, name)
    component = typing.get_type_hints(factory)["return"]
    signature = inspect.signature(factory)
    arguments = {key: object() for key in signature.parameters}
    observed = []
    result = object()

    def construct(**kwargs):
        observed.append(kwargs)
        return result

    registered = []
    monkeypatch.setitem(factory.__func__.__globals__, component.__name__, construct)
    monkeypatch.setattr(manager, "add", lambda value: registered.append(value))
    assert factory(**arguments) is result
    assert observed == [arguments]
    assert registered == [result]
    with pytest.raises(TypeError):
        factory(**arguments, misspelled_option=True)
    with pytest.raises(TypeError):
        factory(object())


def test_analysis_construction_and_validation_remain_component_owned():
    model = Model()
    algorithm = model.analysis.algorithm.modifiednewton(factor_once=True)
    assert model.analysis.algorithm.get(algorithm.tag) is algorithm
    assert "-factoronce" in algorithm.to_tcl()
    with pytest.raises(ValueError):
        model.analysis.algorithm.newton(initial=True, initial_then_current=True)
    with pytest.raises(ValueError):
        model.analysis.integrator.newmark(gamma=0.5, beta=0.25, form="invalid")


@pytest.mark.parametrize(
    "path,name",
    [
        (path, name)
        for path, name in BUILTIN_CASES
        if not path.startswith("section")
        and not name.startswith("pile_")
        and path != "analysis.numberer"
    ],
)
def test_builtin_forwarding_and_exact_registration(path, name, monkeypatch):
    factory = get_factory(path, name)
    namespace = factory.__self__
    owner = getattr(namespace, "_manager", namespace)
    component = typing.get_type_hints(factory, localns=annotation_namespace(factory.__module__))[
        "return"
    ]
    # Aliases have their own normalization tests; use canonical names here.
    aliases = {"name", "regions", "element_group", "element_groups", "core"}
    if name == "mpco":
        aliases.remove("regions")
    arguments = {
        key: object()
        for key in inspect.signature(factory).parameters
        if key not in aliases or key == "name" and path == "interface"
    }
    observed = []
    result = object()
    constructor_signature = inspect.signature(component)

    def construct(*args, **kwargs):
        bound = constructor_signature.bind(*args, **kwargs)
        values = dict(bound.arguments)
        # kwargs-only material and recorder components retain generic internals.
        for key in tuple(values):
            if constructor_signature.parameters[key].kind is inspect.Parameter.VAR_KEYWORD:
                values.update(values.pop(key))
        observed.append(values)
        return result

    monkeypatch.setattr(
        importlib.import_module(component.__module__), component.__name__, construct
    )
    if component.__name__ in factory.__func__.__globals__:
        monkeypatch.setitem(factory.__func__.__globals__, component.__name__, construct)
    registered = []
    monkeypatch.setattr(owner, "add", lambda value: registered.append(value))
    for resolver in ("_resolve_section", "_resolve_transformation", "_resolve_materials"):
        if hasattr(owner, resolver):
            monkeypatch.setattr(owner, resolver, lambda value: value)
    assert factory(**arguments) is result
    assert registered == [result]
    assert len(observed) == 1
    for key, value in arguments.items():
        assert observed[0][key] is value, (path, name, key)
    with pytest.raises(TypeError):
        factory(**arguments, misspelled_option=True)


@pytest.mark.parametrize(
    "path,name", [(path, name) for path, name in BUILTIN_CASES if path.startswith("section")]
)
def test_section_factories_preserve_context_aware_creation(path, name, monkeypatch):
    factory = get_factory(path, name)
    arguments = {key: object() for key in inspect.signature(factory).parameters}
    observed = []
    result = object()

    def create(section_type, **kwargs):
        observed.append((section_type, kwargs))
        return result

    monkeypatch.setattr(factory.__self__._manager, "create_section", create)
    assert factory(**arguments) is result
    assert len(observed) == 1
    assert isinstance(observed[0][0], str)
    assert observed[0][1] == arguments


def test_material_name_alias_and_recorder_selection_aliases():
    model = Model()
    material = model.material.nd.elastic_isotropic(name="soil", E=1e5, nu=0.3)
    assert model.material.get_by_name("soil") is material
    region = model.region.element(user_name="soil_region")
    canonical = model.recorder.vtkhdf(file_base_name="response", resp_types=["disp"], region=region)
    alias = model.recorder.vtkhdf(file_base_name="response", resp_types=["disp"], regions=region)
    assert canonical.to_tcl() == alias.to_tcl()
    with pytest.raises(ValueError, match="only one"):
        model.recorder.vtkhdf(
            file_base_name="response", resp_types=["disp"], region=region, regions=region
        )


def test_core_only_keeps_deliberately_generic_keyword_apis():
    core = Path(__file__).resolve().parents[2] / "src/femora/core"
    flexible = {
        ("assembler.py", "plot"),
        ("meshpart_base.py", "plot"),
        ("element_base.py", "update_element_params"),
        ("event_bus.py", "emit"),
        ("section_manager.py", "create_section"),
        ("tagged_component_manager.py", "create"),
    }
    for path in core.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (
                isinstance(node, ast.FunctionDef)
                and not node.name.startswith("_")
                and node.args.kwarg
            ):
                assert (path.name, node.name) in flexible, (path, node.name)


@pytest.mark.parametrize("name", BUILTIN_FAMILIES["analysis.numberer"])
def test_numberer_concrete_types_preserve_cache(name):
    manager = Model().analysis.numberer
    factory = getattr(manager, name)
    expected = typing.get_type_hints(factory, localns=annotation_namespace(factory.__module__))[
        "return"
    ]
    instance = factory()
    assert isinstance(instance, expected)
    assert factory() is instance
    manager.clear()
    assert factory() is not instance
