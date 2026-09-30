# Troubleshooting

Start with `cla doctor` and the Dashboard's selected evidence details. The Integration tab previews managed configuration changes. Diagnose with the intended executable paths and evidence timestamps; do not reinstall or upgrade the workstation to resolve a missing observation.

| Symptom | Check and recovery |
| --- | --- |
| GUI opens but Codex cannot launch | Select and approve an existing Codex installation and PowerShell 7 executable in Engines, then choose and approve the project in Launch. Missing Codex does not block inventory or Demo mode. |
| Several Codex candidates appear | Review their exact paths. Choose the intended installation; CLA does not automatically change installations. |
| Codex `.cmd` rejected | Select its same-directory `.ps1` companion or that installation's native executable. Batch-only shims are intentionally unsupported for interactive launch. |
| Terminal reports elevation failure | Use an existing unelevated Windows desktop session. If the entire desktop is elevated, default launch refuses. The separate per-launch administrator-inheritance option is available only for explicit use; it is off by default and does not change Windows security policy. |
| Probe says unknown | Passive discovery does not execute programs. Explicitly trust the intended executable and approve fixed probes. Unknown does not mean broken. |
| GPU metrics unavailable | NVIDIA metrics need trusted `nvidia-smi` and approved probing. Non-NVIDIA telemetry and unsupported WDDM fields are unavailable. Do not infer zero usage. |
| Version verified, readiness unknown | Version probing succeeded; the relevant capability has not been exercised. For example, a Blender version response does not verify rendering. |
| Maxima check fails | Inspect the structured version and functional evidence separately. CLA disables user initialization. A nonstandard version identifier is accepted, but wrong mathematical results, timeouts and wrapper limitations remain failures. |
| Local service unknown/unavailable | Confirm the configured loopback endpoint belongs to the intended existing service. CLA does not start a second server or generate tokens as a health test. |
| Conda environment fails | Select the trusted installation's `Scripts\conda.exe`, confirm its PowerShell hook exists and choose `base` or an existing simple environment name. Activation happens only in the child terminal. |
| CLA snapshot file inaccessible to Codex | Query `cla_awareness.pc_summary` using the approved session ID. Do not broaden sandbox access merely to read the supplementary file. |
| MCP entry appears configured but tools unavailable | Configuration inventory is not a handshake. Use CLA session integration/diagnostics; do not register an engine executable as if it were an MCP server. |
| Persistent Apply refuses malformed TOML | Repair the user configuration separately. CLA refuses to guess or replace it. Preview again after repair. |
| Apply says concurrent edit | Another writer changed the configuration after preview. Review the latest file and make a new preview. |
| Managed Remove refuses | The CLA table was changed after integration. Review those changes; automatic rollback will not overwrite them. Other configuration remains intact. |
| Two clicks seem ignored | One prepared session can launch once. Inspect History; create and preview a new session only when another terminal is intended. |
| Portable executable missing DLLs/resources | Extract the entire ZIP and keep all executables and `_internal` together. The GUI executable alone is not portable. |

Use `cla launch --project 'C:\Projects\Example' --dry-run` for a local launch/context preview. It does not open a terminal. `cla gui --demo` uses labelled synthetic evidence and does not present it as live workstation data.

After starting, History distinguishes a created terminal from Codex starting, exiting or failing. Codex's own authentication, quota, network and model errors remain Codex errors; CLA does not create API keys or retry paid sessions automatically.

For reports, export redacted diagnostics and review the file yourself. Never attach authentication files, full environment dumps, raw transcripts or complete Codex configuration. Include the exact release/build manifest and describe whether the problem occurred in the wheel or portable executable.
