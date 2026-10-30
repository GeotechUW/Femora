"""Build the two files the Femora Gemini Gem uses, from the repository.

    python -I agent/build_knowledge.py

Writes, under agent/build/ (git-ignored; delete and rebuild any time):
  femora_context.md    the concept guides followed by the whole API reference: the file uploaded to the Gem
  gem_instructions.md  the rules pasted into the Gem's instructions box

The API reference is extracted from a live Model (every public callable: signature, docstring, return type) and the
concept guides are copied from website/docs/concepts/. Needs nothing beyond Femora's own dependencies. The Femora
commit the files were built from is the last commit that touched src/ or website/docs/ ("+dirty" = uncommitted
changes there); it is written on the first line of femora_context.md. Output uses LF line endings on every OS.

Record of v1, the files the live Gem was built from:
  Femora commit 181ae6e4 (2026-10-23); 604 API entries; about 117k tokens (characters / 4), about 123k prompt tokens
  measured on Gemini 2.5 Flash. sha256, first 16 hex characters, after replacing Windows line endings (CRLF) with LF:
    femora_context.md    73170e3dc49a6b68
    gem_instructions.md  a906f827fe09deb9
  gem_instructions.md contains rule 9 (do not assemble unless asked), added after the first upload, so the live Gem
  may not have it. To rebuild v1: check out the commit that added this file, run it, and compare the hashes.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import subprocess
import sys
import types
import typing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
sys.path.insert(0, str(ROOT / "src"))

# Code from the removed API: the build reports any mention in the context (it does not change the output).
STALE_PATTERNS = [
    r'MeshMaker',
    r'\bfm\.(process|meshPart|meshpart|material|element|assembler|constraint|actions|region|damping|pattern|recorder|mask|mass|section|transformation|timeSeries|analysis)\.',
    r'from femora\.gui',
    r'femora\.gui',
    r'PySide6|PyQt',
]


# ---------------------------------------------------------------- 1. the API, extracted from a live Model
SKIP_ATTRS = {"model", "events"}  # back-references / event plumbing
MAX_DEPTH = 6


def _source(obj) -> tuple[str | None, int | None]:
    try:
        fn = inspect.unwrap(obj)
        file = inspect.getsourcefile(fn)
        line = inspect.getsourcelines(fn)[1]
        return Path(file).resolve().relative_to(ROOT).as_posix(), line
    except (TypeError, OSError, ValueError):
        return None, None


_ADDR_RE = re.compile(r"<(?:[\w.]+\.)?(\w+) object at 0x[0-9A-Fa-f]+>")


def _clean(text: str | None) -> str | None:
    """Drop memory addresses from reprs so entries hash the same on every run."""
    return None if text is None else _ADDR_RE.sub(lambda m: f"<{m.group(1)}>", text)


def _entry(path: str, obj) -> dict:
    try:
        sig = inspect.signature(obj)
        params = [
            {
                "name": p.name,
                "kind": p.kind.name,
                "default": None if p.default is p.empty else _clean(repr(p.default)),
                "annotation": None if p.annotation is p.empty else str(p.annotation),
            }
            for p in sig.parameters.values()
            if p.name not in ("self", "cls")
        ]
        signature = _clean(str(sig))
        returns = None if sig.return_annotation is sig.empty else str(sig.return_annotation)
    except (TypeError, ValueError):
        params, signature, returns = [], "(...)", None
    doc = inspect.getdoc(obj) or ""
    file, line = _source(obj)
    kind = "class" if inspect.isclass(obj) else "function"
    entry = {
        "path": path,
        "kind": kind,
        "signature": signature,
        "params": params,
        "returns": returns,
        "doc": doc,
        "file": file,
        "line": line,
        "has_var_kwargs": any(p["kind"] == "VAR_KEYWORD" for p in params),
    }
    # Hash only what the assistant sees, so unrelated edits do not change it.
    basis = json.dumps([path, signature, returns, doc], sort_keys=True)
    entry["hash"] = hashlib.sha256(basis.encode()).hexdigest()[:16]
    return entry


def walk(obj, path: str, out: dict, seen: set, depth: int = 0) -> None:
    if depth > MAX_DEPTH or id(obj) in seen:
        return
    seen.add(id(obj))
    for name in sorted(dir(obj)):
        if name.startswith("_") or name in SKIP_ATTRS:
            continue
        child = f"{path}.{name}"
        try:
            value = getattr(obj, name)
        except Exception:
            # A property that needs runtime state (e.g. an assembled mesh):
            # fall back to the class named by its return annotation.
            walk_class(_property_type(obj, name), child, out, seen, depth + 1)
            continue
        if inspect.ismethod(value) or inspect.isfunction(value):
            out[child] = _entry(child, value)
        elif inspect.isclass(value) or isinstance(value, (types.ModuleType, type(None), str, int, float, bool, list, dict, tuple, set)):
            continue
        elif type(value).__module__.startswith("femora"):
            if callable(value):  # factory object with __call__, e.g. model.region.element(...)
                out[child] = _entry(child, value)
            walk(value, child, out, seen, depth + 1)


def _property_type(obj, name):
    prop = getattr(type(obj), name, None)
    if not isinstance(prop, property) or prop.fget is None:
        return None
    try:
        hint = typing.get_type_hints(prop.fget).get("return")
    except Exception:
        return None
    return hint if inspect.isclass(hint) else None


def walk_class(cls, path: str, out: dict, seen: set, depth: int) -> None:
    if cls is None or depth > MAX_DEPTH or cls in seen:
        return
    seen.add(cls)
    for name, member in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if inspect.isfunction(member):
            out[f"{path}.{name}"] = _entry(f"{path}.{name}", member)
        elif isinstance(inspect.getattr_static(cls, name, None), property):
            walk_class(_property_type(cls, name), f"{path}.{name}", out, seen, depth + 1)


def walk_module(module, path: str, out: dict) -> None:
    names = getattr(module, "__all__", None) or [n for n in dir(module) if not n.startswith("_")]
    for name in names:
        value = getattr(module, name, None)
        child = f"{path}.{name}"
        if inspect.isfunction(value):
            out[child] = _entry(child, value)
        elif inspect.isclass(value):
            out[child] = _entry(child, value)
            for mname, member in inspect.getmembers(value, inspect.isfunction):
                if not mname.startswith("_"):
                    out[f"{child}.{mname}"] = _entry(f"{child}.{mname}", member)
        elif isinstance(value, types.ModuleType) and value.__name__.startswith("femora") and value.__name__ != module.__name__:
            if f"{path}." not in child[: len(path) + 1] or child.count(".") < 3:
                walk_module(value, child, out)


def extract() -> dict:
    """Walk a live Model and a few modules; return {"commit": ..., "entries": {path: entry}}."""
    import femora
    from femora import Model

    model = Model(model_name="api_extract")
    entries: dict[str, dict] = {}
    walk(model, "model", entries, set())
    for name in ("runtime", "jobs", "results", "tasks"):
        mod = getattr(femora, name, None)
        if mod is not None:
            walk_module(mod, f"femora.{name}", entries)
    import femora.tools.buildings as buildings

    walk_module(buildings, "femora.tools.buildings", entries)
    for name in ("Model", "Workflow", "execute", "submit"):
        entries[f"femora.{name}"] = _entry(f"femora.{name}", getattr(femora, name))

    # Version of the knowledge = last commit that touched what it is built from (the library and the
    # docs), so unrelated commits do not change it. "+dirty" marks uncommitted changes to those inputs.
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    commit = git("log", "-1", "--format=%H", "--", "src", "website/docs")
    if git("status", "--porcelain", "--", "src", "website/docs"):
        commit += "+dirty"
    return {"commit": commit, "entries": entries}


# ---------------------------------------------------------------- 2. the two files
CONCEPTS = ["model", "building-blocks", "managers", "tags-and-ids", "mesh-parts", "regions-and-groups",
            "assembly", "assembled-model", "constraints", "damping", "interfaces", "loading",
            "analysis", "process", "recorders-and-actions"]

INSTRUCTIONS = """You write Python code for Femora, a library that builds OpenSees finite element models.
The attached file `femora_context.md` is the complete, current reference: first the concept guides
(how Femora is organized and in what order things are built), then the full API (every callable with
its exact signature and documentation). Read it as the source of truth.

