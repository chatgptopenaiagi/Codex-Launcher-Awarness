"""Syntax-preserving CLA-owned Codex configuration and allowlisted inventory."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Mapping

import tomlkit

SERVER_NAME = "cla_awareness"
GUIDANCE = """<!-- CLA:BEGIN -->
When current workstation capabilities matter, query CLA awareness tools and check
their timestamps, evidence, and limitations. Installed, configured, reachable,
and capability-verified are separate findings. Refresh volatile resources before
consequential work. Use verified specialist tools for actual computation.
<!-- CLA:END -->"""


class IntegrationError(ValueError):
    """A safe, actionable refusal without modifying Codex configuration."""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def build_mcp_command() -> list[str]:
    """Return the actual installed console runtime, never an ambiguous python."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().with_name("cla-mcp.exe")
        if not candidate.is_file():
            raise IntegrationError("Portable cla-mcp.exe is missing beside this executable.")
        return [str(candidate)]
    python = Path(sys.executable).resolve()
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    if not python.is_file():
        raise IntegrationError("The installed CLA Python console runtime is unavailable.")
    return [str(python), "-m", "codex_launcher_awarness.mcp.server"]


def _toml_value(value: Any) -> str:
    return tomlkit.dumps({"value": value}).partition("=")[2].strip()


def session_overrides(project: str, session_id: str) -> list[str]:
    command = build_mcp_command()
    fields = {
        "command": command[0], "args": command[1:], "enabled": True, "required": True,
        "startup_timeout_sec": 20.0,
        "env": {"CLA_PROJECT_ROOT": project, "CLA_SESSION_ID": session_id},
    }
    result: list[str] = []
    for key, value in fields.items():
        if isinstance(value, dict):
            for env_key, env_value in value.items():
                result.extend(["-c", f"mcp_servers.{SERVER_NAME}.env.{env_key}={_toml_value(env_value)}"])
        else:
            result.extend(["-c", f"mcp_servers.{SERVER_NAME}.{key}={_toml_value(value)}"])
    return result


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _table_hash(value: Any) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _read(path: Path) -> bytes:
    if not path.exists():
        return b""
    if path.stat().st_size > 2_000_000:
        raise IntegrationError("Codex configuration exceeds the 2 MB safety limit.")
    return path.read_bytes()


def _parse(raw: bytes):
    try:
        return tomlkit.parse(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError, tomlkit.exceptions.ParseError) as exc:
        raise IntegrationError("Codex TOML is malformed; no changes were made.") from exc


def _servers(document):
    value = document.get("mcp_servers", {})
    if not isinstance(value, Mapping):
        raise IntegrationError("Codex mcp_servers must be a TOML table; no changes were made.")
    return value


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".cla-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        from .acl import secure_file
        secure_file(Path(temporary), preserve_from=path if path.exists() else None)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def config_inventory(project: str | Path | None = None) -> dict[str, Any]:
    """Read config only, never auth files, commands' env values or other secrets."""
    paths = [codex_home() / "config.toml"]
    if project:
        target = Path(project).resolve()
        # Bounded ancestor metadata reads account for supported project precedence.
        paths.extend([p / ".codex" / "config.toml" for p in list(target.parents)[::-1][-16:] + [target]])
    layers = []
    for path in dict.fromkeys(paths):
        layer: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "scope": "user" if path == paths[0] else "project"}
        if path.is_file():
            try:
                document = tomllib.loads(_read(path).decode("utf-8-sig"))
                layer["settings"] = {key: document[key] for key in ("model", "sandbox_mode", "approval_policy", "profile") if isinstance(document.get(key), str)}
                layer["mcp_servers"] = [{"name": name, "enabled": item.get("enabled", True),
                                         "transport": "stdio" if "command" in item else "http" if "url" in item else "unknown",
                                         "state": "configured", "handshake": "not_run"}
                                        for name, item in list(_servers(document).items())[:100] if isinstance(item, dict)]
                filenames = document.get("project_doc_fallback_filenames", [])
                layer["project_doc_fallback_filenames"] = [x[:120] for x in filenames[:20] if isinstance(x, str)] if isinstance(filenames, list) else []
            except (ValueError, OSError, TypeError):
                layer["error"] = "configuration_unreadable_or_malformed"
        layers.append(layer)
    return {"codex_home": str(codex_home()), "layers": layers,
            "limitations": ["No server was connected. Configured does not mean reachable.",
                             "Project layers load only when Codex trusts the project; managed/invocation settings may override these observations."]}


def guidance_status(project: str | Path) -> dict[str, Any]:
    target = Path(project).resolve()
    roots = [codex_home(), *list(target.parents)[::-1][-16:], target]
    found = []
    for root in roots:
        override = root / "AGENTS.override.md"
        agents = root / "AGENTS.md"
        if override.is_file():
            found.append({"path": str(override), "selected_over_agents_md": True})
        elif agents.is_file():
            found.append({"path": str(agents), "selected_over_agents_md": False})
    return {"found": found, "offered_block": GUIDANCE, "installed": False,
            "limitation": "CLA does not modify guidance. Custom fallback filenames may also apply."}


