# Installation

The private experimental portable release is the primary Windows x64 delivery. Verify `SHA256SUMS.txt`, extract the entire ZIP, and run `CLA-Launcher.exe`. Keep `_internal` and the accompanying files together. Use `cla.exe` for commands and `cla-mcp.exe` for MCP stdio. Python is included in the portable folder. Executables are unsigned; no signing or SmartScreen reputation is claimed.

CLA does not install Codex, PowerShell, Conda, specialist engines, models, CUDA, or drivers. Launching needs an existing supported Codex CLI and PowerShell 7. Missing optional engines are ordinary unknown/not-detected observations. An installer and startup service are not included.

Alternatively, install the wheel in a dedicated compatible Python environment:

```powershell
python -m venv .cla-env
& '.\.cla-env\Scripts\python.exe' -m pip install '.\codex_launcher_awarness-0.1.0-py3-none-any.whl[gui]'
& '.\.cla-env\Scripts\cla.exe' gui
```

Omit `[gui]` for headless usage. Only Windows x64/Python 3.14 has been exercised for this release; declared older Python compatibility is not a claim of live testing.

All private CLA settings and sessions use the Windows Local AppData known folder. The `CLA_DATA_DIR` environment variable supports explicit isolated testing/private alternate storage; it is not a Codex home replacement. The GUI's Desktop shortcut action is optional and does not create a startup entry.

To remove CLA, first use its managed integration removal if you previously applied persistent integration. Then remove the portable folder or uninstall the wheel from its dedicated environment. Private session history can be archived or deleted separately after you review it. Never restore a stale whole Codex config backup to undo one CLA entry.
