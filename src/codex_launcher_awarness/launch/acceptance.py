"""Fixed fake-Codex packaging acceptance: never launches Codex or a model.

This is called only by an explicit developer smoke-test command. All inputs,
manifests, and fake output stay in CLA's private per-user acceptance directory.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import uuid
from dataclasses import replace

import psutil

from ..settings import Settings, app_dir, write_private_json
from .manager import LaunchError, LaunchManager, LaunchRequest
from .windows import is_elevated, spawn_interactive

_FAKE_SCRIPT = """$result = @{ arguments = @($args); cwd = (Get-Location).Path;
    elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Get-Location).Path 'fake-result.json') -Encoding utf8
exit 0
"""

_CONSOLE_FAKE_SCRIPT = r"""Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CLAConsoleCheck {
  [StructLayout(LayoutKind.Explicit, Size=20)] public struct InputRecord {
    [FieldOffset(0)] public UInt16 EventType;
    [FieldOffset(4)] public Int32 KeyDown;
    [FieldOffset(8)] public UInt16 Repeat;
    [FieldOffset(10)] public UInt16 VirtualKey;
    [FieldOffset(12)] public UInt16 Scan;
    [FieldOffset(14)] public UInt16 Character;
    [FieldOffset(16)] public UInt32 ControlState;
  }
  [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr GetStdHandle(int value);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetConsoleMode(IntPtr handle, out UInt32 mode);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool WriteConsoleInputW(IntPtr input, [In] InputRecord[] records, UInt32 count, out UInt32 written);
  public static bool IsConsole(int stream) { UInt32 mode; return GetConsoleMode(GetStdHandle(stream), out mode); }
  public static string OwnInputRoundtrip() {
    if (!IsConsole(-10)) throw new InvalidOperationException("Fake input test has no console handle.");
    string marker = "CLA_INPUT_OK\r";
    InputRecord[] records = new InputRecord[marker.Length];
    for (int index=0; index<marker.Length; index++) {
      records[index].EventType=1; records[index].KeyDown=1; records[index].Repeat=1;
      records[index].Character=(UInt16)marker[index];
      records[index].VirtualKey=(UInt16)(marker[index]=='\r' ? 13 : 0);
    }
    UInt32 written;
    if (!WriteConsoleInputW(GetStdHandle(-10), records, (UInt32)records.Length, out written) || written != records.Length)
      throw new InvalidOperationException("Could not write the fixed marker to the fake process's own input handle.");
    return Console.ReadLine();
  }
}
'@
$result = @{ arguments = @($args); cwd = (Get-Location).Path; pid = $PID;
  started_at = [DateTime]::UtcNow.ToString('o');
  stdin_console = [CLAConsoleCheck]::IsConsole(-10);
  stdout_console = [CLAConsoleCheck]::IsConsole(-11);
  stderr_console = [CLAConsoleCheck]::IsConsole(-12);
  elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
Write-Host 'CLA synthetic console acceptance. No Codex or model. This window closes automatically.'
[Console]::Error.WriteLine('CLA synthetic stderr write check.')
$result.stdout_write_completed = $true
$result.stderr_write_completed = $true
$result.input_roundtrip = [CLAConsoleCheck]::OwnInputRoundtrip()
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Get-Location).Path 'console-started.json') -Encoding utf8
Start-Sleep -Seconds 4
$result.finished_at = [DateTime]::UtcNow.ToString('o')
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Get-Location).Path 'console-finished.json') -Encoding utf8
exit 0
"""


def start_console_launch_acceptance(powershell_path: str, *, allow_elevated: bool = False) -> dict:
    """Start exactly one visible fake console, then return so this owner can exit.

    The external acceptance wrapper checks the child's later completion, proving
    that the owner lifetime does not control the terminal. The fixed fake writes
    a marker only to its own stdin handle and reads it back; it never attaches to
    another console. No real Codex executable can be selected by this function.
