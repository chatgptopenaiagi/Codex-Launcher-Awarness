"""Synthetic data only; never represents the current workstation."""
from .models import Capability, Snapshot


def demo_snapshot() -> Snapshot:
    return Snapshot(demo=True, limitations=["DEMO: synthetic fixture. Launch is disabled in demo mode."], capabilities=[
        Capability(id="cpu", tags=["hardware", "cpu"], readiness="verified", values={"model": "Demo CPU", "physical_cores": 8, "logical_cores": 16, "utilization_percent": 12.5}, units={"utilization_percent": "%"}),
        Capability(id="memory", tags=["hardware", "memory"], readiness="verified", values={"total_bytes": 34359738368, "available_bytes": 21474836480}, units={"total_bytes": "bytes", "available_bytes": "bytes"}),
        Capability(id="gpu", tags=["hardware", "gpu"], readiness="verified", probe_method="service_health", values={"name": "Demo GPU", "vram_total_mib": 8192, "vram_free_mib": 6144, "utilization_percent": 4}, units={"vram_total_mib": "MiB", "vram_free_mib": "MiB"}),
        Capability(id="storage", tags=["hardware", "storage"], readiness="verified", values={"free_bytes": 536870912000, "total_bytes": 1099511627776}, units={"free_bytes": "bytes", "total_bytes": "bytes"}),
        Capability(id="blender", tags=["engine", "blender", "3d"], installation="detected", configuration="unknown", readiness="detected", version="Demo version", limitations=["Executable detected; no MCP handshake performed."]),
        Capability(id="maxima", tags=["engine", "symbolic-math"], installation="detected", readiness="verified", transport="stdio CLI", probe_method="capability_check", values={"arithmetic": "4", "mcp_connectivity": "unknown"}),
        Capability(id="codex", tags=["toolchain", "coding"], installation="detected", readiness="unknown", limitations=["Demo only. Choose a real installation outside demo mode."]),
    ])
