"""Build the upload bundle: a handful of markdown files that carry the whole Femora knowledge.

    python -I agent/build_knowledge.py            # rebuild only what is out of date (and re-extract the API if src changed)
    python -I agent/build_knowledge.py --check    # report what is out of date, change nothing (exit 1 if anything is)
    python -I agent/build_knowledge.py --force    # rebuild every file

Output: agent/build/bundle/   (git-ignored; delete it any time and rebuild)
  SKILL.md           rules, build order, a map of the whole API, and a guide to the other files. It starts with the
                     frontmatter a Claude skill needs, so the bundle uploads as a skill as it is (SKILL.md plus the
                     four numbered files; leave out instructions.txt and the manifest)
  01_api_model.md    exact signatures and docs for everything called on a Model
  02_api_other.md    the rest of the API (jobs, results, runtime, ready-made buildings)
  03_concepts.md     the concept guides from website/docs/concepts
  04_examples.md     worked examples (only if there are example pages)
  instructions.txt   short rules to paste into a platform's instructions box (no stamp, so it pastes cleanly)
  bundle_manifest.json   what each file was built from, with hashes

What goes where is set in CONFIG near the top of this file, so changing contents never needs a code change.

Every .md file starts with a note saying which commit (and commit date) of which inputs it was built from, and
the commit of this generator. The commit DATE is used, not the clock, so unchanged inputs give identical bytes.
"+ uncommitted changes" means the inputs differ from that commit.

A file is out of date when the content of its inputs, its part of CONFIG, or the generator changed.

The first version of this file (see the git history) built the two files the live Gem uses, femora_context.md and
gem_instructions.md; its docstring records their hashes.
"""

from __future__ import annotations

import argparse
import ast
import copy
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
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------- shared helpers and text (self-contained)
BOOKKEEPING = {"add", "clear", "get", "get_all", "get_by_name", "get_by_tag", "get_by_category", "remove",
               "set_tag_start", "resolve", "to_tcl", "create", "get_available_types", "get_static_types",
               "get_transient_types"}

# Secondary or repetitive groups: listed by name only in the map (signatures stay in the group file).
COMPACT_GROUPS = {"femora-jobs", "femora-results", "femora-tools-buildings", "model-analysis", "model-mask"}

GOTCHAS = """\
These were checked against Femora while building this skill; trust them over guesses.

1. `Model` takes keyword arguments only: `Model(model_name="...", model_path="...")`.
2. Unknown keyword arguments to the built-in factories raise `TypeError`. Pass only parameters that are
   listed in the reference for that function.
3. Building mesh parts needs no assembly. `model.assembler.create_section(meshparts=[...], ...)` groups mesh
   parts and `model.assembler.assemble()` builds the assembled mesh. Points are merged only inside one
   section: parts in different sections keep separate nodes at the same location, so tie them yourself
   (for example `model.constraint.mp.equal_dof_between_meshparts(...)`).
4. These need an assembled mesh, so assemble first: `model.constraint.sp.fix_macro_*`,
   `model.constraint.mp.laminar_boundary`, `model.constraint.mp.equal_dof_between_meshparts`, `model.mask.*`.
5. A beam-solid interface (`model.interface.beam_solid_interface`) is declared before assembling.
6. Femora does not convert units. The shipped examples use kN, m, s, with density in Mg/m^3.
7. Building generators (`femora.tools.buildings.*`): `build(model, ...)` only creates the building's mesh
   parts. These methods raise "Mesh must be assembled" unless `model.assembler.assemble()` ran first:
   `apply_fixed_base`, `create_rigid_diaphragms`, `create_gravity_pattern`, `create_pushover_pattern`, and the
   creation of the building's recorders.
"""


def short(doc: str, limit: int = 110) -> str:
    first = re.split(r"\n\s*\n", doc.strip())[0].replace("\n", " ").strip() if doc.strip() else ""
    m = re.match(r"(.+?[.!?])(\s|$)", first)
    s = m.group(1) if m else first
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def group_of(path: str) -> str:
    p = path.split(".")
    if p[0] == "model":
        return "model-" + p[1] if len(p) > 2 else "model-core"
    if p[0] == "femora" and len(p) >= 3 and p[1] == "tools":
        return "femora-tools-buildings"
    if p[0] == "femora" and len(p) >= 3:
        return "femora-" + p[1]
    return "femora-core"


