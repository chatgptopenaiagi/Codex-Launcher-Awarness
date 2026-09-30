"""Windows process creation without elevation inheritance or GUI lifetime coupling.

An elevated CLA can duplicate the existing same-user unelevated desktop shell
token. It never obtains another user's token or changes workstation security.
If the desktop is elevated too, default launch refuses. Explicit user opt-in can
inherit existing administrator rights. Handles close without killing sessions.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def is_elevated() -> bool:
    if os.name != "nt":
        return False
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def desktop_directory() -> Path:
    import ctypes
    from ctypes import wintypes
    buffer = ctypes.create_unicode_buffer(32768)
    # CSIDL_DESKTOPDIRECTORY resolves redirected user Desktop locations.
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer)
    if result:
        raise OSError("Windows could not resolve the user's Desktop folder.")
    return Path(buffer.value)


def spawn_interactive(command: list[str], cwd: str, *, new_console: bool = True, allow_elevated: bool = False) -> dict:
    """new_console=False is used by automated fake-program tests only."""
    if os.name != "nt":
        raise OSError("Windows is required.")
    from ..process_runtime import clean_child_dll_search
    with clean_child_dll_search():
        return _spawn_interactive(command, cwd, new_console=new_console, allow_elevated=allow_elevated)


def _spawn_interactive(command: list[str], cwd: str, *, new_console: bool, allow_elevated: bool) -> dict:
    elevated = is_elevated()
    if not elevated or allow_elevated:
        process = subprocess.Popen(command, cwd=cwd, close_fds=True,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE if new_console else subprocess.CREATE_NO_WINDOW)
        # Popen destruction does not terminate the independent child.
        return {"pid": process.pid, "unelevated": not elevated, "creation_method": "explicit inherited administrator token" if elevated else "CreateProcess"}
    return _spawn_shell_token(command, cwd, new_console=new_console)


def _spawn_shell_token(command: list[str], cwd: str, *, new_console: bool) -> dict:
    import ctypes
    from ctypes import wintypes as wt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    HANDLE = wt.HANDLE
    LPVOID = ctypes.c_void_p

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
                    ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                    ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD),
                    ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD), ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
                    ("hStdInput", HANDLE), ("hStdOutput", HANDLE), ("hStdError", HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]

    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = HANDLE
    kernel.GetCurrentProcess.restype = HANDLE
    kernel.CloseHandle.argtypes = [HANDLE]
    kernel.WaitForSingleObject.argtypes = [HANDLE, wt.DWORD]
    kernel.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(wt.DWORD)]
    user.GetShellWindow.restype = wt.HWND
    user.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    advapi.OpenProcessToken.argtypes = [HANDLE, wt.DWORD, ctypes.POINTER(HANDLE)]
    advapi.GetTokenInformation.argtypes = [HANDLE, ctypes.c_int, LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    advapi.EqualSid.argtypes = [LPVOID, LPVOID]
    advapi.DuplicateTokenEx.argtypes = [HANDLE, wt.DWORD, LPVOID, ctypes.c_int, ctypes.c_int, ctypes.POINTER(HANDLE)]
    advapi.CreateProcessWithTokenW.argtypes = [HANDLE, wt.DWORD, wt.LPCWSTR, wt.LPWSTR, wt.DWORD, LPVOID,
                                              wt.LPCWSTR, ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]

    def check(value, message):
        if not value:
            raise OSError(ctypes.get_last_error(), message)
        return value

    def token_info(token, kind):
        needed = wt.DWORD()
        advapi.GetTokenInformation(token, kind, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        check(advapi.GetTokenInformation(token, kind, buffer, needed, ctypes.byref(needed)), "Cannot inspect Windows shell token.")
        return buffer

    handles = []
    try:
        window = user.GetShellWindow()
        if not window:
            raise OSError("No desktop shell exists. Open CLA in an unelevated interactive Windows session.")
        shell_pid = wt.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(shell_pid))
        shell_process = check(kernel.OpenProcess(0x1000, False, shell_pid), "Cannot open the desktop shell process.")
        handles.append(shell_process)
        shell_token, current_token = HANDLE(), HANDLE()
        check(advapi.OpenProcessToken(shell_process, 0x0002 | 0x0008 | 0x0001, ctypes.byref(shell_token)), "Cannot query the desktop shell token.")
        handles.append(shell_token)
        check(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(current_token)), "Cannot query the current user token.")
        handles.append(current_token)
        shell_user = token_info(shell_token, 1)
        current_user = token_info(current_token, 1)
        shell_sid = ctypes.cast(shell_user, ctypes.POINTER(LPVOID))[0]
        current_sid = ctypes.cast(current_user, ctypes.POINTER(LPVOID))[0]
        if not advapi.EqualSid(shell_sid, current_sid):
            raise OSError("The desktop belongs to another user. Open CLA as the intended unelevated user.")
        primary = HANDLE()
        check(advapi.DuplicateTokenEx(shell_token, 0x02000000, None, 2, 1, ctypes.byref(primary)), "Cannot duplicate the unelevated desktop token.")
        handles.append(primary)
        method = "same-user desktop token"
        elevation = token_info(shell_token, 20)
        if ctypes.cast(elevation, ctypes.POINTER(wt.DWORD))[0]:
            raise OSError("The Windows desktop and CLA are both elevated. CLA will not silently inherit administrator rights. Open an unelevated desktop session, or explicitly select administrator-token inheritance in CLA for this launch.")
        startup, process = STARTUPINFO(), PROCESS_INFORMATION()
        startup.cb = ctypes.sizeof(startup)
        startup.lpDesktop = "winsta0\\default"
        flags = (subprocess.CREATE_NEW_CONSOLE if new_console else subprocess.CREATE_NO_WINDOW) | 0x00000400
        buffer = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
        # Inherit caller environment as an ordinary child would, including an
        # explicit CODEX_HOME; never serialize or log environment values.
        environment = ctypes.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(os.environ.items(), key=lambda item: item[0].casefold())) + "\0\0")
        check(advapi.CreateProcessWithTokenW(primary, 0, command[0], buffer, flags, environment, cwd,
                                           ctypes.byref(startup), ctypes.byref(process)),
              "Could not create the unelevated terminal. Open CLA without Run as administrator.")
        handles.extend([process.hThread, process.hProcess])
        result = {"pid": process.dwProcessId, "unelevated": True, "creation_method": method}
        if not new_console:
            kernel.WaitForSingleObject(process.hProcess, 5000)
            exit_code = wt.DWORD()
            if kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)):
                result["probe_exit_code"] = exit_code.value
        return result
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)