Rules
1. Use ONLY functions and keyword arguments that exist in the API section. Never invent one. If something
   the user needs does not exist, say so and describe what the closest existing pieces can do.
2. Everything is called through a model object: `from femora import Model` then
   `model = Model(model_name="...")`, e.g. `model.material.nd.elastic_isotropic(...)`. The old
   MeshMaker / `fm.material.create_material` style no longer exists; never use it.
3. Work out how pieces connect from the signatures: what a function returns is what other functions
   accept as arguments. The concept guides say what must come before what (for example some boundary
   conditions need an assembled mesh).
4. Return only what was asked. A soil request gets only soil, a pile only the pile, and so on. Do not add
   loads, analysis, recorders, boundary conditions or other components unless asked. Give a complete
   runnable model only when the user asks for one.
5. Do not make physics choices silently (boundary conditions, damping values, materials, units). Use what
   the user gave. If something important is missing, ask one short question, or write the code and list
   your assumptions in a few words. If no material is given, use linear elastic and say so.
6. Femora does not convert units. State the unit system your numbers assume unless the user gave one.
7. If the request builds on code that already exists, state which names it relies on.
8. Put the code in one ```python block and keep the prose short.
9. Do not call the assembler (create_section, assemble) unless the user asks for it or a requested feature
   needs an assembled mesh.
"""


def api_section(entries: dict) -> str:
    groups: dict[str, list] = {}
    for path, e in entries.items():
        top = ".".join(path.split(".")[:2]) if path.startswith("model.") else ".".join(path.split(".")[:3])
        groups.setdefault(top, []).append(e)
    out = ["# Femora API reference", "",
           "Every public callable. `model.` entries are called on a `Model` instance.", ""]
    for top in sorted(groups):
        out.append(f"## {top}")
        for e in sorted(groups[top], key=lambda x: x["path"]):
            doc = re.split(r"\n(?:Raises|Returns|Examples?|Notes?|See Also):?\s*\n", e["doc"])[0].strip()
            out.append(f"### `{e['path']}`\n```\n{e['path']}{e['signature']}\n```")
            if doc:
                out.append(doc)
            out.append("")
    return "\n".join(out)


def main() -> None:
    api = extract()
    short = api["commit"][:8] + ("+dirty" if api["commit"].endswith("+dirty") else "")
    parts = ["# Femora: concept guides", ""]
    for name in CONCEPTS:
        text = (ROOT / "website" / "docs" / "concepts" / f"{name}.md").read_text(encoding="utf-8")
        text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
        parts.append(f"\n<!-- concept: {name} -->\n{text.strip()}\n")
    parts.append(api_section(api["entries"]))
    body = "\n".join(parts)

    hits = [(p, m.group(0)) for p in STALE_PATTERNS for m in re.finditer(p, body)]
    BUILD.mkdir(exist_ok=True)
    # write bytes, not text: identical files on every OS (no CRLF translation on Windows)
    (BUILD / "femora_context.md").write_bytes(
        (f"<!-- generated from commit {short} -->\n" + body).encode("utf-8"))
    (BUILD / "gem_instructions.md").write_bytes(INSTRUCTIONS.encode("utf-8"))
    size = len(body)
    print(f"femora_context.md: {size // 1000} k chars (~{size // 4000} k tokens), commit {short}")
    print(f"stale old-API mentions in the context: {len(hits)}")
    for p, t in hits[:10]:
        print("   ", t)
    print("gem_instructions.md written")


if __name__ == "__main__":
    sys.exit(main())
