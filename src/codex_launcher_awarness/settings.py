"""Validated private per-user settings. No workstation paths ship in defaults."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import tomllib
from urllib.parse import urlsplit

from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, field_validator
import tomlkit


def app_dir() -> Path:
    # platformdirs resolves Windows Local AppData through Windows folder APIs.
    override = os.environ.get("CLA_DATA_DIR")
    path = Path(override) if override else user_data_path("CLA", appauthor=False, roaming=False)
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    trusted_executables: dict[str, str] = Field(default_factory=dict)
    approved_project_roots: list[str] = Field(default_factory=list)
    engine_paths: dict[str, str] = Field(default_factory=dict)
    local_endpoints: list[str] = Field(default_factory=list)
    python_environments: list[str] = Field(default_factory=list)
    engine_volumes: list[str] = Field(default_factory=list)
    probe_timeout_seconds: float = Field(default=4, ge=0.1, le=15)
    max_output_bytes: int = Field(default=32768, ge=1024, le=131072)
    cache_seconds: int = Field(default=30, ge=0, le=300)
    briefing_max_chars: int = Field(default=6000, ge=1000, le=12000)
    probe_enabled: bool = False

    @field_validator("schema_version")
    @classmethod
    def version(cls, value):
        if value != 1:
            raise ValueError("Unsupported settings schema version")
        return value

    @field_validator("local_endpoints")
    @classmethod
    def local_only(cls, values):
        for value in values:
            parts = urlsplit(value)
            if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or parts.username or parts.password or parts.query or parts.fragment
                    or parts.path not in {"", "/"}):
                raise ValueError("Service endpoints must be credential-free HTTP loopback origins")
        return values

    @field_validator("trusted_executables", "engine_paths")
    @classmethod
    def absolute_paths(cls, values):
        if len(values) > 50:
            raise ValueError("At most 50 configured engines")
        for value in values.values():
            if not Path(value).is_absolute():
                raise ValueError("Executable and engine paths must be absolute")
        return values

    @field_validator("approved_project_roots", "python_environments", "engine_volumes")
    @classmethod
    def bounded_roots(cls, values):
        if len(values) > 32:
            raise ValueError("At most 32 locations may be configured")
        if any(not Path(value).is_absolute() for value in values):
            raise ValueError("Configured roots must be absolute paths")
        return values


def load_settings() -> Settings:
    path = app_dir() / "settings.toml"
    if not path.exists():
        return Settings()
    if path.stat().st_size > 65536:
        raise ValueError("Settings exceed 64 KiB")
    return Settings.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".cla-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        from .integration.acl import secure_file
        secure_file(Path(name))
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save_settings(settings: Settings):
    checked = Settings.model_validate(settings.model_dump())
    atomic_write(app_dir() / "settings.toml", tomlkit.dumps(checked.model_dump()))


def write_private_json(path: Path, value, *, exclusive=False):
    from .evidence.redact import redact
    text = json.dumps(redact(value), ensure_ascii=False, indent=2, allow_nan=False)
    if exclusive:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
        from .integration.acl import secure_file
        secure_file(path)
    else:
        atomic_write(path, text)


def project_allowed(path: Path, settings: Settings) -> bool:
    candidate = path.resolve()
    return any(candidate.is_relative_to(Path(root).resolve()) for root in settings.approved_project_roots)
