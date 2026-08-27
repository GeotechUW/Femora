# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

from io import StringIO
import os
from pathlib import Path

import pytest

from femora import runtime


class _FakeProcess:
    def __init__(self, output: str, return_code: int = 0):
        self.stdout = StringIO(output)
        self._return_code = return_code

    def wait(self) -> int:
        return self._return_code


class _FakeTqdm:
    instances = []
    messages = []

    def __init__(self, *, total, desc, initial=0, unit="step", **_kwargs):
        self.total = total
        self.desc = desc
        self.n = initial
        self.unit = unit
        self.closed = False
        self.instances.append(self)

    def update(self, amount):
        self.n += amount

    def close(self):
        self.closed = True

    @classmethod
    def write(cls, message):
        cls.messages.append(message)


@pytest.fixture(autouse=True)
def reset_fake_tqdm():
    _FakeTqdm.instances.clear()
    _FakeTqdm.messages.clear()


def _configure_process(monkeypatch, output: str, return_code: int = 0):
    monkeypatch.setattr(runtime, "tqdm", _FakeTqdm)
    monkeypatch.setattr(
        runtime.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _FakeProcess(output, return_code),
    )


def test_setup_local_registers_explicit_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "OpenSees"
    executable.write_text("placeholder", encoding="ascii")
    monkeypatch.setattr(runtime, "_probe_runtime", lambda _: "3.8.0")

    configured = runtime.setup("local", executable=executable)

    assert configured.environment == "local"
    assert configured.executable == executable.resolve()
    assert configured.version == "3.8.0"
    assert configured.installed is False
    assert os.environ["FEMORA_OPENSEES"] == str(executable.resolve())


def test_setup_accepts_google_colab_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_dir = tmp_path / "opensees"
    executable = install_dir / "OpenSees"
    tcl_library = install_dir / "lib" / "tcl8.6"
    tcl_library.mkdir(parents=True)
    executable.write_text("placeholder", encoding="ascii")
    monkeypatch.setattr(runtime, "_probe_runtime", lambda _: "3.8.0")

    configured = runtime.setup("google_colab", install_dir=install_dir)

    assert configured.environment == "colab"
    assert configured.executable == executable.resolve()
    assert configured.tcl_library == tcl_library.resolve()
    assert configured.installed is False


def test_setup_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="environment must be"):
        runtime.setup("cluster")


def test_run_tracks_managed_analysis_progress(tmp_path, monkeypatch):
    script = tmp_path / "model.tcl"
    executable = tmp_path / "OpenSees"
    script.write_text("wipe\n", encoding="ascii")
    executable.write_text("", encoding="ascii")
    _configure_process(
        monkeypatch,
        "FEMORA_PROGRESS|START|Dynamic response|10\n"
        "FEMORA_PROGRESS|UPDATE|Dynamic response|4|10\n"
        "FEMORA_PROGRESS|UPDATE|Dynamic response|10|10\n",
    )

    completed = runtime.run(script, executable=executable)

    assert completed.returncode == 0
    assert len(_FakeTqdm.instances) == 1
    assert _FakeTqdm.instances[0].n == 10
    assert _FakeTqdm.instances[0].closed


def test_run_tracks_final_time_as_seconds(tmp_path, monkeypatch):
    script = tmp_path / "model.tcl"
    executable = tmp_path / "OpenSees"
    script.write_text("wipe\n", encoding="ascii")
    executable.write_text("", encoding="ascii")
    _configure_process(
        monkeypatch,
        "FEMORA_PROGRESS|START|Dynamic response|40.0|s|2.0\n"
        "FEMORA_PROGRESS|UPDATE|Dynamic response|2.5|40.0|s\n"
        "FEMORA_PROGRESS|UPDATE|Dynamic response|40.0|40.0|s\n",
    )

    completed = runtime.run(script, executable=executable)

    assert completed.returncode == 0
    assert _FakeTqdm.instances[0].total == 40.0
    assert _FakeTqdm.instances[0].unit == "s"
    assert _FakeTqdm.instances[0].n == 40.0


def test_run_raises_when_analysis_reports_failure(tmp_path, monkeypatch):
    script = tmp_path / "model.tcl"
    executable = tmp_path / "OpenSees"
    script.write_text("wipe\n", encoding="ascii")
    executable.write_text("", encoding="ascii")
    _configure_process(
        monkeypatch,
        "FEMORA_PROGRESS|START|Dynamic response|10\n"
        "FEMORA_PROGRESS|ERROR|Dynamic response|3|-3\n",
    )

    with pytest.raises(runtime.RuntimeExecutionError, match="failed at step 3"):
        runtime.run(script, executable=executable)

    assert "failed at step 3" in _FakeTqdm.messages[0]
