"""Run the portable CLI's fixed fake-launch acceptance from outside its source.

Usage: python scripts/acceptance_frozen_launch.py --cla ABSOLUTE_CLA_EXE
       --powershell ABSOLUTE_PWSH_EXE [--allow-elevated]
This command never invokes a real Codex installation or spends model quota.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone


def finish_console_acceptance(started: dict, owner_exit_time: datetime) -> dict:
    root = Path(started["artifact_root"]).resolve()
    run_id = started["run_id"]
    if root.name != "console-launch-" + run_id or root.parent.name != "acceptance":
        raise ValueError("Unexpected private acceptance directory")
    project = Path(started["project"]).resolve()
    manifest = Path(started["manifest_path"]).resolve()
    if not project.is_relative_to(root) or not manifest.is_relative_to(root):
        raise ValueError("Acceptance artifacts escaped their private directory")
    finished = project / "console-finished.json"
    deadline = time.monotonic() + 20
    payload, lifecycle = {}, {}
    while time.monotonic() < deadline:
        try:
            if finished.is_file():
                payload = json.loads(finished.read_text(encoding="utf-8-sig"))
            lifecycle = json.loads((manifest.parent / "status.json").read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
        if payload and lifecycle.get("status") in {"codex_exited", "failed"}:
            break
        time.sleep(0.1)
    expected = json.loads(manifest.read_text(encoding="utf-8"))["codex_args"]
    finished_at = datetime.fromisoformat(payload["finished_at"].replace("Z", "+00:00")) if payload.get("finished_at") else None
    checks = {"creator_process_exited": True,
              "child_completed_after_creator_exit": bool(finished_at and finished_at > owner_exit_time),
              "stdin_console_handle": payload.get("stdin_console") is True,
              "stdout_console_handle": payload.get("stdout_console") is True,
              "stderr_console_handle": payload.get("stderr_console") is True,
              "stdout_write": payload.get("stdout_write_completed") is True,
              "stderr_write": payload.get("stderr_write_completed") is True,
              "stdin_readline_roundtrip": payload.get("input_roundtrip") == "CLA_INPUT_OK",
              "exact_arguments": payload.get("arguments") == expected,
              "correct_project": payload.get("cwd") == str(project),
              "single_launch_duplicate_blocked": started.get("duplicate_blocked") is True,
              "bootstrap_exit_zero": lifecycle.get("status") == "codex_exited" and lifecycle.get("exit_code") == 0}
    summary = {"schema_version": 1, "run_id": run_id, "test": "real_new_console_fake_codex",
               "status": "PASS" if all(checks.values()) else "FAIL", "frozen": started.get("frozen"),
               "checks": checks, "model_calls": 0, "codex": "fixed fake PowerShell executable",
               "input_roundtrip": "PASS" if checks["stdin_readline_roundtrip"] else "FAIL",
               "input_scope": "Only the fake child own stdin buffer is flushed, then a fixed marker is written with WriteConsoleInputW and read by Console.ReadLine; no other console attached; unexpected input redacted",
               "child_elevated_by_explicit_test_opt_in": payload.get("elevated"),
               "launch": {"cwd": "<private-CLA-acceptance-project>",
                          "argv": ["<selected-pwsh.exe>", "-NoLogo", "-NoProfile", "-File", "<CLA-owned-bootstrap.ps1>", "-Manifest", "<private-launch.json>"],
                          "stdio": "Inherited genuine console handles; CREATE_NEW_CONSOLE; no pipe or stdin redirect",
                          "test_only_difference": "Omitted -NoExit so the fixed four-second fake test closes its own terminal"}}
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cla", required=True, type=Path)
    parser.add_argument("--powershell", required=True, type=Path)
    parser.add_argument("--allow-elevated", action="store_true",
                        help="Explicitly allow the fake acceptance child to inherit current administrator rights")
    parser.add_argument("--interactive-console", action="store_true", help="Create exactly one visible timed fake console and verify independent lifetime")
    parser.add_argument("--source", action="store_true", help="Developer check using --cla PYTHON_EXE; reports frozen=false")
    args = parser.parse_args()
    command = [str(args.cla.resolve())] + (["-m", "codex_launcher_awarness"] if args.source else [])
    command += ["_launch-smoke", "--powershell", str(args.powershell.resolve())]
    if args.allow_elevated:
        command.append("--allow-elevated")
    if args.interactive_console:
        command.append("--interactive-console")
    # The portable CLI executes the actual child-creation code. This Python
    # wrapper merely validates its sanitized result and cannot provide a venv.
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(key, None)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45,
                            cwd=args.cla.resolve().parent, env=environment,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    owner_exit_time = datetime.now(timezone.utc)
    if result.returncode:
        print(json.dumps({"status": "FAIL", "reason": "portable_cli_failed", "exit_code": result.returncode}))
        return 1
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(json.dumps({"status": "FAIL", "reason": "non_json_stdout"}))
        return 1
    if args.interactive_console:
        if summary.get("status") != "STARTED":
            print(json.dumps({"status": "FAIL", "reason": "console_not_started"}))
            return 1
        summary = finish_console_acceptance(summary, owner_exit_time)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if summary.get("status") == "PASS" and summary.get("frozen") is (not args.source) and summary.get("model_calls") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
