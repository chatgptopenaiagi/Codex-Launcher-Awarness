"""Redaction on collection/storage, briefing, logs and export boundaries."""
from __future__ import annotations
import re

SENSITIVE_KEY = re.compile(r"(?:password|passwd|secret|credential|authorization|cookie|private.?key|api.?key|access.?token|refresh.?token|connection.?string)", re.I)
TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,})\b")
ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|connection[_-]?string)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)")
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
WIN_PATH = re.compile(r"(?i)[A-Z]:[\\/][^\r\n\"<>|]*")


def redact_text(value: str, public=False) -> str:
    result = TOKEN.sub("[REDACTED]", value)
    result = ASSIGNMENT.sub(lambda m: m.group(1) + "=[REDACTED]", result)
    result = BEARER.sub("Bearer [REDACTED]", result)
    if public:
        result = WIN_PATH.sub("<local-path>", result)
    return result


def redact(value, public=False):
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if SENSITIVE_KEY.search(str(k)) else redact(v, public=public) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, public=public) for item in value]
    if isinstance(value, str):
        return redact_text(value, public=public)
    return value
