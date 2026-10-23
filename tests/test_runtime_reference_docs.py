"""Validate runtime documentation against mocked solver behavior, without downloads."""

import ast
from io import StringIO
from pathlib import Path
import re
import subprocess
from textwrap import dedent

import pytest

from femora import runtime


SOURCE = Path(__file__).resolve().parents[1] / "src/femora/runtime.py"


class FakeProcess:
    def __init__(self, output="model finished\n", code=0):
        self.stdout = StringIO(output)
        self.code = code

    def wait(self):
        return self.code


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FEMORA_OPENSEES", "unset-for-test")
    executable = tmp_path / "path/to/OpenSees"
    executable.parent.mkdir(parents=True)
    executable.write_text("placeholder", encoding="ascii")
    script = tmp_path / "example_outputs/case/model.tcl"
    script.parent.mkdir(parents=True)
    script.write_text("wipe\n", encoding="ascii")
    return executable, script


def test_runtime_doc_examples_compile_and_returns_are_documented():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            continue
        for snippet in re.findall(r"```python\n(.*?)```", ast.get_docstring(node) or "", re.S):
            compile(dedent(snippet), str(SOURCE), "exec")
    griffe = pytest.importorskip("griffe")
    module = griffe.GriffeLoader(search_paths=[SOURCE.parents[1]], allow_inspection=False).load("femora.runtime")
    for name in ("setup", "run"):
        sections = module[name].docstring.parse("google")
        returns = next(section for section in sections if section.kind.value == "returns")
        assert len(returns.value) == 1 and returns.value[0].annotation is not None


def test_overview_example_and_explicit_log_write(files, monkeypatch):
    executable, script = files
    launched = []

    def probe(argv, **kwargs):
        assert Path(argv[1]).is_file()
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(argv, 0, "OpenSees Version 3.8.0\nFEMORA_OPENSEES_RUNTIME_OK\n", "")

    def launch(argv, **kwargs):
        launched.append((argv, kwargs))
        return FakeProcess()

    monkeypatch.setattr(runtime.subprocess, "run", probe)
    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    snippets = re.findall(r"```python\n(.*?)```", runtime.__doc__, re.S)
    namespace = {}
    exec(snippets[0], namespace)
    assert namespace["info"].executable == executable.resolve()
    assert namespace["info"].version == "3.8.0"
    completed = namespace["completed"]
    assert completed.returncode == 0
    assert completed.stdout == "model finished\n" and completed.stderr is None
    assert launched[0][0] == [str(executable.resolve()), str(script.resolve())]
    assert launched[0][1]["cwd"] == script.parent
    assert not list(script.parent.rglob("manifest.json"))
    assert not list(script.parent.rglob("stdout.log"))
    assert not (script.parent / "solver_output.log").exists()
    exec(snippets[1], namespace)
    assert (script.parent / "solver_output.log").read_text() == completed.stdout


def test_run_resolves_script_independently_of_working_directory(files, tmp_path, monkeypatch):
    executable, script = files
    working = tmp_path / "solver-working"
    working.mkdir()
    launched = []

    def launch(argv, **kwargs):
        launched.append((argv, kwargs))
        return FakeProcess()

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    runtime.run("example_outputs/case/model.tcl", executable=executable, cwd="solver-working")
    assert launched[0][0][1] == str(script.resolve())
    assert launched[0][1]["cwd"] == working


def test_successful_probe_can_have_no_version(files, monkeypatch):
    executable, _ = files
    monkeypatch.setattr(runtime.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, "FEMORA_OPENSEES_RUNTIME_OK\n", ""))
    info = runtime.setup("local", executable=executable)
    assert info.version is None
    assert info.installed is False


def test_failed_run_contains_tail_without_jobs_result(files, monkeypatch):
    executable, script = files
    output = "".join(f"line {i}\n" for i in range(30))
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(output, 7))
    with pytest.raises(runtime.RuntimeExecutionError) as captured:
        runtime.run(script, executable=executable)
    message = str(captured.value)
    assert "OpenSees exited with code 7" in message
    assert "line 9\n" not in message and "line 10\n" in message and "line 29" in message
    assert not hasattr(captured.value, "run")
    assert not hasattr(captured.value, "stdout")
    assert not list(script.parent.rglob("stdout.log"))


def test_warning_alone_does_not_fail_the_run(files, monkeypatch):
    executable, script = files
    output = "WARNING: diagnostic only\n"
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(output))
    assert runtime.run(script, executable=executable).stdout == output


def test_missing_model_and_failed_launch_are_different(files, monkeypatch):
    executable, script = files
    with pytest.raises(FileNotFoundError):
        runtime.run("missing.tcl", executable=executable)

    def launch(*args, **kwargs):
        raise PermissionError("executable cannot start")

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    with pytest.raises(runtime.RuntimeExecutionError) as captured:
        runtime.run(script, executable=executable)
    assert isinstance(captured.value.__cause__, PermissionError)
