# Security and privacy

CLA 0.1.0 is an experimental private prerelease. Its awareness tools are read-only in intent; they are **not an operating-system sandbox**. A trusted executable or Conda activation hook still executes local code with the child user's permissions. Trust only installations you intend to run.

## Collection boundaries

- Default discovery reads bounded metadata. Paths found on PATH or supplied as engine hints are not permission to execute them.
- Explicitly trusted executables use fixed argument templates, deadlines, output limits and hidden probe consoles. Probe cleanup targets only CLA-created processes and their owned Windows Job Objects.
- Approved project roots receive fixed manifest/entry-point existence checks. CLA does not recursively inspect repositories, load project Python plugins or obey discovered text as instructions.
- Selected Python package metadata is read without importing GPU frameworks. Unsupported metrics stay unavailable. Aggregate GPU usage is never attributed wholesale to Qwen or another process.
- Configured loopback HTTP health/model endpoints reject credentials, external hosts, redirects and oversized responses. No token generation, model start, model download, benchmark or Qwen calibration occurs during discovery.
- MCP inventory reads allowlisted Codex configuration fields. It does not connect other MCP servers, collect authentication files, copy credentials or dump environment variables.
- CLA does not change system PATH, profiles, execution policy, startup behavior, services, drivers or engine installations.

## Context and privacy

There is no telemetry or automatic upload. Dependency/documentation retrieval, authorized GitHub delivery and explicitly launched Codex sessions are separate network activities.

Review the exact briefing preview before Start Codex. Approved local observations sent to a cloud-backed Codex session are no longer confined to the PC. Local-only preview/export is available. Do not include passwords, tokens, private keys or connection strings in tasks. Redaction runs before returned snapshots, saved diagnostics, briefing and export, but cannot identify every possible secret or sensitive fact. Public-style exports additionally replace local paths. Treat every export as reviewable content, not an automatic guarantee of anonymity.

Private settings, evidence, session manifests, integration backups and status live under per-user Local AppData `CLA`, using that user's normal filesystem protections. These are local private files, not encrypted vaults. Session artifacts are immutable by CLA convention, not protected against the same user or an administrator modifying them. CLA does not record full Codex conversations. Review retained session data and backups before sharing or removing them; automatic retention is not implemented.

## Launch and permissions

Project, task and option values remain argument data in a private manifest and fixed bootstrap. No user input reaches `Invoke-Expression`. Unsupported batch wrapper cases fail closed. The selected Codex installation, child Conda environment, permission choice and context are shown in preview. Conda activation affects only the new terminal.

CLA preserves inherited Codex settings by default. Selecting full access with no approval deliberately disables Codex's sandbox and command-approval barriers; CLA does not describe that selection as safe. It does not silently widen sandbox access to the snapshot path. The prompt and CLA MCP provide an approved alternative when the snapshot file is outside allowed filesystem scope.

Default terminals run unelevated, with same-user token checks and a bootstrap guard. An elevated-only desktop blocks that default route. A separate, unchecked per-launch option or `--allow-elevated` explicitly permits the current administrator token; it is not silently selected and does not change Windows security settings. Administrator-token inheritance and Codex's sandbox/approval options are different controls, both visible in preview. Closing CLA does not terminate an independently launched Codex terminal. CLA never kills unrelated applications to relieve resource contention.

## MCP boundary

Only protocol messages go to stdout. The standard SDK supplies initialization, tool discovery/calls and shutdown. Tools accept bounded freshness controls, known engine identifiers and approved session identifiers. They expose no shell execution, arbitrary URL/path/file read, installation, credential access, process-kill or system-modification capability.

MCP clients can retrieve CLA's approved observations. Treat that access as access to local machine context. A configured server is not a verified handshake. An observation is not an instruction, a resource reservation or a guarantee of future readiness.

## Managed configuration

Session integration uses invocation overrides and leaves persistent Codex configuration unchanged. Persistent Preview/Apply and Remove are separate explicit actions. CLA adds only its managed table, preserves TOML structure, uses atomic writes and private backups, and detects concurrent changes. Removal refuses to erase a table that differs from the managed addition. It never restores a historical entire configuration over newer edits. External agent guidance is offered, not silently installed.

## Reporting a problem

Use the private repository's issue channel with a sanitized reproduction. Do not publish private snapshots, configuration backups, authentication files or raw conversation logs. Include the release version, build-manifest hash, expected behavior and sanitized diagnostic export. This experimental project has no published security support SLA, signing guarantee or completed independent security audit.
