# Core Editor Contracts

`core_factories.py` checks concrete return types through the public `Model`
manager chains without executing a model. `core_factories_invalid.py` contains
six intentional errors: five unknown keywords and one wrong value type.

Run the automated gate with Pyright installed:

```sh
python -m pytest tests/core/test_static_factory_types.py -q
```

Alternatively, set `FEMORA_PYRIGHT_JS` to the bundled Pyright `index.js`
entrypoint; this requires Node. The gate skips when neither is available.
Directly running Pyright on `tests/typing/pyrightconfig.json` must report exactly
the six intentional errors and no errors in the valid fixture.

## Factory Standard

- Give built-in factories explicit parameter names, defaults, and annotations.
- Return the concrete component type so editors expose its members.
- Preserve existing positional arguments and supported aliases; make newly
  exposed options keyword-only where the previous API accepted only keywords.
- Delegate validation and construction to the component, and register the same
  object with its owning manager. Do not duplicate numerical behavior.
- Keep generic plugin factories and visualization/event forwarding flexible.
- Document parameters and examples in source docstrings, the source for the
  generated API reference. Extend `test_factory_signatures.py` for new factories.

The installed package includes `femora/py.typed`; separate generated stubs are
not needed for these source-defined APIs. Unknown built-in factory keywords now
raise `TypeError` instead of being silently swallowed by a component's `**kwargs`.
