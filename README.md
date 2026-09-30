# Codex Launcher Awarness (CLA)

Experimental Windows desktop launcher and evidence-backed workstation briefing for Codex. Version 0.1.0 is a private prerelease, not a production-ready release. The spelling **Awarness** is intentional.

CLA observes configured capabilities, distinguishes installation from operational verification, previews what Codex will receive, and opens one independent PowerShell session in your selected project. Its read-only `cla_awareness` MCP server provides fresh observations. It does not replace Codex, optimize the workstation, benchmark models, or implement new Blender or Maxima bridges.

## Run

Extract the complete portable ZIP to a user-writable folder and open `CLA-Launcher.exe`. Keep its `_internal` directory beside the executables. The portable distribution includes Python and Qt; it does not include Codex, PowerShell, Conda, specialist engines, or model weights. Windows x64, an existing Codex installation, and PowerShell 7 are required for launching Codex. Missing Codex does not prevent viewing inventory or Demo mode.

For the wheel, use a dedicated Python 3.11–3.14 environment (this release is tested on Windows x64 / Python 3.14):

```powershell
python -m pip install 'codex_launcher_awarness-0.1.0-py3-none-any.whl[gui]'
cla gui
cla scan --json
cla brief --project 'C:\Projects\Example'
cla launch --project 'C:\Projects\Example' --dry-run
cla doctor
cla mcp
```

The headless wheel does not require Qt. Install the `gui` extra for the desktop interface. Run `cla --help` for trust, project, probe and integration options. `cla-mcp.exe` is a console/stdio executable; do not double-click it expecting a graphical window.

## First run and privacy

Use Launch to select and approve a project. In Engines, review discovered executable candidates and explicitly trust the intended Codex and PowerShell paths. Optional Conda activation occurs only in the new child session. Refresh passive inventory first; approve fixed executable probes separately. Write the task, choose a relevance filter, preview the exact context, and acknowledge that approved context sent to cloud-backed Codex leaves the PC. Press Start Codex once. Closing CLA leaves that terminal running.

The approved briefing is an actual initial Codex prompt. It contains bounded facts and instructions to query `cla_awareness`, with a reference to an immutable private snapshot. A file path alone does not mean Codex has read that file. Session-scoped MCP overrides expose approved observations without changing global Codex configuration or broadening sandbox access. Detailed snapshots and launch records live under Windows Local AppData `CLA`, not inside projects.

There is no telemetry. Logs/exports/briefings are redacted, but redaction is defense in depth: review the exact preview before sharing. Do not paste credentials into tasks. Screenshots and examples use clearly labelled synthetic data.

## Evidence and tools

Every observation has an identifier, method, UTC timestamps, expiry, units, limitations and error/unknown detail. A discovered file is not an execution check, a version response is not a mathematical check, a configured MCP entry is not a handshake, and driver CUDA support is not an installed toolkit or verified PyTorch environment. No heavy GPU imports, benchmarks, model starts, or Qwen calibration happen during routine discovery.

MCP tools: `pc_summary`, `pc_cpu_status`, `pc_gpu_status`, `pc_memory_status`, `pc_storage_status`, `pc_installed_engines`, `pc_service_status`, `pc_mcp_status`, `pc_python_environments`, `pc_wsl_status`, and `pc_project_capabilities`. They accept bounded freshness controls and approved identifiers, never arbitrary commands, paths or URLs.

## Integration and undo

CLA-launched sessions use per-invocation configuration. Optional persistent integration is a separate Preview Changes → Apply action, or an explicit `cla integrate --apply` command with a scope. It adds only the CLA-owned table, preserves other settings, checks concurrent changes, and records a private backup and hashes. `cla integrate --remove` removes only unchanged CLA-managed additions; it never restores an old entire file over newer user edits. External `AGENTS.md` guidance is offered, not installed silently.

## Limits and documentation

Windows is the tested release target. WSL launching, embedded terminals, deeper engine control, model benchmarking, and automatic specialist MCP registration are not implemented. Unknown/unsupported metrics remain unknown. Read-only tools are not an operating-system sandbox. Live evidence expires and does not reserve resources. An elevated launcher needs an existing unelevated desktop token to open the default unelevated session safely. On an elevated-only desktop the default refuses; an explicitly selected per-launch option (CLI `--allow-elevated`) can use the current elevated token. This is separate from Codex's sandbox choice and never happens silently.

See [architecture](docs/architecture.md), [security/privacy](SECURITY.md), [installation](docs/installation.md), [user guide](docs/user-guide.md), [verification and blocked acceptance](docs/verification.md), [troubleshooting](docs/troubleshooting.md), [developer instructions](docs/development.md), [compatibility decisions](docs/compatibility.md), [release notes](CHANGELOG.md), and [roadmap](docs/roadmap.md). Licensing for CLA itself is [pending](LICENSE-PENDING.md); dependencies retain their own licenses and notices.
