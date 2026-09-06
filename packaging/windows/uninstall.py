r"""Standalone stub bundled as `<install-dir>\uninstall.exe`.

Looks up the installed "WhisperFlow" product via the registry rather than a
build-time-embedded product code, since WiX's product code can change across
rebuilds. Uninstalling a per-machine MSI requires an elevated caller, so this
re-launches `msiexec /x` with the `runas` verb rather than requiring the stub
itself to be launched elevated.
"""

from __future__ import annotations

import ctypes
import re
import sys
import winreg

_DISPLAY_NAME = "WhisperFlow"
_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
_GUID_RE = re.compile(r"\{[0-9A-Fa-f-]{36}\}")


def _find_product_code() -> str | None:
    for key_path in _UNINSTALL_KEYS:
        try:
            uninstall_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        except OSError:
            continue
        with uninstall_key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(uninstall_key, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(uninstall_key, subkey_name) as subkey:
                        display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        if display_name != _DISPLAY_NAME:
                            continue
                        uninstall_string = winreg.QueryValueEx(subkey, "UninstallString")[0]
                except OSError:
                    continue
                match = _GUID_RE.search(uninstall_string) or _GUID_RE.search(subkey_name)
                if match:
                    return match.group(0)
    return None


def _pause_on_error() -> None:
    if sys.stdin.isatty():
        input("Press Enter to close...")


def main() -> int:
    product_code = _find_product_code()
    if product_code is None:
        print(f"{_DISPLAY_NAME} does not appear to be installed.", file=sys.stderr)
        _pause_on_error()
        return 1

    # ShellExecuteW's "runas" verb prompts UAC for just this step, rather
    # than requiring this stub itself to be launched elevated.
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "msiexec.exe", f"/x {product_code} /qb", None, 1
    )
    if result <= 32:  # ShellExecuteW returns a value > 32 on success.
        print(f"Failed to launch the uninstaller (error code {result}).", file=sys.stderr)
        _pause_on_error()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
