"""Tests for source and frozen executable resolution."""

from __future__ import annotations

import sys
from pathlib import Path

from lib.runtime import find_bundled_executable


def test_source_install_uses_path_lookup(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr("lib.runtime.shutil.which", lambda name: f"/usr/bin/{name}")

    assert find_bundled_executable("ffmpeg") == "ffmpeg"


def test_frozen_windows_install_prefers_bundled_binary(monkeypatch, tmp_path: Path) -> None:
    install_directory = tmp_path / "WhisperFlow"
    bundled_binary = install_directory / "bin" / "ffmpeg.exe"
    bundled_binary.parent.mkdir(parents=True)
    bundled_binary.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install_directory / "whisperflow.exe"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("lib.runtime.shutil.which", lambda name: None)

    assert find_bundled_executable("ffmpeg") == str(bundled_binary)


def test_frozen_install_falls_back_to_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "whisperflow.exe"))
    monkeypatch.setattr("lib.runtime.shutil.which", lambda name: f"/usr/bin/{name}")

    assert find_bundled_executable("ffprobe") == "ffprobe"