def param_names(e: dict) -> str:
    return ", ".join(p["name"] + ("=…" if p["default"] is not None else "")
                     for p in e["params"] if p["kind"] != "VAR_KEYWORD") + \
           (", **kwargs" if e["has_var_kwargs"] else "")


def docs_pages(section: str, exclude=()) -> list[str]:
    """Every page in website/docs/<section>/, in the order of the site navigation (website/mkdocs.yml); pages the
    navigation does not mention yet come last, alphabetically. Nothing is listed by hand, so a new page is picked up
    automatically."""
    present = {p.stem for p in (ROOT / "website" / "docs" / section).glob("*.md")}
    nav = ROOT / "website" / "mkdocs.yml"
    ordered: list[str] = []
    if nav.exists():
        for name in re.findall(section + r"/([A-Za-z0-9_-]+)\.md", nav.read_text(encoding="utf-8")):
            if name in present and name not in ordered:
                ordered.append(name)
    ordered += sorted(present - set(ordered))
    return [n for n in ordered if n not in set(exclude)]


def concept_names(exclude=()) -> list[str]:
    return docs_pages("concepts", exclude)


RULES = """1. Use ONLY functions and keyword arguments that exist in the API files. Never invent one. If something
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

# ---------------------------------------------------------------- configuration
# BEGIN CONFIG
# include_hints: hand-written "gotchas" (facts learned while testing). OFF = only generated content and the behavior
#   rules. Turn on only to measure how much hand-tuning adds, never for a headline score.
# api_files: which API groups go into which file; a file takes every group whose name starts with one of its
#   prefixes. Groups: model-<manager>, femora-core, femora-jobs, femora-results, femora-runtime, femora-tasks,
#   femora-tools-buildings.
# concepts_exclude / examples_exclude: concept and example pages are discovered automatically from website/docs, in the
#   order of website/mkdocs.yml; name a page here (without .md) only to leave it OUT.
# skill_name / skill_description: the frontmatter at the top of SKILL.md. Name: lowercase letters, numbers and hyphens,
#   at most 64 characters, no "anthropic" or "claude". Description: what the skill does and when to use it, in third
#   person, at most 1024 characters (some sources say claude.ai accepts 200, so keep it short). Checked at build time.
# github_repo / docs_url: where the links point; empty = derived (git remote "origin"; https://femora.io/docs).
# budgets_tokens: warn when a file grows past this many tokens (characters / 4).
CONFIG = {'include_hints': False,
 'api_files': {'01_api_model.md': ['model-'], '02_api_other.md': ['femora-']},
 'concepts_exclude': [],
 'examples_exclude': [],
 'github_repo': '',
 'docs_url': '',
 'skill_name': 'femora',
 'skill_description': 'Writes and explains Python code for Femora, a library that builds OpenSees finite element models '
                      '(soil, piles, buildings, assembly, constraints, loads). Use for any Femora modeling request.',
 'budgets_tokens': {'SKILL.md': 14000,
                    '01_api_model.md': 60000,
                    '02_api_other.md': 30000,
                    '03_concepts.md': 70000,
                    '04_examples.md': 40000}}
# END CONFIG
OUT = HERE / "build" / "bundle"
API_JSON = HERE / "build" / "api.json"
API_STAMP = HERE / "build" / "api.src_hash"
# The generator's CODE decides whether every file is out of date; CONFIG is hashed per file instead (only the part a
# file uses), so editing one list does not rebuild everything. generator_hash() leaves the CONFIG block out.
GENERATOR = ["agent/build_knowledge.py"]
GENERATOR_STAMP = GENERATOR


def generator_hash() -> str:
    text = chr(10).join(Path(__file__).read_text(encoding="utf-8").splitlines())
    start, end = text.index("# BEGIN CONFIG"), text.index("# END CONFIG")
    return hashlib.sha256((text[:start] + text[end:]).encode()).hexdigest()


BUILD_ORDER = """\
Everything is called through a `Model` instance. What a function returns is what other functions accept.
Typical order: material -> element -> mesh part (with an optional region) -> assemble -> constraints and
loads -> recorders -> analysis steps. Request only the parts the user asked for."""


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


# ---------------------------------------------------------------- git and hashing
def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def commit_info(paths: list[str]) -> dict:
    """Last commit touching paths: {"hash", "date", "dirty"}; hash is None if they were never committed."""
    if not paths:
        return {"hash": None, "date": None, "dirty": False}
    out = git("log", "-1", "--format=%H %cs", "--", *paths)
    dirty = bool(git("status", "--porcelain", "--", *paths))
    if not out:
        return {"hash": None, "date": None, "dirty": True}
    h, d = out.split()
    return {"hash": h, "date": d, "dirty": dirty}


def files_under(paths: list[str]) -> list[Path]:
    found = []
    for p in paths:
        path = ROOT / p
        if path.is_dir():
            found += [f for f in sorted(path.rglob("*"))
                      if f.is_file() and f.suffix in (".py", ".md", ".yaml") and "__pycache__" not in f.parts]
        elif path.is_file():
            found.append(path)
    return found


def content_hash(paths: list[str]) -> str:
    h = hashlib.sha256()
    for f in files_under(paths):
        h.update(f.relative_to(ROOT).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))  # same hash on Windows and Linux checkouts
    return h.hexdigest()


def stamp_text(info: dict) -> str:
    if info["hash"] is None:
        return "uncommitted files"
    return f"commit `{info['hash'][:8]}` ({info['date']})" + (" + uncommitted changes" if info["dirty"] else "")


# ---------------------------------------------------------------- examples
# An example is a website page (website/docs/examples/<slug>.md) whose code lives in examples/*.py and is pulled
# in with `--8<-- "path:section"` lines. The bundle does not copy the code: it describes each example, lists the
# calls the script makes in order, and links to the exact lines on GitHub, pinned to a commit.
INCLUDE_RE = re.compile(r'^(\s*)--8<--\s+"([^":]+)(?::([^"]+))?"\s*$')
ROOT_NAMES = {"model", "runtime", "fm", "femora", "jobs", "results"}
WARNINGS: list[str] = []
_PIN_CACHE: dict[str, str | None] = {}


def pinned_hash(path: str) -> str | None:
    """Last commit that changed this file; warns if that commit is not on a remote branch (the link would 404)."""
    if path not in _PIN_CACHE:
        h = commit_info([path])["hash"]
        if h is None:
            WARNINGS.append(f"{path} is not committed: its GitHub link points at the main branch instead")
        elif not git("branch", "-r", "--contains", h):
            WARNINGS.append(f"commit {h[:8]} of {path} is not on any remote branch: its GitHub link will not resolve "
                            "until it is pushed")
        _PIN_CACHE[path] = h
    return _PIN_CACHE[path]


def blob_url(cfg: dict, path: str, first: int | None = None, last: int | None = None) -> str:
    url = f"{cfg['github_repo']}/blob/{pinned_hash(path) or 'main'}/{path}"
    return url + (f"#L{first}-L{last}" if first else "")


def section_lines(src: str) -> dict[str, tuple[int, int]]:
    """{section: (first line, last line)} from `# --8<-- [start:name]` / `[end:name]` markers."""
    start: dict[str, int] = {}
    found: dict[str, tuple[int, int]] = {}
    for i, line in enumerate(src.splitlines(), 1):
        m = re.search(r"--8<--\s+\[(start|end):([^\]]+)\]", line)
        if m and m.group(1) == "start":
            start[m.group(2)] = i + 1
        elif m and m.group(2) in start:
            found[m.group(2)] = (start[m.group(2)], i - 1)
    return found


def ordered_calls(src: str) -> list[str]:
    """Distinct API calls (model.x.y(...), runtime.z(...)) in the order the script first makes them."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    calls: list[str] = []
    for node in sorted((n for n in ast.walk(tree) if isinstance(n, ast.Call)), key=lambda n: (n.lineno, n.col_offset)):
        parts, cur = [], node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name) and cur.id in ROOT_NAMES and parts:
            path = ".".join(reversed(parts)) if cur.id == "model" else cur.id + "." + ".".join(reversed(parts))
            if path not in calls:
                calls.append(path)
    return calls


