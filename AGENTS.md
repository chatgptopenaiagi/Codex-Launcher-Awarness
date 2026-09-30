# CLA development instructions

Preserve the product spelling Codex Launcher Awarness. This is an experimental Windows application, not a new specialist bridge or universal shell MCP server.

- Keep Qt imports inside GUI entry points. Headless CLI/MCP imports must never load Qt, torch, tensorflow, CUDA runtimes, or model libraries.
- Separate installed, configured, reachable, version-checked and capability-verified evidence. Unknown values are not zero or healthy. Expired evidence stays stale until re-observed.
- Use only bounded passive discovery and fixed probes of explicitly trusted paths. Do not recursively scan unrelated directories or execute project descriptors.
- Store private settings, evidence, sessions, backups and logs under CLA Local AppData. Keep live inventory, user paths, tokens and conversations out of source, packages, screenshots and releases.
- Launch one independent PowerShell session using the owned JSON bootstrap. The default is unelevated and must refuse an elevated-only desktop unless the user explicitly selects the separate per-launch administrator-inheritance option. Never silently select that option. No user input may enter Invoke-Expression or an interpolated shell command. Conda activation affects the child only.
- Preserve Codex authentication, existing configuration, plugins, MCP entries and user guidance. Persistent integration requires its explicit Apply action; test edits only against isolated fixtures.
- Do not run model benchmarks, start duplicate servers, calibrate Qwen, kill unrelated processes, modify PATH/profiles/services, or upgrade the workstation.
- Use the dedicated environment. Run pytest, wheel installation tests, and frozen GUI/MCP smoke tests after relevant changes. Label real, mocked, skipped and not-run checks accurately.
- Release only sanitized source and verified assets to the authorized private repository. No PyPI or public release without authorization. Do not fabricate signing or attestations.
