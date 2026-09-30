import json
import os
import tomllib
import uuid
from pathlib import Path

import pytest

from codex_launcher_awarness.integration import IntegrationError, IntegrationManager, config_inventory, guidance_status
from codex_launcher_awarness.integration.config import session_overrides


@pytest.fixture
def integration(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    return IntegrationManager(state_dir=tmp_path / "private"), home / "config.toml"


def test_preview_read_only_and_actual_absolute_runtime(integration):
    manager, config = integration
    plan = manager.preview("user")
    assert not config.exists()
    assert Path(plan["table"]["command"]).is_absolute()
    assert tomllib.loads(plan["toml"])["mcp_servers"]["cla_awareness"] == plan["table"]
    assert "codex mcp add cla_awareness --" in plan["codex_mcp_add"]


def test_config_preserved_idempotent_and_owned_rollback(integration):
    manager, config = integration
    original = '# keep this comment\nmodel = "existing-model"\n\n[mcp_servers.cua_repl]\ncommand = "preserve-me"\n\n[plugins.example]\nenabled = true\n'
    config.write_text(original, encoding="utf-8")
    result = manager.apply(manager.preview("user"))
    assert result["status"] == "applied"
    assert Path(result["backup"]).read_text() == original
    assert manager.apply(manager.preview("user"))["status"] == "unchanged"
    doc = config.read_text()
    assert '# keep this comment' in doc and 'command = "preserve-me"' in doc
    # A later unrelated edit must survive managed rollback.
    config.write_text(doc.replace('existing-model', 'new-user-model'), encoding="utf-8")
    result = manager.remove("user")
    assert result["status"] == "removed"
    final = tomllib.loads(config.read_text())
    assert final["model"] == "new-user-model"
    assert "cla_awareness" not in final["mcp_servers"]
    assert final["mcp_servers"]["cua_repl"]["command"] == "preserve-me"
    assert final["plugins"]["example"]["enabled"] is True


def test_concurrent_edit_refused(integration):
    manager, config = integration
    config.write_text('model = "one"\n')
    plan = manager.preview("user")
    config.write_text('model = "two"\n')
    with pytest.raises(IntegrationError, match="changed since preview"):
        manager.apply(plan)
    assert config.read_text() == 'model = "two"\n'


def test_modified_owned_table_not_removed(integration):
    manager, config = integration
    manager.apply(manager.preview("user"))
    config.write_text(config.read_text().replace("enabled = true", "enabled = false"))
    before = config.read_bytes()
    with pytest.raises(IntegrationError, match="modified"):
        manager.remove("user")
    assert config.read_bytes() == before


@pytest.mark.parametrize("content", ['model = [', '[mcp_servers.cla_awareness]\ncommand="other"\n'])
def test_malformed_or_unowned_refused(integration, content):
    manager, config = integration
    config.write_text(content)
    with pytest.raises(IntegrationError):
        manager.preview("user")
    assert config.read_text() == content


def test_explicit_project_scope_only(integration, tmp_path):
    manager, config = integration
    project = tmp_path / "project"
    project.mkdir()
    plan = manager.preview("project", project)
    manager.apply(plan)
    assert (project / ".codex" / "config.toml").is_file()
    assert not config.exists()
    assert manager.remove("project", project)["status"] == "removed"
    with pytest.raises(IntegrationError):
        manager.preview("all")


def test_allowlist_inventory_does_not_expose_secret_env_or_urls(integration):
    _, config = integration
    canary = "cla-canary-" + uuid.uuid4().hex
    config.write_text('[mcp_servers.external]\nurl="https://secret-canary.example/token"\n[mcp_servers.external.env]\nAPI_KEY="' + canary + '"\n')
    result = json.dumps(config_inventory())
    assert canary not in result and "secret-canary" not in result
    assert '"state": "configured"' in result and '"handshake": "not_run"' in result


def test_guidance_override_detected_without_writing(integration, tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "AGENTS.md").write_text("stable")
    (folder / "AGENTS.override.md").write_text("override")
    result = guidance_status(folder)
    assert any(x["path"].endswith("AGENTS.override.md") for x in result["found"])
    assert not result["installed"]
    assert (folder / "AGENTS.md").read_text() == "stable"


def test_session_overrides_are_parseable_toml_and_do_not_edit(integration):
    _, config = integration
    arguments = session_overrides(r"C:\Projects\O'Brien; [$test] 日本", "a" * 32)
    assert not config.exists()
    assert arguments[::2] == ["-c"] * (len(arguments) // 2)
    for argument in arguments[1::2]:
        tomllib.loads(argument)
    assert any("CLA_SESSION_ID=" in arg for arg in arguments)


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL preservation")
def test_windows_config_acl_preserved(integration):
    import ctypes
    from ctypes import wintypes as wt
    manager, config = integration
    config.write_text('model="unchanged"\n', encoding="utf-8")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.GetFileSecurityW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    def descriptor(path):
        length = wt.DWORD()
        advapi.GetFileSecurityW(str(path), 4, None, 0, ctypes.byref(length))
        buffer = ctypes.create_string_buffer(length.value)
        assert advapi.GetFileSecurityW(str(path), 4, buffer, length, ctypes.byref(length))
        return buffer.raw
    before = descriptor(config)
    manager.apply(manager.preview("user"))
    assert descriptor(config) == before
    manager.remove("user")
    assert descriptor(config) == before