def load_example(slug: str) -> dict:
    page = f"website/docs/examples/{slug}.md"
    text = strip_front_matter((ROOT / page).read_text(encoding="utf-8"))
    scripts = []
    for line in text.splitlines():
        m = INCLUDE_RE.match(line)
        if m and m.group(2).endswith(".py") and m.group(2) not in scripts:
            scripts.append(m.group(2))
    main = next((s for s in scripts if not s.endswith("_postprocess.py")), None)
    post = next((s for s in scripts if s.endswith("_postprocess.py")), None)
    if main and post is None and (ROOT / main.replace(".py", "_postprocess.py")).exists():
        post = main.replace(".py", "_postprocess.py")
    src = (ROOT / main).read_text(encoding="utf-8").replace("\r\n", "\n") if main else ""
    # the title readers see is the page's; the script's own title cell is only a fallback
    title = re.search(r"^#\s+(.+)$", text, flags=re.M) or re.search(r"^# # (.+)$", src, flags=re.M)
    desc = ""
    cell = re.search(r"^# # .+\n#\n((?:#.*\n)+)", src, flags=re.M)   # first paragraph of the script's markdown cell
    if cell:
        desc = " ".join(l[1:].strip() for l in cell.group(1).splitlines() if l.strip("# ")).split("  ")[0]
    if not desc:  # fall back to the page's first plain paragraph
        for para in re.split(r"\n\s*\n", text):
            p = para.strip()
            if p and not p.startswith(("#", "!", "<", "|", "`", "-", "*", ">", "=", "?", "-->")) and "--8<--" not in p:
                desc = " ".join(p.split())
                break
    return {"slug": slug, "page": page, "main": main, "post": post, "scripts": scripts,
            "title": title.group(1).strip() if title else slug, "desc": desc[:400],
            "calls": ordered_calls(src),
            "inputs": [page] + scripts + ([post] if post and post not in scripts else [])}