class IntegrationManager:
    """Only explicit apply/remove calls write. Plans detect concurrent edits."""

    def __init__(self, settings=None, *, state_dir: Path | None = None):
        if state_dir is None:
            from ..settings import app_dir
            state_dir = app_dir()
        self.state_dir = Path(state_dir)

    def _target(self, scope: str, project: str | Path | None) -> Path:
        if scope == "user":
            return codex_home() / "config.toml"
        if scope == "project" and project:
            target = Path(project).expanduser().resolve()
            if not target.is_dir():
                raise IntegrationError("Project scope requires an existing project directory.")
            return target / ".codex" / "config.toml"
        raise IntegrationError("Explicit integration scope must be user or project (with a project path).")

    def _record_path(self, target: Path) -> Path:
        return self.state_dir / "integration" / f"{_sha(str(target).casefold().encode())}.json"

    def preview(self, scope: str = "user", project: str | Path | None = None) -> dict[str, Any]:
        target = self._target(scope, project)
        before = _read(target)
        doc = _parse(before)
        command = build_mcp_command()
        table = {"command": command[0], "args": command[1:], "enabled": True, "startup_timeout_sec": 20.0}
        existing = _servers(doc).get(SERVER_NAME)
        state = "add"
        if existing is not None:
            if not isinstance(existing, Mapping):
                raise IntegrationError("The existing cla_awareness entry is not a table; no overwrite is allowed.")
            record_path = self._record_path(target)
            if not record_path.exists():
                raise IntegrationError("cla_awareness already exists and is not managed by this CLA installation; no overwrite is allowed.")
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if _table_hash(existing.unwrap()) != record["table_hash"]:
                raise IntegrationError("The CLA table has been edited; refusing to overwrite it.")
            if existing.unwrap() != table:
                raise IntegrationError("The managed runtime differs. Remove the unchanged CLA integration before applying the new runtime.")
            state = "unchanged"
        rendered = tomlkit.document()
        rendered["mcp_servers"] = {SERVER_NAME: table}
        def quote(s: str) -> str:
            return "'" + s.replace("'", "''") + "'"
        return {"schema_version": "1.0", "scope": scope, "project": str(project) if project else None,
                "target": str(target), "before_sha256": _sha(before), "action": state, "table": table,
                "toml": tomlkit.dumps(rendered),
                "codex_mcp_add": "codex mcp add cla_awareness -- " + " ".join(quote(s) for s in command),
                "warning": "Apply edits only this CLA table. No other MCP servers or runtime settings are changed."}

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        target = self._target(plan["scope"], plan.get("project"))
        if str(target) != plan["target"]:
            raise IntegrationError("Integration plan target changed.")
        before = _read(target)
        if _sha(before) != plan["before_sha256"]:
            raise IntegrationError("Codex configuration changed since preview; preview again.")
        fresh = self.preview(plan["scope"], plan.get("project"))
        if fresh["table"] != plan["table"]:
            raise IntegrationError("CLA runtime changed since preview; preview again.")
        if fresh["action"] == "unchanged":
            return {"status": "unchanged", "target": str(target), "sha256": _sha(before)}
        doc = _parse(before)
        if "mcp_servers" not in doc:
            doc["mcp_servers"] = tomlkit.table()
        if SERVER_NAME in doc["mcp_servers"]:
            raise IntegrationError("A CLA table appeared concurrently.")
        doc["mcp_servers"][SERVER_NAME] = plan["table"]
        after = tomlkit.dumps(doc).encode("utf-8")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.state_dir / "backups" / f"codex-{timestamp}.toml"
        _atomic(backup, before)
        if _sha(_read(target)) != plan["before_sha256"]:
            raise IntegrationError("Codex configuration changed before commit; no configuration changes made.")
        _atomic(target, after)
        record = {"target": str(target), "table_hash": _table_hash(plan["table"]),
                  "before_sha256": _sha(before), "after_sha256": _sha(after), "backup": str(backup), "at": timestamp}
        _atomic(self._record_path(target), json.dumps(record, indent=2).encode())
        return {"status": "applied", **record}

    def remove(self, scope: str = "user", project: str | Path | None = None) -> dict[str, Any]:
        target = self._target(scope, project)
        record_path = self._record_path(target)
        if not record_path.exists():
            raise IntegrationError("No CLA ownership record exists; refusing to remove configuration.")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        before = _read(target)
        doc = _parse(before)
        existing = _servers(doc).get(SERVER_NAME)
        if existing is None:
            record_path.unlink()
            return {"status": "already_removed", "target": str(target)}
        if _table_hash(existing.unwrap()) != record["table_hash"]:
            raise IntegrationError("CLA-managed configuration was modified; refusing to remove user edits.")
        del doc["mcp_servers"][SERVER_NAME]
        after = tomlkit.dumps(doc).encode()
        if _sha(_read(target)) != _sha(before):
            raise IntegrationError("Codex configuration changed during removal; retry.")
        _atomic(target, after)
        record_path.unlink()
        return {"status": "removed", "target": str(target), "before_sha256": _sha(before), "after_sha256": _sha(after),
                "note": "Only the unchanged CLA table was removed; no whole-file backup was restored."}
