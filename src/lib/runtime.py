"""Runtime paths for source and frozen WhisperFlow installations."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def find_bundled_executable(name: str) -> str | None:
    """Return a bundled executable path when running a frozen application.

    PyInstaller's one-directory build keeps bundled tools beside the
    launcher, while its one-file build expands them under ``_MEIPASS``.
    Source installs deliberately retain the existing ``PATH`` lookup.
    """
    if not getattr(sys, "frozen", False):
        return name if shutil.which(name) is not None else None

    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    bundle_roots = [Path(sys.executable).resolve().parent]
    temporary_bundle = getattr(sys, "_MEIPASS", None)
    if temporary_bundle is not None:
        bundle_roots.append(Path(temporary_bundle))

    for bundle_root in bundle_roots:
        candidate = bundle_root / "bin" / executable_name
        if candidate.is_file():
            return str(candidate)
    return name if shutil.which(name) is not None else None