def topics(calls: list[str], limit: int = 9) -> str:
    """The API areas an example touches, in order of first use (for the guide's one-line summary)."""
    seen: list[str] = []
    for c in calls:
        p = c.split(".")
        if len(p) == 1:
            continue  # model-level helpers such as set_results_folder say nothing about the example
        if p[0] in ROOT_NAMES - {"model"}:
            t = c
        elif p[0] in ("material", "element", "meshpart", "constraint", "section") and len(p) > 2:
            t = ".".join(p[:2])
        else:
            t = p[0]
        if t not in seen:
            seen.append(t)
    return ", ".join(seen[:limit])


def examples_guide(ex: list[dict], cfg: dict, examples_text: str) -> str:
    """One entry per example: title, where its section starts in 04_examples.md, description, areas used, links."""
    lines = examples_text.splitlines()
    out = []
    for e in ex:
        links = [f"docs: {cfg['docs_url']}/examples/{e['slug']}/"]
        if e["main"]:
            links.append(f"code: {blob_url(cfg, e['main'])}")
        if e["post"]:
            links.append(f"post-processing: {blob_url(cfg, e['post'])}")
        start = next((i for i, l in enumerate(lines, 1) if l == f"<!-- example: {e['slug']} -->"), None)
        where = f", line {start} of `04_examples.md`" if start else ""
        desc = f" {e['desc']}" if e["desc"] else ""
        uses = f" Uses: {topics(e['calls'])}." if e["calls"] else ""
        out.append(f"- **{e['title']}** (`{e['slug']}`{where}).{desc}{uses}\n  " + "; ".join(links))
    return "\n".join(out)


