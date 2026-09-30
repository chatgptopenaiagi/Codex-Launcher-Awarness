"""Versioned observations. Readiness is never inferred from installation alone."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expiry(seconds=30) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


STATES = {"unknown", "not_detected", "detected", "configured", "reachable", "verified", "degraded", "unavailable", "stale"}


class Capability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    tags: list[str] = Field(default_factory=list)
    host: str = "windows"
    backend: str = "native"
    installation: str = "unknown"
    resolution_source: str | None = None
    path: str | None = None
    configuration: str = "unknown"
    reachability: str = "unknown"
    readiness: str = "unknown"
    version: str | None = None
    transport: str | None = None
    limitations: list[str] = Field(default_factory=list)
    observed_at: str = Field(default_factory=utc_now)
    expires_at: str = Field(default_factory=expiry)
    evidence_id: str = Field(default_factory=lambda: uuid4().hex)
    probe_method: str = "passive_metadata"
    duration_ms: float = 0
    values: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    error: dict[str, Any] | None = None

    @field_validator("installation", "configuration", "reachability", "readiness")
    @classmethod
    def state(cls, value):
        if value not in STATES:
            raise ValueError("Unknown evidence state")
        return value

    @property
    def stale(self) -> bool:
        return datetime.fromisoformat(self.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)

    def effective_readiness(self) -> str:
        return "stale" if self.stale else self.readiness


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: str = Field(default_factory=utc_now)
    capabilities: list[Capability] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    demo: bool = False

    @field_validator("schema_version")
    @classmethod
    def schema(cls, value):
        if value != 1:
            raise ValueError("Unsupported evidence schema")
        return value

    def sanitized(self, public=False) -> dict:
        from .redact import redact
        return redact(self.model_dump(mode="json"), public=public)
