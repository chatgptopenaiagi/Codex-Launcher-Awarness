"""Keep PyInstaller's private DLL directory out of external child processes.

The Win32 loader setting is process-local, so all CLA external child creation
uses this shared lock. PATH and the parent environment are never modified.
The original setting is restored immediately after creation, even on failure.
"""
from __future__ import annotations

from contextlib import contextmanager
import sys
import threading

_DLL_SEARCH_LOCK = threading.RLock()


def _get_dll_directory() -> str | None:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    ctypes.set_last_error(0)
    length = kernel.GetDllDirectoryW(0, None)
    if not length:
        error = ctypes.get_last_error()
        if error:
            raise OSError(error, "Cannot inspect the process DLL search directory.")
        return None
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = kernel.GetDllDirectoryW(len(buffer), buffer)
    if not copied or copied >= len(buffer):
        raise OSError(ctypes.get_last_error(), "Cannot read the process DLL search directory.")
    return buffer.value


def _set_dll_directory(value: str | None) -> None:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    if not kernel.SetDllDirectoryW(value):
        raise OSError(ctypes.get_last_error(), "Cannot set the process DLL search directory.")


@contextmanager
def clean_child_dll_search():
    """Wrap only external Popen/CreateProcess creation, never a child lifetime.

This is a no-op for source/wheel execution and non-Windows processes. It does
not change OS policy, registry settings, installed software, or system PATH.
"""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    with _DLL_SEARCH_LOCK:
        previous = _get_dll_directory()
        _set_dll_directory(None)
        try:
            yield
        finally:
            _set_dll_directory(previous)