def clean_page(text: str) -> str:
    """Drop website widgets (embedded frames, buttons) and push headings down so they nest under the example."""
    text = re.sub(r"<(div|figure|iframe|script|style)\b.*?</\1>", "", text, flags=re.S)
    text = re.sub(r"^\s*</?(div|figure|iframe)[^>]*>\s*$", "", text, flags=re.M)
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and re.match(r"^#{1,3}\s", line):
            line = "###" + line
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def build_examples(f: dict, head: str, cfg: dict) -> str:
    ex = f["ex"]
    out = ["# Femora worked examples", "", head,
           "The full code is not copied here. Each example has a link to its code on GitHub, pinned to a commit, "
           "and its explanation page. Read the explanation and the order of calls to see how the pieces fit; if you "
           "need more than that and can open web pages, follow the code links. Examples show the usual order of steps: "
           "never copy parts the user did not ask for.", "", "## Contents", ""]
    out += [f"- {e['slug']}: {e['title']}" for e in ex] + [""]
    cache: dict[str, dict] = {}
    for e in ex:
        out += ["", "---", "", f"<!-- example: {e['slug']} -->", f"## {e['title']} (`{e['slug']}`)", "", e["desc"], "",
                f"- Docs page: {cfg['docs_url']}/examples/{e['slug']}/"]
        if e["main"]:
            out.append(f"- Full code: {blob_url(cfg, e['main'])}")
        if e["post"]:
            out.append(f"- Post-processing code: {blob_url(cfg, e['post'])}")
        out += ["", "Calls in the order the script first makes them:", "",
                " -> ".join(f"`{c}`" for c in e["calls"]) or "(none found)", "", "### Explanation", ""]
        text = clean_page(strip_front_matter((ROOT / e["page"]).read_text(encoding="utf-8")))
        for line in text.splitlines():
            m = INCLUDE_RE.match(line)
            if not m:
                out.append(line)
                continue
            indent, path, section = m.group(1), m.group(2), m.group(3)
            if not path.endswith(".py"):
                continue  # an image included by the docs site
            if path not in cache:
                cache[path] = section_lines((ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n"))
            span = cache[path].get(section) if section else None
            label = f"`{Path(path).name}`" + (f", section `{section}`" if section else "")
            where = f" (lines {span[0]}-{span[1]})" if span else ""
            out.append(f"{indent}> Code for this step: {label}{where}: {blob_url(cfg, path, *(span or (None, None)))}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- plan
def plan(cfg: dict) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for name, prefixes in cfg["api_files"].items():
        files[name] = {"kind": "api", "inputs": ["src"], "show": ["src/"], "cfg": prefixes}
    files["03_concepts.md"] = {"kind": "concepts", "show": ["website/docs/concepts/"], "cfg": cfg["concepts"],
                               "inputs": ["website/docs/concepts"]}   # the whole folder: a new or changed page rebuilds it
    if cfg.get("examples"):
        ex = [load_example(s) for s in cfg["examples"]]
        files["04_examples.md"] = {"kind": "examples", "ex": ex, "show": ["website/docs/examples/", "examples/"],
                                   "inputs": sorted({p for e in ex for p in e["inputs"]}),
                                   "cfg": {"examples": cfg["examples"], "repo": cfg["github_repo"],
                                           "docs": cfg["docs_url"]}}
    files["SKILL.md"] = {"kind": "start", "inputs": ["src"], "show": ["src/"],
                                 "cfg": {"hints": cfg["include_hints"], "api_files": cfg["api_files"],
                                         "skill": [cfg["skill_name"], cfg["skill_description"]]}}
    files["instructions.txt"] = {"kind": "instructions", "inputs": [], "show": [], "cfg": None}
    return files


def recipe_keys(files: dict[str, dict], gen_hash: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, f in files.items():
        if f["kind"] == "start":
            continue
        keys[name] = hashlib.sha256(json.dumps(
            {"in": content_hash(f["inputs"]), "cfg": f["cfg"], "gen": gen_hash}, sort_keys=True).encode()).hexdigest()[:16]
    start = files["SKILL.md"]  # the start file describes the others, so it depends on all of them
    keys["SKILL.md"] = hashlib.sha256(json.dumps(
        {"in": content_hash(start["inputs"]), "cfg": start["cfg"], "gen": gen_hash, "deps": keys},
        sort_keys=True).encode()).hexdigest()[:16]
    return keys


# ---------------------------------------------------------------- content
def header(name: str, f: dict, info: dict, gen: dict) -> str:
    inputs = ", ".join(f"`{p}`" for p in f["show"])
    gen_text = stamp_text(gen) if gen["hash"] else "uncommitted"
    return (f"> **Generated file. Do not edit by hand.** Built from {stamp_text(info)} of {inputs}.\n"
            f"> Generator `agent/build_knowledge.py` at {gen_text}. "
            f"Rebuild with `python -I agent/build_knowledge.py`.\n\n")


def fmt_entry(e: dict) -> str:
    doc = re.split(r"\n(?:Raises|Returns|Examples?|Notes?|See Also):?\s*\n", e["doc"])[0].strip()
    lines = [f"### `{e['path']}`", "```", f"{e['path']}{e['signature']}", "```"]
    if doc:
        lines.append(doc)
    return "\n".join(lines) + "\n"


def groups_for(api: dict, prefixes: list[str]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for path in sorted(api["entries"]):
        g = group_of(path)
        if any(g.startswith(p) for p in prefixes):
            groups.setdefault(g, []).append(api["entries"][path])
    return dict(sorted(groups.items()))


def build_api(name: str, f: dict, api: dict, head: str) -> str:
    groups = groups_for(api, f["cfg"])
    toc = "\n".join(f"- {g}: {len(items)} entries" for g, items in groups.items())
    out = [f"# Femora API reference ({name})", "", head, "Exact signatures and documentation. Call `model.` entries on a "
           "`Model` instance.", "", "## Contents", "", toc, ""]
    for g, items in groups.items():
        out += [f"## {g}", ""] + [fmt_entry(e) for e in items]
    return "\n".join(out)


def strip_front_matter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text.replace("\r\n", "\n"), flags=re.S).strip() + "\n"


def build_concepts(f: dict, head: str) -> str:
    pages = []
    for c in f["cfg"]:
        text = strip_front_matter((ROOT / "website" / "docs" / "concepts" / f"{c}.md").read_text(encoding="utf-8"))
        title = re.search(r"^#\s+(.+)$", text, flags=re.M)
        pages.append((c, title.group(1) if title else c, text))
    toc = "\n".join(f"- {c}: {t}" for c, t, _ in pages)
    out = ["# Femora concept guides", "", head, "## Contents", "", toc, ""]
    for c, _, text in pages:
        out += ["", "---", "", f"<!-- concept: {c} (website/docs/concepts/{c}.md) -->", text]
    return "\n".join(out)


def concepts_guide(cfg: dict, concepts_text: str) -> str:
    """One line per concept guide: its title, its own ## headings, and where it starts. Only what the page itself says."""
    lines = concepts_text.splitlines()
    out = []
    for c in cfg["concepts"]:
        text = strip_front_matter((ROOT / "website" / "docs" / "concepts" / f"{c}.md").read_text(encoding="utf-8"))
        title = re.search(r"^#\s+(.+)$", text, flags=re.M)
        heads, fenced = [], False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
            if not fenced and line.startswith("## "):
                heads.append(line[3:].strip())
        start = next((i for i, l in enumerate(lines, 1) if l.startswith(f"<!-- concept: {c} ")), None)
        where = f", line {start} of `03_concepts.md`" if start else ""
        sections = f" Sections: {'; '.join(heads[:16])}." if heads else ""
        out.append(f"- **{title.group(1) if title else c}** (`{c}`{where}).{sections}")
    return "\n".join(out)


def rules_text() -> str:
    return RULES.strip()


def build_start(files: dict, built: dict[str, str], api: dict, cfg: dict, head: str) -> str:
    describe = {"api": "exact signatures and documentation", "concepts": "the concept guides (how Femora is organized, "
                "what must come before what)", "examples": "worked examples"}
    guide = []
    for name, f in files.items():
        if name in ("SKILL.md", "instructions.txt"):
            continue
        what = describe[f["kind"]]
        if f["kind"] == "api":
            what += ": " + ", ".join(groups_for(api, f["cfg"]))[:90] + "..."
        guide.append(f"- `{name}` (about {len(built[name]) // 4:,} tokens): {what}")
    where = {g: n for n, f in files.items() if f["kind"] == "api" for g in groups_for(api, f["cfg"])}
    map_lines = []
    for g, items in groups_for(api, ["model-", "femora-"]).items():
        kept = [e for e in items if e["path"].split(".")[-1] not in BOOKKEEPING]
        map_lines.append(f"\n### {g}  (in `{where.get(g, '?')}`)")
        if g in COMPACT_GROUPS:
            by_parent: dict[str, list[str]] = {}
            for e in kept:
                parent, _, leaf = e["path"].rpartition(".")
                by_parent.setdefault(parent, []).append(leaf)
            map_lines += [f"- `{parent}`: " + ", ".join(sorted(leaves)) for parent, leaves in by_parent.items()]
        else:
            map_lines += [f"- `{e['path']}({param_names(e)})` {short(e['doc'])}" for e in kept]
    hints = f"\n## Hints\n\n{GOTCHAS}" if cfg["include_hints"] else ""
    concept_section = ""
    if "03_concepts.md" in built:
        concept_section = ("\n## Concept guides\n\n`03_concepts.md` holds the guides below, one section each, listed here "
                           "with their own section headings. They explain how Femora is organized, in what order things "
                           "happen, and why. Read the guide that matches the question before writing code.\n\n"
                           + concepts_guide(cfg, built["03_concepts.md"]) + "\n")
    ex_section = ""
    if "04_examples.md" in files:
        ex_section = ("\n## Examples guide\n\nWorked examples. The full code is linked, not copied here: follow a link when "
                      "this guide is not enough and you can open web pages. `04_examples.md` has more per example: its "
                      "explanation, and the calls its script makes, in order. Examples show the usual order of steps; "
                      "never copy parts the user did not ask for.\n\n"
                      + examples_guide(files["04_examples.md"]["ex"], cfg, built["04_examples.md"]) + "\n")
    return f"""---
name: {cfg["skill_name"]}
description: {cfg["skill_description"]}
---

# Femora: start here

{head}You write Python code for Femora, a library that builds OpenSees finite element models. The API changes over
time, so never rely on memory: these files are the source of truth.

## The files

- `SKILL.md` (this file): rules, build order, and a map of the whole API.
{chr(10).join(guide)}

Read this file first. Find what you need in the API map below. Before calling a function, open the API file named
in the map and read its exact signature; do not guess keyword names.

## Rules

{rules_text()}

## Build order

{BUILD_ORDER}
{concept_section}{hints}{ex_section}
## API map

One line per function: path, parameter names (`=…` marks a default), summary. Manager bookkeeping calls (`add`,
`get`, `remove`, `clear`, ...) are in the API files only.
{chr(10).join(map_lines)}
"""


def build_instructions() -> str:
    return ("You write Python code for Femora, a library that builds OpenSees finite element models. The attached "
            "files are the complete, current reference and the source of truth. Read SKILL.md first; it "
            "has the rules, a map of the whole API, and a guide to the other files.\n\nRules\n"
            + rules_text() + "\n")


# ---------------------------------------------------------------- main
def ensure_api(force: bool, do_extract: bool) -> dict:
    """The API catalog, from a cache in agent/build/ unless src changed (extracting takes about 30 s)."""
    src_hash = content_hash(["src"])
    fresh = API_JSON.exists() and API_STAMP.exists() and API_STAMP.read_text().strip() == src_hash
    if not fresh and do_extract:
        print("src changed since the API was last extracted; extracting (about 30 s)...", flush=True)
        api = extract()
        API_JSON.parent.mkdir(parents=True, exist_ok=True)
        API_JSON.write_bytes(json.dumps(api, indent=1).encode("utf-8"))
        API_STAMP.write_text(src_hash)
        return api
    if not fresh:
        print("WARNING: the cached API catalog may be out of date (skipped extraction, --no-extract)")
    return json.loads(API_JSON.read_text(encoding="utf-8"))


def check_skill_fields(cfg: dict) -> None:
    """The frontmatter must follow the rules for Claude skills, or an upload would be rejected."""
    name, desc = cfg["skill_name"], cfg["skill_description"]
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or "anthropic" in name or "claude" in name:
        sys.exit(f"skill_name {name!r}: lowercase letters, numbers and hyphens, at most 64 characters, "
                 "and no 'anthropic' or 'claude'")
    if not desc or desc != desc.strip() or len(desc) > 1024 or re.search(r"<[^>]+>", desc) or ": " in desc or " #" in desc:
        sys.exit("skill_description must be 1 to 1024 characters with no XML tags, no ': ' and no ' #' "
                 "(it is written as plain YAML)")
    if len(desc) > 200:
        WARNINGS.append(f"skill_description is {len(desc)} characters; some sources say claude.ai accepts only 200")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report what is out of date; change nothing")
    ap.add_argument("--force", action="store_true", help="rebuild every file")
    ap.add_argument("--no-extract", action="store_true", help="do not re-extract the API even if src changed")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)

    cfg = copy.deepcopy(CONFIG)
    cfg["concepts"] = concept_names(cfg.get("concepts_exclude") or [])   # discovered, not listed
    cfg["examples"] = docs_pages("examples", ["index"] + (cfg.get("examples_exclude") or []))   # likewise
    origin = git("remote", "get-url", "origin").removesuffix(".git")   # the repo the links point to, unless overridden
    cfg["github_repo"] = (cfg.get("github_repo") or origin).rstrip("/")
    cfg["docs_url"] = (cfg.get("docs_url") or "https://femora.io/docs").rstrip("/")
    check_skill_fields(cfg)
    files = plan(cfg)
    gen_hash = generator_hash()
    keys = recipe_keys(files, gen_hash)
    manifest_path = out / "bundle_manifest.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8"))["files"] if manifest_path.exists() else {}

    status = {}
    for name in files:
        if not (out / name).exists() or name not in old:
            status[name] = "missing"
        elif old[name]["recipe"] != keys[name]:
            status[name] = "out of date"
        else:
            status[name] = "up to date"
    removed = [n for n in old if n not in files]

    if a.check:
        print(f"{'file':20s} {'status':12s} built from")
        for name, st in status.items():
            b = old.get(name, {})
            built = stamp_text(b["input_commit"]) if b.get("input_commit") else "-"
            print(f"{name:20s} {st:12s} {built}")
        for n in removed:
            print(f"{n:20s} {'no longer planned':12s}")
        bad = [n for n, s in status.items() if s != "up to date"] + removed
        print("\nall up to date" if not bad else f"\n{len(bad)} file(s) need a rebuild: python -I agent/build_knowledge.py")
        return 1 if bad else 0

    todo = [n for n, s in status.items() if a.force or s != "up to date"]
    if "SKILL.md" not in todo and todo:
        todo.append("SKILL.md")  # it lists the other files, so it follows any change
    if not todo and not removed:
        print("bundle is up to date; nothing to rebuild")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    api = ensure_api(a.force, not a.no_extract)
    gen = commit_info(GENERATOR_STAMP)
    infos = {n: commit_info(f["inputs"]) for n, f in files.items()}
    built: dict[str, str] = {}
    for name in files:   # texts of files that are not rebuilt are read back, for the start file's token counts
        if name not in todo and (out / name).exists():
            built[name] = (out / name).read_text(encoding="utf-8")
    for name in [n for n in files if n not in ("SKILL.md", "instructions.txt")]:
        if name not in todo:
            continue
        f = files[name]
        head = header(name, f, infos[name], gen)
        built[name] = (build_api(name, f, api, head) if f["kind"] == "api" else
                       build_concepts(f, head) if f["kind"] == "concepts" else build_examples(f, head, cfg))
    if "SKILL.md" in todo:
        built["SKILL.md"] = build_start(files, built, api, cfg, header("SKILL.md", files["SKILL.md"],
                                                                                infos["SKILL.md"], gen))
    if "instructions.txt" in todo:
        built["instructions.txt"] = build_instructions()

    new_manifest = {n: old[n] for n in old if n in files and n not in todo}
    for name in todo:
        data = built[name].encode("utf-8")
        (out / name).write_bytes(data)
        i = infos[name]
        new_manifest[name] = {"recipe": keys[name], "bytes": len(data), "tokens_estimated": len(built[name]) // 4,
                              "sha256": hashlib.sha256(data).hexdigest()[:16], "inputs": files[name]["show"],
                              "input_commit": i if files[name]["inputs"] else None}
    for n in removed:
        (out / n).unlink(missing_ok=True)
    manifest_path.write_bytes(json.dumps({
        "generator_commit": gen, "femora_package_version": "0.1.0.7", "python": sys.version.split()[0],
        "files": {n: new_manifest[n] for n in files}}, indent=2).encode("utf-8") + b"\n")

    print(f"bundle written to {out}")
    for name in files:
        tok = new_manifest[name]["tokens_estimated"]
        flag = "rebuilt" if name in todo else "kept   "
        budget = cfg["budgets_tokens"].get(name)
        warn = f"   WARNING: over the {budget:,} token budget" if budget and tok > budget else ""
        print(f"  {flag} {name:20s} ~{tok:>7,} tokens{warn}")
    print(f"  total ~{sum(new_manifest[n]['tokens_estimated'] for n in files):,} tokens")
    if len(built["SKILL.md"].splitlines()) > 500:
        WARNINGS.append("SKILL.md is over 500 lines; the guidance for skills is to keep it shorter")
    for w in WARNINGS:
        print("WARNING:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
