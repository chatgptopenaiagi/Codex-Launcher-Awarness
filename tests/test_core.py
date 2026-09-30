from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from codex_launcher_awarness.evidence import Capability, Snapshot, redact, redact_text
from codex_launcher_awarness.evidence.demo import demo_snapshot
from codex_launcher_awarness.briefing import make_briefing
from codex_launcher_awarness.settings import Settings, save_settings, load_settings


def test_unknown_is_not_zero_or_healthy():
    cap = Capability(id="gpu")
    assert cap.readiness == "unknown"
    assert cap.version is None
    assert "used_bytes" not in cap.values
    assert cap.evidence_id and cap.observed_at and cap.expires_at


def test_stale_does_not_mutate_original_evidence():
    cap = Capability(id="cpu", readiness="verified", expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    assert cap.effective_readiness() == "stale"
    assert cap.readiness == "verified"


@pytest.mark.parametrize("budget", [1000, 2000, 6000, 12000])
def test_briefing_budget_provenance_and_secret_redaction(budget):
    snapshot = demo_snapshot()
    secret = uuid.uuid4().hex
    text = make_briefing(snapshot, "C:/Projects/Demo", "password=" + secret + " " + "x"*14000, max_chars=budget)
    assert len(text) <= budget
    assert secret not in text
    assert "DEMO" in text and "Token estimate" in text
    assert snapshot.session_id in text


def test_redaction_applies_before_private_and_public_storage():
    secrets = [uuid.uuid4().hex for _ in range(4)]
    data = {"api_key": secrets[0], "note": f"secret={secrets[1]} token:{secrets[2]} Bearer {secrets[3]}", "path": "C:\\Users\\Demo\\private"}
    private = json.dumps(redact(data))
    assert all(secret not in private for secret in secrets)
    assert "Demo" not in json.dumps(redact(data, public=True))


def test_validated_private_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CLA_DATA_DIR", str(tmp_path))
    settings = Settings(local_endpoints=["http://127.0.0.1:8080"])
    save_settings(settings)
    assert load_settings() == settings
    with pytest.raises(ValueError):
        Settings(local_endpoints=["http://example.com:8080"])
    with pytest.raises(ValueError):
        Settings(local_endpoints=["http://user:secret@127.0.0.1"])


def test_headless_imports_do_not_load_gui_or_gpu():
    code = "import codex_launcher_awarness.cli, codex_launcher_awarness.mcp.server; import sys; assert not any(x in sys.modules for x in ['PySide6','torch','tensorflow','cupy']); print('headless-ok')"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "headless-ok"


def test_cli_version_help_and_demo(tmp_path):
    env = {**os.environ, "CLA_DATA_DIR": str(tmp_path)}
    for args in [["--version"], ["--help"], ["scan", "--json", "--demo"]]:
        run = subprocess.run([sys.executable, "-m", "codex_launcher_awarness", *args], env=env, capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stderr
        assert "0.1.0" in run.stdout or "CLA" in run.stdout or '"demo": true' in run.stdout


def test_persistent_writes_require_explicit_scope(tmp_path):
    env = {**os.environ, "CLA_DATA_DIR": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "codex_launcher_awarness", "integrate", "--apply"], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "explicit --scope" in result.stderr
