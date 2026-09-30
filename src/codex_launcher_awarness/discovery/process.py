"""Fixed-template probes with bounded capture and owned-child cleanup."""

from __future__ import annotations

import os
import ctypes
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from codex_launcher_awarness.process_runtime import clean_child_dll_search


class _OwnedJob:
    """Windows Job Object makes cancellation include only our probe descendants."""

    def __init__(self, child: subprocess.Popen):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        limits = EXTENDED()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError("Could not create owned probe job")
        if not self.api.AssignProcessToJobObject(self.handle, int(child._handle)):
            # A probe can exit before assignment; no descendants are expected for such a case.
            if child.poll() is None:
                self.close()
                raise OSError("Could not assign owned probe job")

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


@dataclass(frozen=True)
class ProbeResult:
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: float
    error: str | None = None


def run_probe(executable: Path, arguments: list[str], *, timeout: float = 4,
              max_bytes: int = 32768, cancel: threading.Event | None = None,
              environment: dict[str, str] | None = None) -> ProbeResult:
    """No shell; terminate only the child we created. Never return unbounded output."""
    started = time.monotonic()
    if cancel is not None and cancel.is_set():
        return ProbeResult(None, "", "", 0, "cancelled")
    if not executable.is_absolute() or not executable.is_file():
        return ProbeResult(None, "", "", 0, "executable_missing")
    if executable.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        return ProbeResult(None, "", "", 0, "wrapper_requires_powershell")
    buffers: list[bytearray] = [bytearray(), bytearray()]
    exceeded = threading.Event()
    try:
        with clean_child_dll_search():
            child = subprocess.Popen(
                [str(executable), *arguments], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                env=environment,
            )
    except PermissionError:
        return ProbeResult(None, "", "", (time.monotonic() - started) * 1000, "access_denied")
    except OSError:
        return ProbeResult(None, "", "", (time.monotonic() - started) * 1000, "process_start_failed")
    try:
        job = _OwnedJob(child)
    except OSError:
        child.kill()
        child.communicate(timeout=1)
        return ProbeResult(child.returncode, "", "", (time.monotonic() - started) * 1000,
                           "owned_process_isolation_failed")

    def consume(pipe, buffer: bytearray) -> None:
        try:
            while chunk := pipe.read(4096):
                remaining = max_bytes - len(buffer)
                buffer.extend(chunk[:max(remaining, 0)])
                if len(chunk) > remaining:
                    exceeded.set()
                    break
        finally:
            pipe.close()

    readers = [threading.Thread(target=consume, args=(pipe, buffer), daemon=True)
               for pipe, buffer in zip((child.stdout, child.stderr), buffers)]
    for reader in readers:
        reader.start()
    error = None
    try:
        while child.poll() is None:
            if cancel is not None and cancel.is_set():
                error = "cancelled"
            elif exceeded.is_set():
                error = "output_limit"
            elif time.monotonic() - started >= timeout:
                error = "timeout"
            if error:
                job.close()
                child.terminate()
                try:
                    child.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1)
                break
            time.sleep(0.02)
        for reader in readers:
            reader.join(timeout=0.5)
        if exceeded.is_set() and not error:
            error = "output_limit"
        if child.returncode not in (None, 0) and not error:
            error = "nonzero_exit"
    finally:
        job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=1)
    return ProbeResult(child.returncode, buffers[0].decode("utf-8-sig", "replace"),
                       buffers[1].decode("utf-8-sig", "replace"),
                       round((time.monotonic() - started) * 1000, 2), error)
