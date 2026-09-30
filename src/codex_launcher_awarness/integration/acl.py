"""Windows ACL helpers limited to files CLA is already authorized to write.

No process privileges, user rights, system policy or pre-existing directories
are changed. Existing Codex config DACLs are preserved during atomic replace.
"""
from __future__ import annotations

import os
from pathlib import Path


def secure_file(path: Path, *, preserve_from: Path | None = None) -> None:
    if os.name != "nt":
        if preserve_from is None:
            path.chmod(0o600)
        else:
            path.chmod(preserve_from.stat().st_mode & 0o777)
        return
    import ctypes
    from ctypes import wintypes as wt
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.GetFileSecurityW.argtypes = [wt.LPCWSTR, wt.DWORD, pointer, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    advapi.SetFileSecurityW.argtypes = [wt.LPCWSTR, wt.DWORD, pointer]
    advapi.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wt.WORD), ctypes.POINTER(wt.DWORD)]
    advapi.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, pointer, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(wt.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(pointer), ctypes.POINTER(wt.DWORD)]
    kernel.GetCurrentProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.LocalFree.argtypes = [pointer]

    def check(value):
        if not value:
            raise OSError(ctypes.get_last_error(), "Could not preserve/private-protect the CLA output file ACL.")

    if preserve_from is not None and preserve_from.exists():
        length = wt.DWORD()
        advapi.GetFileSecurityW(str(preserve_from), 4, None, 0, ctypes.byref(length))
        descriptor = ctypes.create_string_buffer(length.value)
        check(advapi.GetFileSecurityW(str(preserve_from), 4, descriptor, length, ctypes.byref(length)))
        control, revision = wt.WORD(), wt.DWORD()
        check(advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)))
        protection = 0x80000000 if control.value & 0x1000 else 0x20000000
        check(advapi.SetFileSecurityW(str(path), 4 | protection, descriptor))
        return
    token = wt.HANDLE()
    sid_text = wt.LPWSTR()
    descriptor = pointer()
    try:
        check(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)))
        length = wt.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))
        user = ctypes.create_string_buffer(length.value)
        check(advapi.GetTokenInformation(token, 1, user, length, ctypes.byref(length)))
        sid = ctypes.cast(user, ctypes.POINTER(pointer))[0]
        check(advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)))
        sddl = f"D:P(A;;FA;;;SY)(A;;FA;;;{sid_text.value})"
        check(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None))
        check(advapi.SetFileSecurityW(str(path), 4 | 0x80000000, descriptor))
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        if sid_text:
            kernel.LocalFree(sid_text)
        if token:
            kernel.CloseHandle(token)
