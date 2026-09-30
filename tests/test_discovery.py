"""Synthetic provider tests; hardware/live specialist acceptance is recorded separately."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from codex_launcher_awarness.discovery import DiscoveryService
from codex_launcher_awarness.discovery import service, specialists
from codex_launcher_awarness.discovery.parsers import number, nvidia_csv, wsl_list
from codex_launcher_awarness.discovery.process import ProbeResult, run_probe
from codex_launcher_awarness.discovery.specialists import llama_health, maxima_check, run_wrapper, validate_endpoint
from codex_launcher_awarness.settings import Settings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CLA_DATA_DIR", str(tmp_path / "private"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "program-files"))
    return tmp_path


def test_passive_does_not_execute_or_import_gpu(isolated, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("passive scan executed code"))
    monkeypatch.setattr(service, "run_probe", forbidden)
    monkeypatch.setattr(service, "run_wrapper", forbidden)
    before = set(sys.modules)
    snapshot = DiscoveryService(Settings()).scan()
    assert snapshot.schema_version == 1
    assert not ({"torch", "transformers", "PySide6", "pynvml"} & (set(sys.modules) - before))
    assert all(record.evidence_id and record.observed_at and record.expires_at for record in snapshot.capabilities)
    assert next(record for record in snapshot.capabilities if record.id == "hardware.memory").units["total_bytes"] == "bytes"
    assert next(record for record in snapshot.capabilities if record.id == "tool.codex").installation == "not_detected"
    forbidden.assert_not_called()


def test_candidates_multiple_paths_and_wrappers(isolated, monkeypatch):
    one, two = isolated / "one space", isolated / "two"
    one.mkdir(); two.mkdir()
    for folder, filename in ((one, "codex.cmd"), (one, "codex.ps1"), (two, "codex.exe"), (two, "python.exe")):
        (folder / filename).touch()
    monkeypatch.setenv("PATH", os.pathsep.join([str(one), str(two), str(one), "."]))
    monkeypatch.setenv("ProgramFiles", str(isolated / "unused"))
    candidates = service.resolve_candidates("codex")
    assert [Path(entry["path"]).name for entry in candidates] == ["codex.cmd", "codex.ps1", "codex.exe"]
    assert len(service.resolve_candidates("python")) == 1


def test_engine_hint_not_authorization(isolated, monkeypatch):
    executable = isolated / "blender.exe"
    executable.touch()
    blocked = Mock(side_effect=AssertionError("hint executed"))
    monkeypatch.setattr(service, "run_probe", blocked)
    monkeypatch.setattr(service, "run_wrapper", blocked)
    snapshot = DiscoveryService(Settings(engine_paths={"blender": str(executable)})).scan(allow_probes=True)
    blender = next(record for record in snapshot.capabilities if record.id == "tool.blender")
    assert blender.installation == "detected"
    assert blender.configuration == "configured"
    assert blender.readiness == "unknown"
    assert blender.values["trusted_for_probes"] is False
    blocked.assert_not_called()


@pytest.mark.parametrize("value", ["N/A", "[Not Supported]", "", "nan", "inf", "-1"])
def test_missing_metric_not_zero(value):
    assert number(value) is None


def test_gpu_aggregate_units_and_unsupported():
    devices = nvidia_csv("Synthetic GPU, 555.12, 6144, 5102, 1042, [Not Supported], N/A, 0, GPU-private\n")
    assert devices[0]["memory_used_mib"] == 5102
    assert devices[0]["utilization_percent"] is None
    assert devices[0]["temperature_celsius"] is None
    assert "uuid" not in devices[0]


@pytest.mark.parametrize("text", ["bad", "GPU,not-driver,1,2,3,4,5,0,id"])
def test_malformed_gpu(text):
    with pytest.raises(ValueError):
        nvidia_csv(text)


def test_gpu_provider_failure_structured(isolated, monkeypatch):
    executable = isolated / "nvidia-smi.exe"; executable.touch()
    monkeypatch.setattr(service, "run_probe", lambda *args, **kwargs: ProbeResult(0, "bad", "", 1))
    provider = DiscoveryService(Settings(trusted_executables={"nvidia_smi": str(executable)}))
    record = provider._gpu(None)[0]
    assert record.error["code"] == "malformed_gpu_response"
    assert record.readiness == "unavailable"
    assert record.values["devices"] == []


def test_gpu_driver_support_separate(isolated, monkeypatch):
    executable = isolated / "nvidia-smi.exe"; executable.touch()
    outputs = iter(["GPU, 555.12, 100, 90, 10, 3, 40, 0, ignored", "CUDA Version : 12.5"])
    monkeypatch.setattr(service, "run_probe", lambda *args, **kwargs: ProbeResult(0, next(outputs), "", 1))
    record = DiscoveryService(Settings(trusted_executables={"nvidia_smi": str(executable)}))._gpu(None)[0]
    assert record.values["driver_cuda_support"] == "12.5"
    assert record.values["pytorch_execution"] == "not_run"
    assert record.values["warnings"]
    assert all("Qwen" not in warning for warning in record.values["warnings"])


def test_cancelled_scan_is_partial(isolated):
    cancel = threading.Event(); cancel.set()
    snapshot = DiscoveryService(Settings()).scan(cancel=cancel)
    assert snapshot.capabilities == []
    assert any("cancelled" in text for text in snapshot.limitations)


def test_cache_is_copy_and_force_refresh(isolated):
    provider = DiscoveryService(Settings())
    first = provider.scan(); original = first.session_id
    first.capabilities.clear()
    second = provider.scan()
    assert second.session_id == original and second.capabilities
    assert provider.scan(force=True).session_id != original


def test_project_bounds_and_manifest_not_ready(isolated):
    private_marker = uuid4().hex
    approved = isolated / "approved"; approved.mkdir()
    project = approved / "demo"; project.mkdir()
    (project / "AGENTS.override.md").write_text("untrusted instructions", encoding="utf-8")
    (project / "pyproject.toml").write_text(private_marker, encoding="utf-8")
    provider = DiscoveryService(Settings(approved_project_roots=[str(approved)]))
    with pytest.raises(ValueError, match="approved"):
        provider.scan(isolated)
    snapshot = provider.scan(project)
    record = next(record for record in snapshot.capabilities if record.id == "project.capabilities")
    assert record.readiness == "unknown"
    assert record.values["guidance_override_present"] is True
    assert private_marker not in snapshot.model_dump_json()


def test_fixed_metadata_no_heavy_import(isolated):
    root = isolated / "python environment"; root.mkdir()
    (root / "python.exe").touch()
    info = root / "Lib" / "site-packages" / "torch-9.9.dist-info"; info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: torch\nVersion: 9.9\n", encoding="utf-8")
    record = DiscoveryService(Settings(python_environments=[str(root)]))._python_environments()[0]
    assert record.values["packages"] == {"torch": "9.9"}
    assert record.readiness == "unknown"
    assert record.values["gpu_execution"] == "not_run"


@pytest.mark.parametrize("endpoint", ["https://127.0.0.1:80", "http://evil.invalid:80", "http://127.0.0.1:80/a",
                                       "http://user:secret@127.0.0.1:80", "http://127.0.0.1", "http://127.0.0.1:80?token=x"])
def test_endpoint_validation(endpoint):
    with pytest.raises(ValueError):
        validate_endpoint(endpoint)


def _mock_http(monkeypatch, bodies, *, delay=0, status=200, cancel_on_read=None, header_wait=False):
    requests, sockets = [], []
    bodies = iter(bodies)
    class Socket:
        def __init__(self):
            self.timeouts = []
            self.closed = threading.Event()
        def settimeout(self, value): self.timeouts.append(value)
        def shutdown(self, how): self.closed.set()
        def close(self): self.closed.set()
    class Response:
        def __init__(self):
            self.data, self.offset, self.status = next(bodies), 0, status
        def read1(self, limit):
            if delay: time.sleep(delay)
            if cancel_on_read: cancel_on_read.set()
            chunk = self.data[self.offset:self.offset + limit]
            self.offset += len(chunk)
            return chunk
        def close(self): pass
        def isclosed(self): return False
    class Connection:
        def __init__(self, host, port, timeout):
            self.sock = Socket(); sockets.append(self.sock)
        def connect(self): pass
        def request(self, method, path, headers): requests.append((method, path, headers))
        def getresponse(self):
            if header_wait:
                self.sock.closed.wait(2)
                raise OSError("test-owned socket interrupted")
            return Response()
        def close(self): self.sock.close()
    monkeypatch.setattr(specialists.http.client, "HTTPConnection", Connection)
    return requests, sockets


def test_service_response_redacts_metadata(monkeypatch):
    private_marker = "sk-" + uuid4().hex
    bodies = [json.dumps({"status": "ok", "secret": private_marker}).encode(),
              json.dumps({"data": [{"id": "private/path/" + private_marker}]}).encode()]
    requests, sockets = _mock_http(monkeypatch, bodies)
    result = llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=1024)
    assert result["responses"]["model_count"] == 1
    assert private_marker not in json.dumps(result)
    assert [item[1] for item in requests] == ["/health", "/v1/models"]
    assert all(sock.closed.is_set() for sock in sockets)


def test_service_malformed_and_cancel(monkeypatch):
    _mock_http(monkeypatch, [b'[]'])
    assert llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=1024)["error"] == "malformed_response"
    event = threading.Event(); event.set()
    assert llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=1024, cancel=event)["error"] == "cancelled"


@pytest.mark.parametrize("body,expected", [(b'[' * 2000 + b'0' + b']' * 2000, "malformed_response"),
                                           (b'{"too_large":"' + b'x' * 12000 + b'"}', "response_limit"),
                                           (b'{"invalid":', "malformed_response")])
def test_service_adversarial_json_bounded(monkeypatch, body, expected):
    _mock_http(monkeypatch, [body])
    assert llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=8192)["error"] == expected


def test_service_redirect_not_followed(monkeypatch):
    requests, _ = _mock_http(monkeypatch, [b''], status=302)
    result = llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=1024)
    assert result["error"] == "redirect_rejected"
    assert len(requests) == 1


def test_service_total_deadline_slow_body(monkeypatch):
    _, sockets = _mock_http(monkeypatch, [b'{"status":"ok"}'], delay=.03)
    started = time.monotonic()
    result = llama_health("http://127.0.0.1:8080", timeout=.05, max_bytes=1024)
    assert result["error"] == "timeout"
    assert time.monotonic() - started < .25
    assert sockets[0].timeouts[1] < sockets[0].timeouts[0]


def test_service_body_cancellation(monkeypatch):
    event = threading.Event()
    _mock_http(monkeypatch, [b'{"status":"ok"}'], cancel_on_read=event)
    assert llama_health("http://127.0.0.1:8080", timeout=1, max_bytes=1024, cancel=event)["error"] == "cancelled"


def test_service_slow_headers_interrupted(monkeypatch):
    _, sockets = _mock_http(monkeypatch, [], header_wait=True)
    started = time.monotonic()
    result = llama_health("http://127.0.0.1:8080", timeout=.05, max_bytes=1024)
    assert result["error"] == "timeout"
    assert time.monotonic() - started < .25
    assert sockets[0].closed.is_set()


def test_real_loopback_socket_health_and_deadline():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.server.slow:
                try:
                    # An unfinished header must be cut off by CLA's whole-request deadline.
                    self.connection.sendall(b'HTTP/1.0 200 OK\r\nX-Slow: ')
                    for _ in range(40):
                        self.connection.sendall(b'x')
                        time.sleep(.025)
                except OSError:
                    pass
                return
            body = b'{"status":"ok"}' if self.path == '/health' else b'{"data":[{"id":"synthetic"}]}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.slow = False
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    worker.start()
    try:
        endpoint = f'http://127.0.0.1:{server.server_port}'
        result = llama_health(endpoint, timeout=1, max_bytes=1024)
        assert result['error'] is None and result['responses']['model_count'] == 1
        server.slow = True
        started = time.monotonic()
        result = llama_health(endpoint, timeout=.12, max_bytes=1024)
        assert result['error'] == 'timeout'
        assert time.monotonic() - started < .5
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=.5)


def test_wsl_metadata_only():
    output = "  NAME            STATE           VERSION\n* Demo Linux      Stopped         2\n  Other           Running         2\n"
    rows = wsl_list(output)
    assert rows[0] == {"name": "Demo Linux", "state": "Stopped", "version": 2, "default": True}
    assert rows[1]["state"] == "Running"


def test_probe_success_failure_and_timeout():
    executable = Path(sys.executable)
    assert run_probe(executable, ["-I", "-c", "print('ok')"]).stdout.strip() == "ok"
    assert run_probe(executable, ["-I", "-c", "raise SystemExit(7)"]).error == "nonzero_exit"
    assert run_probe(executable, ["-I", "-c", "import time; time.sleep(4)"], timeout=.15).error == "timeout"
    assert run_probe(executable, ["-I", "-c", "print('x'*100000)"], max_bytes=1024).error == "output_limit"


def test_probe_dll_search_context_only_covers_creation(monkeypatch):
    from contextlib import contextmanager
    from codex_launcher_awarness.discovery import process
    active = []
    events = []
    real_popen = process.subprocess.Popen
    @contextmanager
    def guarded():
        active.append(True); events.append("enter")
        try:
            yield
        finally:
            active.pop(); events.append("restore")
    def start(*args, **kwargs):
        assert active == [True]
        child = real_popen(*args, **kwargs)
        events.append("created")
        return child
    monkeypatch.setattr(process, "clean_child_dll_search", guarded)
    monkeypatch.setattr(process.subprocess, "Popen", start)
    result = run_probe(Path(sys.executable), ["-I", "-c", "print('owned-child')"])
    assert result.error is None
    assert events == ["enter", "created", "restore"]
    assert active == []


def test_probe_missing_denied_cancel(isolated, monkeypatch):
    assert run_probe(isolated / "missing.exe", []).error == "executable_missing"
    event = threading.Event(); event.set()
    assert run_probe(Path(sys.executable), [], cancel=event).error == "cancelled"
    private_marker = uuid4().hex
    monkeypatch.setattr("subprocess.Popen", Mock(side_effect=PermissionError(private_marker)))
    result = run_probe(Path(sys.executable), [])
    assert result.error == "access_denied"
    assert private_marker not in result.stderr


def test_wrapper_no_shell_interpolation(isolated, monkeypatch):
    pwsh = isolated / "pwsh.exe"; pwsh.touch()
    calls = []
    monkeypatch.setattr(specialists, "run_probe", lambda *args, **kwargs: calls.append((args, kwargs)) or ProbeResult(0, "", "", 1))
    for bad in ("x%USERPROFILE%.bat", "x&bad.bat", "x^bad.cmd"):
        assert run_wrapper(isolated / bad, ["--version"], pwsh).error == "unsupported_batch_path_characters"
    assert not calls
    wrapper = isolated / "space O'Brien [日] $tool.cmd"
    assert run_wrapper(wrapper, ["--version"], pwsh).error is None
    import base64
    script = base64.b64decode(calls[0][0][1][-1]).decode("utf-16le")
    assert "O''Brien" in script and "Invoke-Expression" not in script


def test_maxima_raw_version_and_fixed_arithmetic(isolated, monkeypatch):
    calls = []
    version = "Maxima branch_synthetic_dirty"
    outputs = iter([version, "CLA_ARITH=4\nCLA_FACTOR=(x-1)*(x+1)\nCLA_FACTOR_EQ=true\nCLA_DIFF=3*x^2\nCLA_INTEGRAL=1/3\n"])
    def fake(executable, args, pwsh, **kwargs):
        calls.append((args, kwargs))
        assert kwargs["environment"]["MAXIMA_USERDIR"].startswith(str(isolated))
        if any(arg.startswith("--batch=") for arg in args):
            path = Path(next(arg.partition("=")[2] for arg in args if arg.startswith("--batch=")))
            assert path.read_text() == specialists.MAXIMA_CHECK
            assert "\\" not in next(arg for arg in args if arg.startswith("--batch="))
        return ProbeResult(0, next(outputs), "", 1)
    monkeypatch.setattr(specialists, "run_wrapper", fake)
    result = maxima_check(isolated / "maxima.bat", None, timeout=4, max_bytes=1024, cancel=None)
    assert result["version"] == version
    assert result["math_check"] == "verified"
    assert all("--no-init" in args for args, kwargs in calls)
    assert not list((isolated / "private" / "probes").iterdir())


def test_mcp_inventory_not_handshake(isolated):
    private_marker = "sk-" + uuid4().hex
    root = isolated / "codex"; root.mkdir()
    (root / "config.toml").write_text(f'[mcp_servers.synthetic]\ncommand="{private_marker}"\n[mcp_servers.synthetic.env]\nTOKEN="{private_marker}"\n', encoding="utf-8")
    record = DiscoveryService(Settings())._mcp_inventory(None)[0]
    assert record.configuration == "configured"
    assert record.readiness == "unknown"
    assert private_marker not in record.model_dump_json()
