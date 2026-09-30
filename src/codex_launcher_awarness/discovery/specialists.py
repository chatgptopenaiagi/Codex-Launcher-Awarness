"""Approved specialist health checks; no benchmarks or model inference."""

from __future__ import annotations

import base64
import http.client
import json
import os
import re
import socket
import tempfile
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .process import ProbeResult, run_probe

MAXIMA_CHECK = '''display2d:false$
printf(true,"CLA_ARITH=~a~%",2+2)$
printf(true,"CLA_FACTOR=~a~%",factor(x^2-1))$
printf(true,"CLA_FACTOR_EQ=~a~%",is(ratsimp(factor(x^2-1)-(x-1)*(x+1))=0))$
printf(true,"CLA_DIFF=~a~%",diff(x^3,x))$
printf(true,"CLA_INTEGRAL=~a~%",integrate(x^2,x,0,1))$
quit()$
'''


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_wrapper(executable: Path, arguments: list[str], powershell: Path | None, *,
                environment: dict[str, str] | None = None, **kwargs) -> ProbeResult:
    if executable.suffix.lower() not in {".bat", ".cmd", ".ps1"}:
        return run_probe(executable, arguments, environment=environment, **kwargs)
    if powershell is None or not powershell.is_file():
        return ProbeResult(None, "", "", 0, "trusted_powershell_required")
    # cmd.exe expands these characters even through some quoted batch arguments.
    # Batch paths outside this conservative subset remain inventory-only.
    if executable.suffix.lower() in {".bat", ".cmd"} and any(
            c in value for value in [str(executable), *arguments] for c in '%!^&|<>"\r\n'):
        return ProbeResult(None, "", "", 0, "unsupported_batch_path_characters")
    script = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; "
    if executable.suffix.lower() == ".ps1":
        script += "$PSNativeCommandArgumentPassing='Standard'; "
    # @(... ) is an array expression, not splatting. Passing that expression to
    # a .ps1 shim gives it one nested array argument, which npm can stringify as
    # a single prompt. A named, typed array preserves individual CLI arguments.
    script += "[string[]]$claProbeArguments = @(" + ",".join(_ps_literal(arg) for arg in arguments) + "); "
    script += "& " + _ps_literal(str(executable)) + " @claProbeArguments; exit $LASTEXITCODE"
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return run_probe(powershell, ["-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                     environment=environment, **kwargs)


def maxima_check(executable: Path, powershell: Path | None, *, timeout: float,
                 max_bytes: int, cancel: threading.Event | None) -> dict:
    from codex_launcher_awarness.settings import app_dir
    root = app_dir() / "probes"
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="maxima-", dir=root) as folder:
        userdir = Path(folder)
        source = userdir / "cla-check.mac"
        source.write_text(MAXIMA_CHECK, encoding="ascii")
        env = os.environ.copy()
        env.update(MAXIMA_USERDIR=str(userdir), MAXIMA_TEMPDIR=str(userdir),
                   MAXIMA_INITIAL_FOLDER=str(userdir))
        env.pop("MAXIMA_LISP", None)
        args = dict(environment=env, timeout=timeout, max_bytes=max_bytes, cancel=cancel)
        version_started_at = datetime.now(timezone.utc).isoformat()
        version = run_wrapper(executable, ["--no-init", "--version"], powershell, **args)
        version_details = {"evidence_id": str(uuid.uuid4()), "started_at": version_started_at,
                           "observed_at": datetime.now(timezone.utc).isoformat(),
                           "exit_status": version.returncode, "duration_ms": version.duration_ms,
                           "timeout_seconds": timeout, "timed_out": version.error == "timeout",
                           "method": "executable_version_probe", "error": version.error}
        # Preserve the arbitrary build string; do not infer official release provenance.
        version_lines = [line.strip() for line in version.stdout.splitlines() if line.strip().startswith("Maxima ")]
        version_text = version_lines[0][:300] if version_lines else None
        if version.error:
            return {"version": version_text, "version_probe": "failed", "math_check": "not_run",
                    "version_probe_details": version_details,
                    "functional_check_details": {"state": "not_run", "exit_status": None,
                                                  "observed_at": None, "timeout_seconds": None},
                    "error": version.error, "duration_ms": version.duration_ms}
        remaining = max(0.05, timeout - (time.monotonic() - started))
        args["timeout"] = remaining
        check_started_at = datetime.now(timezone.utc).isoformat()
        check = run_wrapper(executable, ["--no-init", "--very-quiet", "--quit-on-error",
                                        "--suppress-input-echo", "--batch=" + source.as_posix()], powershell, **args)
        check_details = {"evidence_id": str(uuid.uuid4()), "started_at": check_started_at,
                         "observed_at": datetime.now(timezone.utc).isoformat(),
                         "exit_status": check.returncode, "duration_ms": check.duration_ms,
                         "timeout_seconds": round(remaining, 4), "timed_out": check.error == "timeout",
                         "method": "actual_capability_check", "error": check.error}
        results = {}
        for line in check.stdout.splitlines():
            match = re.fullmatch(r"CLA_([A-Z_]+)=(.{1,160})", line.strip())
            if match:
                results[match[1].lower()] = match[2].replace(" ", "")
        passed = (not check.error and results.get("arith") == "4" and
                  results.get("factor_eq") == "true" and results.get("diff") == "3*x^2" and
                  results.get("integral") == "1/3")
        return {"version": version_text, "version_probe": "verified" if version_text else "malformed",
                "math_check": "verified" if passed else "failed", "checks": results,
                "version_probe_details": version_details, "functional_check_details": check_details,
                "error": check.error or (None if passed else "unexpected_math_result"),
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "user_initialization": "disabled (--no-init and isolated MAXIMA_USERDIR)",
                "provenance": "observed build string; official release provenance not established"}


def validate_endpoint(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Only explicitly configured loopback HTTP endpoints are supported")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Endpoint must be an origin without credentials, query or path")
    if not parsed.port:
        raise ValueError("Explicit local endpoint port required")
    return endpoint.rstrip("/")


def _http_json(endpoint: str, suffix: str, *, deadline: float, max_bytes: int,
               cancel: threading.Event | None = None) -> tuple[dict | None, str | None]:
    """One owned loopback socket. Watchdog also bounds slow response headers."""
    parsed = urllib.parse.urlsplit(endpoint)
    # Avoid DNS resolution for the only permitted hostname; IPv6 is explicit ::1.
    host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
    remaining = deadline - time.monotonic()
    if cancel is not None and cancel.is_set():
        return None, "cancelled"
    if remaining <= 0:
        return None, "timeout"
    connection = http.client.HTTPConnection(host, parsed.port, timeout=remaining)
    done = threading.Event()
    sockets = []
    stopped = [None]

    def check() -> str | None:
        if cancel is not None and cancel.is_set():
            return "cancelled"
        if time.monotonic() >= deadline:
            return "timeout"
        return None

    def interrupt_owned_socket():
        while not done.wait(0.02):
            reason = check()
            if reason:
                stopped[0] = reason
                target = sockets[0] if sockets else connection.sock
                if target is not None:
                    try:
                        target.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    target.close()
                    return

    watcher = threading.Thread(target=interrupt_owned_socket, daemon=True, name="CLA-loopback-deadline")
    watcher.start()
    response = None
    try:
        connection.connect()
        sockets.append(connection.sock)
        if reason := check():
            return None, reason
        connection.request("GET", suffix, headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if reason := check():
            return None, reason
        if 300 <= response.status < 400:
            return None, "redirect_rejected"
        if response.status != 200:
            return None, "service_unavailable"
        data = bytearray()
        while True:
            if reason := check():
                return None, reason
            if response.isclosed():
                break
            # read1 performs at most one underlying socket read. Resetting its
            # timeout prevents a trickled body from renewing the total budget.
            sockets[0].settimeout(max(0.001, deadline - time.monotonic()))
            chunk = response.read1(min(4096, max_bytes + 1 - len(data)))
            if reason := check():
                return None, reason
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                return None, "response_limit"
        payload = json.loads(data)
        if not isinstance(payload, dict):
            return None, "malformed_response"
        return payload, None
    except (TimeoutError, socket.timeout):
        return None, stopped[0] or check() or "timeout"
    except (OSError, http.client.HTTPException):
        return None, stopped[0] or check() or "service_unavailable"
    except (ValueError, TypeError, RecursionError):
        return None, "malformed_response"
    finally:
        done.set()
        if response is not None:
            response.close()
        connection.close()
        watcher.join(timeout=0.2)


def llama_health(endpoint: str, *, timeout: float, max_bytes: int,
                 cancel: threading.Event | None = None) -> dict:
    endpoint = validate_endpoint(endpoint)
    started = time.monotonic()
    deadline = started + timeout
    responses = {}
    for suffix in ("/health", "/v1/models"):
        if cancel is not None and cancel.is_set():
            return {"error": "cancelled", "responses": responses}
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            return {"error": "timeout", "responses": responses}
        payload, error = _http_json(endpoint, suffix, deadline=deadline, max_bytes=max_bytes, cancel=cancel)
        if error:
            return {"error": error, "responses": responses,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2)}
        if suffix == "/health":
            status = payload.get("status")
            responses["health"] = status if status in {"ok", "loading model", "error"} else "unknown"
        else:
            # Models may contain paths or user-supplied arbitrary strings: do not publish IDs.
            models = payload.get("data")
            responses["model_count"] = len(models) if isinstance(models, list) else None
            responses["model_metadata_available"] = isinstance(models, list)
    return {"error": None, "responses": responses,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)}
