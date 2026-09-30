# Architecture

CLA 0.1.0 is an experimental Windows application with one headless core and three entry points: desktop GUI, CLI, and stdio MCP. Importing the package or starting MCP does not initialize Qt or load GPU frameworks.

```text
Project + task + explicit executable choices
                   |
   DiscoveryService -> timestamped Capability records
                   |
       immutable session Snapshot + briefing preview
                   |
       approved private JSON launch manifest
                   |
 fixed PowerShell bootstrap -> independent interactive Codex
                   |
       session-scoped cla_awareness MCP queries
```

## Responsibilities

| Component | Responsibility |
| --- | --- |
| `discovery` | Bounded passive inventory and separately approved fixed probes. |
| `evidence` | Versioned records, provenance, freshness, units and redaction. |
| `briefing` | Relevance filtering and bounded human-readable context. |
| `launch` | Validated arguments, immutable artifacts, duplicate prevention and Windows process creation. |
| `integration` | Allowlisted Codex inventory, per-invocation overrides and optional managed TOML edits. |
| `mcp` | Official Python SDK protocol handling and read-only structured awareness tools. |
| `gui` | Preview, trust choices, refresh/cancel, integration and history. |

Codex configuration remains connection/runtime configuration. `AGENTS.md` holds stable development guidance. Snapshots hold changing observations. Codex decides how to reason and orchestrate; existing specialist engines perform computation. CLA does not create missing specialist bridges.

## Evidence, storage and freshness

Schema version 1 capability records separate installation, configuration, reachability and readiness. Records include UTC observation/expiry times, a unique evidence ID, probe method/duration, values with units, limitations, and structured failure or unknown information. These states are independent: an operational Maxima CLI does not imply an MCP connection.

CPU/RAM observations use OS-backed psutil metadata and an 80 ms CPU sample. GPU observations use an explicitly trusted `nvidia-smi`, aggregate VRAM and supported fields. Missing measurements remain null. Toolkit discovery, driver support, Python package metadata and actual framework execution are distinct. Selected environment metadata is read without importing the packages. Project checks inspect a fixed list of entry points, not their contents or promises.

Each scan has a 15-second aggregate deadline, bounded individual probe time/output, cancellation, and an in-memory cache. A cached observation keeps its original timestamps. The discovery service can return a partial snapshot with a cancellation limitation; the GUI discards a cancelled scan's result and retains its previous completed snapshot. Loopback service checks request health/model metadata and never generate tokens.

Runtime data lives in per-user Local AppData `CLA`: private settings, session snapshots, launch manifests, status, diagnostics and integration backups. Session IDs isolate concurrent launches. `CLA_DATA_DIR` supports explicit test isolation; it is not a substitute Codex home. Neither credentials nor full Codex conversations are copied.

## Launch and context delivery

The approved briefing becomes the actual initial Codex prompt. The immutable snapshot path is supplementary; its presence is not proof that Codex read it. CLA exposes the same approved evidence through its MCP server when the chosen Codex sandbox cannot access Local AppData. It never silently grants additional filesystem access.

Arguments are data in a private JSON manifest, read by a shipped PowerShell script. The script uses `Set-Location -LiteralPath` and argument arrays, never `Invoke-Expression` on user input. A conservative Windows command-line budget prevents oversized prompts. Named Conda activation runs only in the new child session through the explicitly trusted installation's hook.

One prepared session can be claimed once, including across separate launch-manager instances. The independent terminal outlives the GUI. Status records distinguish terminal creation, Codex start/exit and launch failure; terminal creation alone is not a successful model response.

## Integration and packaging

CLA-launched sessions add only invocation-level `cla_awareness` overrides. Optional persistent integration is explicit, syntax-preserving and atomic; hashes detect concurrent edits. Managed removal compares the current CLA table with the recorded addition, retaining unrelated or subsequently changed user settings.

The wheel uses a PEP 517 backend and ships package resources. The Windows portable bundle uses PyInstaller one-folder packaging with separate windowed GUI and console CLI/MCP executables. Codex, PowerShell, engines, model weights and personal settings remain external.
