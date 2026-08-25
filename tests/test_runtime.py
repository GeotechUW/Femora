# =============================================================================
# Femora: Fast Efficient Meta-modeling for OpenSees-based Resilience Analysis
# Copyright 2026 Amin Pakzad and Pedro Arduino
# Developed at the UW Geotechnical Lab
# SPDX-License-Identifier: Apache-2.0
# =============================================================================

"""Tests for OpenSees runtime configuration."""

import os
from pathlib import Path

import pytest

from femora import runtime


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
