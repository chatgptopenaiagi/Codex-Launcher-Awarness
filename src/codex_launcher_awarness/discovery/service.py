"""Evidence-first, bounded Windows discovery. No engine is executed by inventory."""

from __future__ import annotations

import importlib.metadata
import itertools
import json
import os
import platform
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil

from codex_launcher_awarness.evidence.models import Capability, Snapshot
from codex_launcher_awarness.settings import Settings

from .parsers import nvidia_csv, wsl_list
from .process import run_probe
from .specialists import llama_health, maxima_check, run_wrapper, validate_endpoint

COMMANDS = {
    "powershell": ("pwsh.exe", "pwsh"), "codex": ("codex.exe", "codex.cmd", "codex.ps1", "codex"),
    "git": ("git.exe", "git"), "gh": ("gh.exe", "gh"),
    "python": ("python.exe", "python3.exe", "python3", "python"),
    "conda": ("conda.exe", "conda.bat", "conda.cmd", "conda"),
    "blender": ("blender.exe", "blender"), "maxima": ("maxima.bat", "maxima.exe", "maxima"),
    "nvidia_smi": ("nvidia-smi.exe", "nvidia-smi"), "wsl": ("wsl.exe",),
    "nvcc": ("nvcc.exe", "nvcc"), "llama_server": ("llama-server.exe", "llama-server"),
}
VERSION_ARGUMENTS = {
    "powershell": ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    "codex": ["--version"], "git": ["--version"], "gh": ["--version"],
    "python": ["-I", "--version"], "conda": ["--version"],
    "blender": ["--version"], "nvcc": ["--version"],
}


def resolve_candidates(name: str) -> list[dict]:
    """Enumerate direct PATH files only, preserving order and duplicate installations."""
    filenames = COMMANDS.get(name, ())
    results, seen = [], set()
    for raw in os.environ.get("PATH", "").split(os.pathsep)[:200]:
        directory = Path(raw.strip('"'))
        if not directory.is_absolute():
            continue
        for filename in filenames:
            candidate = directory / filename
            key = str(candidate).casefold()
            try:
                valid = candidate.is_file()
            except OSError:
                valid = False
            if key not in seen and valid:
                seen.add(key)
                results.append({"path": str(candidate), "resolution_source": "PATH"})
    # Desktop-bundled candidates: enumerate only direct Codex package directories,
    # then check fixed relative entrypoints; never recurse through WindowsApps.
    if name == "codex" and os.name == "nt":
        windowsapps = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WindowsApps"
        try:
            with os.scandir(windowsapps) as entries:
                packages = [Path(entry.path) for entry in entries
                            if "codex" in entry.name.lower() and entry.is_dir(follow_symlinks=False)][:20]
            for package in packages:
                for relative in ("app/resources/codex.exe", "app/codex.exe", "codex.exe"):
                    candidate = package / relative
                    if candidate.is_file() and str(candidate).casefold() not in seen:
                        seen.add(str(candidate).casefold())
                        results.append({"path": str(candidate), "resolution_source": "desktop_package_metadata"})
        except (OSError, PermissionError):
            pass
    return results[:64]


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _record(identifier: str, tags: list[str], *, ttl: int = 30, **kwargs) -> Capability:
    now = _utc()
    return Capability(id=identifier, tags=tags, observed_at=now.isoformat(),
                      expires_at=(now + timedelta(seconds=ttl)).isoformat(),
                      evidence_id=str(uuid.uuid4()), **kwargs)


def _within(path: Path, roots: list[str]) -> bool:
    try:
        resolved = path.resolve(strict=True)
        return any(resolved == (root := Path(value).resolve(strict=True)) or root in resolved.parents for value in roots)
    except (OSError, ValueError):
        return False


def _cpu_model() -> str | None:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()[:180]
        except OSError:
            return None
    return platform.processor() or None


class _ScanCancellation:
    def __init__(self, event, deadline: float):
        self.event, self.deadline = event, deadline

    def is_set(self) -> bool:
        return bool(self.event and self.event.is_set()) or time.monotonic() >= self.deadline

    def remaining(self) -> float:
        return max(0.05, self.deadline - time.monotonic())


class DiscoveryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[tuple, tuple[float, Snapshot]] = {}
        self._lock = threading.Lock()

    def scan(self, project: Path | None = None, allow_probes: bool = False,
             cancel: threading.Event | None = None, force: bool = False) -> Snapshot:
        project = Path(project) if project else None
        if project and not _within(project, self.settings.approved_project_roots):
            raise ValueError("Project is outside explicitly approved project roots")
        key = (str(project) if project else None, allow_probes)
        with self._lock:
            existing = self._cache.get(key)
            if existing and not force and time.monotonic() - existing[0] < self.settings.cache_seconds:
                return existing[1].model_copy(deep=True)
        records: list[Capability] = []
        cancel = _ScanCancellation(cancel, time.monotonic() + 15)
        limitations = ["Read-only observations are not a sandbox or resource reservation.",
                       "Configured integration entries are not live MCP handshake evidence."]
        if not allow_probes:
            limitations.append("Executable and service probes were not approved for this scan.")
        stages = [lambda: self._hardware(project), self._toolchain, self._python_environments,
                  lambda: self._project(project), lambda: self._mcp_inventory(project)]
        if allow_probes:
            stages.extend([lambda: self._gpu(cancel), lambda: self._specialists(cancel),
                           lambda: self._versions(cancel), lambda: self._services(cancel),
                           lambda: self._wsl(cancel)])
        else:
            stages.extend([self._unprobed_gpu, self._unprobed_services, self._unprobed_wsl])
        for stage in stages:
            if cancel is not None and cancel.is_set():
                limitations.append("Collection cancelled or aggregate 15 second deadline reached; snapshot is partial.")
                break
            try:
                records.extend(stage())
            except (OSError, ValueError, psutil.Error) as exc:
                records.append(_record("provider.error." + str(len(records)), ["diagnostics"],
                                       error={"code": "provider_failed", "kind": type(exc).__name__},
                                       limitations=["One provider failed; other observations remain available."]))
        # Later active evidence replaces the same passive tool identity.
        merged = {record.id: record for record in records}
        snapshot = Snapshot(schema_version=1, session_id=str(uuid.uuid4()), created_at=_utc().isoformat(),
                            capabilities=list(merged.values()), limitations=limitations, demo=False)
        snapshot = Snapshot.model_validate(snapshot.sanitized())
        if cancel is None or not cancel.is_set():
            with self._lock:
                self._cache[key] = (time.monotonic(), snapshot)
        return snapshot.model_copy(deep=True)

    def _trusted(self, name: str) -> Path | None:
        value = self.settings.trusted_executables.get(name)
        if value:
            path = Path(value)
            if path.is_absolute() and path.is_file():
                return path
        return None

    def _kwargs(self, cancel) -> dict:
        timeout = min(self.settings.probe_timeout_seconds, cancel.remaining()) if isinstance(cancel, _ScanCancellation) else self.settings.probe_timeout_seconds
        return {"timeout": timeout,
                "max_bytes": self.settings.max_output_bytes, "cancel": cancel}

    def _hardware(self, project: Path | None) -> list[Capability]:
        started = time.monotonic()
        cpu = _record("hardware.cpu", ["hardware", "cpu"], installation="detected", readiness="verified",
                      values={"model": _cpu_model(), "physical_count": psutil.cpu_count(logical=False),
                              "logical_count": psutil.cpu_count(logical=True),
                              "utilization_percent": psutil.cpu_percent(interval=0.08)},
                      units={"utilization_percent": "%"}, probe_method="passive_metadata",
                      duration_ms=round((time.monotonic() - started) * 1000, 2),
                      limitations=["CPU utilization is a bounded 80 ms sample, not a sustained workload measurement."])
        mem = psutil.virtual_memory()
        records = [cpu, _record("hardware.memory", ["hardware", "memory"], installation="detected", readiness="verified",
                               values={"total_bytes": mem.total, "available_bytes": mem.available,
                                       "used_bytes": mem.total - mem.available, "utilization_percent": mem.percent},
                               units={"total_bytes": "bytes", "available_bytes": "bytes", "used_bytes": "bytes",
                                      "utilization_percent": "%"})]
        volumes = ([str(project)] if project else []) + self.settings.engine_volumes
        seen = set()
        for index, value in enumerate(volumes[:16]):
            path = Path(value)
            if not path.is_absolute():
                continue
            volume = path.anchor
            if volume.casefold() in seen:
                continue
            seen.add(volume.casefold())
            try:
                usage = shutil.disk_usage(path)
                records.append(_record("hardware.storage." + str(index), ["hardware", "storage"],
                                       installation="detected", readiness="verified", path=volume,
                                       values={"total_bytes": usage.total, "free_bytes": usage.free, "used_bytes": usage.used},
                                       units={"total_bytes": "bytes", "free_bytes": "bytes", "used_bytes": "bytes"}))
            except OSError as exc:
                records.append(_record("hardware.storage." + str(index), ["hardware", "storage"], path=volume,
                                       readiness="unavailable", error={"code": "storage_unavailable", "kind": type(exc).__name__}))
        return records

    def _toolchain(self) -> list[Capability]:
        records = []
        for name in COMMANDS:
            candidates = resolve_candidates(name)
            trusted = self._trusted(name)
            hint = self.settings.engine_paths.get(name)
            if hint and Path(hint).is_file() and not any(Path(item["path"]) == Path(hint) for item in candidates):
                candidates.append({"path": hint, "resolution_source": "configured_hint"})
            if trusted:
                candidates = [{"path": str(trusted), "resolution_source": "explicit_trust"}] + [
                    entry for entry in candidates if Path(entry["path"]) != trusted]
            configured = self.settings.trusted_executables.get(name) or self.settings.engine_paths.get(name)
            tags = ["engines" if name in {"blender", "maxima", "llama_server"} else "toolchain", name]
            if name in {"blender", "maxima", "llama_server"}:
                tags.append("engine")
            if name == "nvcc":
                tags.append("cuda")
            limitations = ["Presence does not verify executable operation or MCP connectivity."]
            if name == "nvcc":
                limitations.append("A toolkit executable is separate from driver CUDA support and framework execution.")
            if name == "blender":
                limitations.append("Version verification does not establish scene rendering or bpy capability.")
            records.append(_record("tool." + name, tags, installation="detected" if candidates else "not_detected",
                                   resolution_source=candidates[0]["resolution_source"] if candidates else None,
                                   path=candidates[0]["path"] if candidates else (configured or None),
                                   configuration="configured" if configured else "unknown", readiness="unknown",
                                   transport="cli", values={"candidates": candidates, "trusted_for_probes": bool(trusted)},
                                   limitations=limitations,
                                   error={"code": "configured_executable_missing"} if configured and not Path(configured).is_file() else None))
        return records

    def _versions(self, cancel) -> list[Capability]:
        passive = {record.id: record for record in self._toolchain()}
        records = []
        for name, arguments in VERSION_ARGUMENTS.items():
            if cancel is not None and cancel.is_set():
                break
            executable = self._trusted(name)
            if executable is None:
                continue
            result = run_wrapper(executable, arguments, self._trusted("powershell"), **self._kwargs(cancel))
            text = result.stdout + "\n" + result.stderr
            match = re.search(r"(?<!\d)(\d{1,4}\.\d{1,4}(?:\.\d{1,4})?(?:[-+][A-Za-z0-9.]+)?)", text)
            record = passive["tool." + name]
            record.probe_method = "executable_version_probe"
            record.duration_ms = result.duration_ms
            record.version = match[1] if match else None
            record.reachability = "reachable" if result.returncode == 0 else "unavailable"
            # --version establishes that fixed probe, not rendering/inference or a usable integration.
            record.readiness = "unknown" if not result.error and match else "degraded"
            record.values["version_probe"] = "verified" if not result.error and match else "failed"
            if name in {"blender", "nvcc", "python"}:
                record.values["capability_check"] = "not_run"
            record.error = {"code": result.error or "malformed_version"} if result.error or not match else None
            records.append(record)
        return records

    def _unprobed_gpu(self) -> list[Capability]:
        executable = self._trusted("nvidia_smi")
        return [_record("hardware.gpu", ["hardware", "gpu"], installation="unknown", readiness="unknown",
                        values={"devices": [], "metrics_available": False},
                        limitations=["GPU metrics require an explicitly trusted nvidia-smi executable and approved probe.",
                                     "Non-NVIDIA GPU metrics are not implemented."],
                        error={"code": "probe_not_approved" if executable else "trusted_nvidia_smi_missing"})]

    def _gpu(self, cancel) -> list[Capability]:
        executable = self._trusted("nvidia_smi")
        if executable is None:
            return self._unprobed_gpu()
        result = run_probe(executable, ["--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,index,uuid",
                                        "--format=csv,noheader,nounits"], **self._kwargs(cancel))
        error = result.error
        devices = []
        if not error:
            try:
                devices = nvidia_csv(result.stdout)
                if not devices:
                    error = "no_gpu_metrics"
            except ValueError:
                error = "malformed_gpu_response"
        warnings = []
        cuda_support = None
        if not error and not (cancel and cancel.is_set()):
            driver_probe = run_probe(executable, ["--version"], **self._kwargs(cancel))
            match = re.search(r"CUDA\s+Version\s*:\s*(\d+\.\d+)", driver_probe.stdout, re.IGNORECASE)
            if not driver_probe.error and match:
                cuda_support = match[1]
        for device in devices:
            free, total = device["memory_free_mib"], device["memory_total_mib"]
            if free is not None and total and free / total < 0.15:
                warnings.append("Low observed aggregate GPU memory headroom; no process attribution or stop recommendation.")
        return [_record("hardware.gpu", ["hardware", "gpu"], installation="detected" if devices else "unknown",
                        readiness="verified" if devices else "unavailable", path=str(executable),
                        resolution_source="explicit_trust", probe_method="actual_capability_check", duration_ms=result.duration_ms,
                        values={"devices": devices, "metrics_available": bool(devices), "warnings": warnings,
                                "driver_cuda_support": cuda_support, "pytorch_execution": "not_run"},
                        units={"memory_total_mib": "MiB", "memory_used_mib": "MiB", "memory_free_mib": "MiB",
                               "utilization_percent": "%", "temperature_celsius": "degrees Celsius"},
                        limitations=["Aggregate GPU metrics do not attribute usage to Qwen or any other process.",
                                     "Unsupported WDDM/per-process measurements remain unavailable.",
                                     "Driver CUDA support, installed CUDA toolkit and working PyTorch are separate findings."],
                        error={"code": error} if error else None)]

    def _specialists(self, cancel) -> list[Capability]:
        executable = self._trusted("maxima")
        if executable is None:
            return []
        result = maxima_check(executable, self._trusted("powershell"), **self._kwargs(cancel))
        return [_record("tool.maxima", ["engines", "engine", "maxima", "symbolic-math"], installation="detected",
                        path=str(executable), resolution_source="explicit_trust", configuration="configured",
                        reachability="reachable" if result["version_probe"] == "verified" else "unknown",
                        readiness="verified" if result["math_check"] == "verified" else "degraded",
                        version=result["version"], transport="cli", probe_method="actual_capability_check",
                        duration_ms=result["duration_ms"], values=result,
                        limitations=["Four fixed arithmetic/symbolic checks verify this CLI access route only.",
                                     "No MCP connection has been established; project bridges remain separate evidence."],
                        error={"code": result["error"]} if result.get("error") else None)]

    def _python_environments(self) -> list[Capability]:
        records = []
        allowed_packages = {"torch", "numpy", "sympy", "scipy", "transformers", "nvidia-cudnn-cu12",
                            "nvidia-cublas-cu12", "pyside6", "mcp"}
        for index, value in enumerate(self.settings.python_environments[:32]):
            root = Path(value)
            if not root.is_absolute():
                continue
            sites = [root / "Lib" / "site-packages"]
            packages = {}
            try:
                for site in sites:
                    if not site.is_dir():
                        continue
                    # Metadata API reads dist-info; it does not import packages or load GPU libraries.
                    for distribution in itertools.islice(importlib.metadata.distributions(path=[str(site)]), 2048):
                        name = (distribution.metadata.get("Name") or "").lower().replace("_", "-")
                        if name in allowed_packages:
                            packages[name] = distribution.version[:80]
            except (OSError, ValueError):
                packages = {}
            executable = next((path for path in (root / "python.exe", root / "Scripts" / "python.exe") if path.is_file()), None)
            records.append(_record("python.environment." + str(index), ["python", "environments"], path=str(root),
                                   installation="detected" if executable else "not_detected", configuration="configured",
                                   values={"executable": str(executable) if executable else None, "packages": packages,
                                           "gpu_execution": "not_run"},
                                   limitations=["Package metadata presence does not verify imports, CUDA/cuDNN linkage or computation."]))
        return records

    def _project(self, project: Path | None) -> list[Capability]:
        if project is None:
            return []
        known = ("pyproject.toml", "package.json", "AGENTS.md", "AGENTS.override.md", "cla-engines.yaml",
                 "bridge/blender_mcp.py", "bridge/math_mcp.py", "bridge/maxima_mcp.py", "config/blender.yaml")
        found = [name for name in known if (project / name).is_file()]
        return [_record("project.capabilities", ["project", "integrations"], path=str(project), installation="detected",
                        configuration="configured", values={"entrypoints_present": found,
                                                            "guidance_override_present": "AGENTS.override.md" in found},
                        limitations=["Only fixed manifest/entry-point existence was checked; no project code was executed.",
                                     "Manifest or adapter presence does not establish registration, readiness or handshake."])]

    def _unprobed_services(self) -> list[Capability]:
        records = []
        for index, endpoint in enumerate(self.settings.local_endpoints[:8]):
            try:
                validate_endpoint(endpoint)
                error = "probe_not_approved"
            except ValueError:
                error = "invalid_local_endpoint"
            records.append(_record("service.llama." + str(index), ["services", "service", "llama", "qwen", "gpu"],
                                   configuration="configured", transport="http-loopback", values={"endpoint_index": index},
                                   error={"code": error}, limitations=["No tokens generated; model readiness is unverified."]))
        return records

    def _mcp_inventory(self, project: Path | None) -> list[Capability]:
        from codex_launcher_awarness.integration.config import config_inventory
        inventory = config_inventory(project)
        return [_record("integration.mcp", ["mcp", "integrations"], configuration="configured"
                        if any(layer.get("mcp_servers") for layer in inventory["layers"]) else "unknown",
                        values=inventory, limitations=inventory["limitations"])]

    def _services(self, cancel) -> list[Capability]:
        records = []
        for index, endpoint in enumerate(self.settings.local_endpoints[:8]):
            if cancel is not None and cancel.is_set():
                break
            try:
                result = llama_health(endpoint, **self._kwargs(cancel))
            except ValueError:
                result = {"error": "invalid_local_endpoint", "responses": {}}
            responses = result["responses"]
            compatible = responses.get("health") == "ok" and responses.get("model_metadata_available") is True
            records.append(_record("service.llama." + str(index), ["services", "service", "llama", "qwen", "gpu"],
                                   configuration="configured", reachability="reachable" if responses else "unavailable",
                                   readiness="verified" if compatible else "unknown", transport="http-loopback",
                                   probe_method="service_health_request", duration_ms=result.get("duration_ms", 0),
                                   values={"endpoint_index": index, **responses},
                                   error={"code": result["error"]} if result["error"] else None,
                                   limitations=["Compatible health/model metadata does not prove Qwen identity or generation capability.",
                                                "No inference, benchmarks, downloads or service startup occurred."]))
        return records

    def _unprobed_wsl(self) -> list[Capability]:
        return [_record("wsl.distributions", ["wsl"], backend="wsl", readiness="unknown",
                        values={"distributions": []}, error={"code": "metadata_probe_not_approved"},
                        limitations=["No WSL distribution was started. Launching WSL is not implemented."])]

    def _wsl(self, cancel) -> list[Capability]:
        executable = self._trusted("wsl")
        if executable is None:
            return self._unprobed_wsl()
        result = run_probe(executable, ["--list", "--verbose"], **self._kwargs(cancel))
        return [_record("wsl.distributions", ["wsl"], backend="wsl", path=str(executable),
                        installation="detected", readiness="unknown", probe_method="passive_metadata",
                        duration_ms=result.duration_ms, values={"distributions": wsl_list(result.stdout)},
                        error={"code": result.error} if result.error else None,
                        limitations=["Distribution metadata only; no stopped distribution was launched.",
                                     "CLI text may be localized; an empty parsed list is not proof of absence."])]