"""
    run_id = uuid.uuid4().hex
    root = app_dir() / "acceptance" / ("console-launch-" + run_id)
    root.mkdir(parents=True)
    project = root / "project O'Brien; [$literal] 日本"
    project.mkdir()
    fake = project / "fake codex.ps1"
    fake.write_text(_CONSOLE_FAKE_SCRIPT, encoding="utf-8")
    settings = Settings(trusted_executables={"codex": str(fake), "powershell": powershell_path},
                        approved_project_roots=[str(project)])
    task = "Synthetic console context ' \" ; $([literal]) [brackets] 日本\n" + "bounded context " * 100
    manager = LaunchManager(settings, state_dir=root / "state")
    prepared = manager.prepare(LaunchRequest(str(project), "Fake console acceptance only", str(fake), powershell_path,
                                            allow_elevated=allow_elevated), {}, task)
    # The fake test has a fixed four-second lifetime. Real Start retains -NoExit.
    prepared = replace(prepared, command=[value for value in prepared.command if value != "-NoExit"])
    launch = manager.launch(prepared)
    try:
        manager.launch(prepared)
    except LaunchError:
        duplicate_blocked = True
    else:
        duplicate_blocked = False
    record = {"schema_version": 1, "run_id": run_id, "test": "real_new_console_fake_codex",
              "status": "STARTED", "frozen": bool(getattr(sys, "frozen", False)), "model_calls": 0,
              "pid": launch["pid"], "duplicate_blocked": duplicate_blocked,
              "manifest_path": str(prepared.manifest_path), "project": str(project),
              "artifact_root": str(root), "allow_elevated": allow_elevated,
              "input_roundtrip": "PENDING: fixed marker written only to the fake's own console input handle"}
    write_private_json(root / "started.json", record)
    return record


def run_fake_launch_acceptance(powershell_path: str, *, allow_elevated: bool = False) -> dict:
    run_id = uuid.uuid4().hex
    root = app_dir() / "acceptance" / ("frozen-launch-" + run_id)
    root.mkdir(parents=True)
    project = root / "project O'Brien; [$literal] 日本"
    project.mkdir()
    fake = project / "fake codex.ps1"
    fake.write_text(_FAKE_SCRIPT, encoding="utf-8")
    settings = Settings(trusted_executables={"codex": str(fake), "powershell": powershell_path},
                        approved_project_roots=[str(project)])
    task = "Synthetic packaging context: apostrophe ' quote \" semicolon; dollar$ brackets[] 日本\n" + "bounded context " * 160
    request = LaunchRequest(str(project), "Fake packaging acceptance only", str(fake), powershell_path,
                            allow_elevated=allow_elevated)
    prepared = LaunchManager(settings, state_dir=root / "state").prepare(request, {}, task)
    # A hidden terminal is appropriate for the fixed fake executable only. Real
    # user Start always uses a new interactive console and -NoExit.
    command = [value for value in prepared.command if value != "-NoExit"]
    launch = spawn_interactive(command, str(project), new_console=False, allow_elevated=allow_elevated)
    status_path = prepared.manifest_path.parent / "status.json"
    status = {}
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
        if status.get("status") in {"failed", "codex_exited"}:
            break
        time.sleep(0.1)
    payload_path = project / "fake-result.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8-sig")) if payload_path.exists() else {}
    expected = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))["codex_args"]
    checks = {
        "bootstrap_completed": status.get("status") == "codex_exited" and status.get("exit_code") == 0,
        "exact_arguments": payload.get("arguments") == expected,
        "correct_project": payload.get("cwd") == str(project),
        "expected_token": payload.get("elevated") == (is_elevated() and allow_elevated),
        "real_codex_not_invoked": True,
    }
    try:
        psutil.Process(launch["pid"]).wait(timeout=5)
    except psutil.NoSuchProcess:
        checks["fake_process_finished"] = True
    except psutil.TimeoutExpired:
        # Never kill by pattern or take over an independent terminal lifecycle.
        checks["fake_process_finished"] = False
    else:
        checks["fake_process_finished"] = True
    summary = {"schema_version": 1, "run_id": run_id, "test": "frozen_external_child_bootstrap",
               "status": "PASS" if all(checks.values()) else "FAIL", "frozen": bool(getattr(sys, "frozen", False)),
               "checks": checks, "model_calls": 0, "codex": "fixed fake PowerShell executable",
               "child_elevated_by_explicit_test_opt_in": payload.get("elevated"),
               "stdout_protocol": "JSON summary only", "artifacts": "Private CLA acceptance directory"}
    write_private_json(root / "summary.json", summary)
    return summary
