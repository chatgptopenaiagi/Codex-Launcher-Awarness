# Development and release operations

Read repository `AGENTS.md` and [security boundaries](../SECURITY.md) before changing providers or launch behavior. Use a dedicated environment; do not modify Conda base, installed Codex, engines, drivers or global configuration as a development shortcut.

From a clean Windows x64 checkout with the intended Python interpreter:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -e '.[gui,dev]'
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m codex_launcher_awarness gui --demo
```

The release baseline uses Python 3.14.7. `requirements-lock.txt` records the build environment; `pyproject.toml` declares supported ranges and package resources. Editable installation is convenient for development but never substitutes for a clean non-editable wheel acceptance test.

## Test boundaries

Use synthetic evidence, temporary CLA/Codex homes, fake Codex executables and explicit test-owned processes. Do not read real authentication files, publish live inventory or include personalized paths in fixtures. Never claim a mock transcript is a live model response.

Provider tests cover missing tools, permissions, malformed output, unsupported metrics, deadline/cancellation, units and provenance. Launch tests exercise argument preservation, hostile punctuation, duplicate prevention, child-only Conda activation and lifecycle. Integration tests cover syntax preservation, malformed TOML, concurrent edits, idempotence and managed removal. MCP tests use a real SDK client for initialization, tools, validation, structured errors and clean EOF/stdout. GUI tests use synthetic fixtures.

Record PASS, FAIL, SKIPPED and NOT_RUN precisely. Missing CI hardware is not a successful live engine test. Routine test runs must not spend model quota. A separately authorized live Codex acceptance is bounded and its private evidence must demonstrate an actual briefing receipt and awareness query, rather than terminal creation alone.

The fake launch acceptance uses a real PowerShell child with a fixed fake Codex script. It verifies argument transfer, project selection, bootstrap lifecycle and token expectations; it is not a live Codex or model test. Its optional elevated-token test is distinct from the default unelevated route, which remains blocked on an elevated-only desktop. Frozen GUI smoke tests use synthetic Demo data, and offscreen widget tests use injected fake discovery/launch services.

## Build and smoke test

Use the repository scripts with the dedicated environment:

```powershell
& '.\.venv\Scripts\python.exe' scripts/build.py
& '.\.venv\Scripts\python.exe' scripts/smoke_wheel.py --wheel 'dist\release\codex_launcher_awarness-0.1.0-py3-none-any.whl' --output 'dist\release\wheel-smoke-summary.json'
& '.\.venv\Scripts\python.exe' scripts/smoke_artifacts.py --bundle 'dist\portable\CLA-0.1.0-windows-x64' --output 'dist\release\frozen-smoke-summary.json'
```

The wheel check creates a fresh environment outside the repository, installs the wheel non-editably, and exercises headless imports, package resources, console entry points and the actual MCP protocol. It starts no model session. The frozen smoke check likewise starts no model session.

For the portable child-process path, run the fixed fake-Codex acceptance with the exact reviewed PowerShell 7 installation; replace the example executable path if needed:

```powershell
& '.\.venv\Scripts\python.exe' scripts/acceptance_frozen_launch.py --cla 'dist\portable\CLA-0.1.0-windows-x64\cla.exe' --powershell 'C:\Program Files\PowerShell\7\pwsh.exe'
```

This default check uses a hidden real PowerShell child and a fixed fake Codex script. It does not run an installed Codex executable or prove a visible interactive terminal. On an elevated-only desktop, its default unelevated route remains blocked; append `--allow-elevated` only when explicitly approving administrator inheritance for this fake acceptance test. That result remains separate from live Codex/model acceptance.

To exercise a real new console with the same fixed fake script:

```powershell
& '.\.venv\Scripts\python.exe' scripts/acceptance_frozen_launch.py --cla 'dist\portable\CLA-0.1.0-windows-x64\cla.exe' --powershell 'C:\Program Files\PowerShell\7\pwsh.exe' --interactive-console
```

This creates exactly one visible synthetic terminal that closes automatically after approximately four seconds. It verifies console stdin/stdout/stderr handles, output writes, exact arguments/project selection, duplicate prevention, and completion after the creator CLI has exited. A fixed marker is written only to the fake child's own console input and read back; no other console is attached. The optional `--allow-elevated` choice has the same explicit test-only meaning as above. Sanitized JSON is emitted to stdout and a summary is retained in CLA's private acceptance directory; the wrapper has no `--output` option.

For a developer source check, `--source --cla '.\.venv\Scripts\python.exe'` selects the source runtime and reports `frozen: false`. It does not substitute for rerunning against the actual portable `cla.exe`.

The build uses the PEP 517 backend for wheel/sdist and PyInstaller for a one-folder portable Windows bundle. The wheel includes resources and separate CLI/MCP/GUI entry points. The GUI extra remains optional for headless users. Distinct portable names are `CLA-Launcher.exe`, `cla.exe`, and `cla-mcp.exe`.

Smoke acceptance must install the wheel non-editably into a clean environment, run it outside the source tree, and start frozen GUI/CLI/MCP without relying on the development environment. Preserve generated test results. Review the build manifest, file sizes, SHA-256 checksums, dependency inventory and copied third-party notices. Do not package personal settings, runtime evidence, Codex, engines, drivers, model weights or developer environments.

## Private release checklist

1. Inspect authenticated GitHub identity and repository permissions. Reconcile an existing repository without force-pushing or overwriting unrelated work.
2. Run source, wheel and frozen-artifact verification; report remaining skips or blockers explicitly.
3. Review source and archives for private paths, credentials and live inventory. Use only synthetic screenshots/examples.
4. Push sanitized source to the private repository. Attach actual wheel, sdist, portable ZIP, checksums, build manifest and sanitized test summary to an experimental prerelease.
5. Retrieve uploaded assets and compare hashes. Report the verified commit/tag/URLs; do not infer upload success from local files.

Do not publish to PyPI, change repository visibility or select public licensing terms without authorization. The Windows CI workflow repeats applicable build/test work; adding CI is not evidence that a remote CI run has passed. This release makes no signing, attestation or bit-for-bit reproducibility claim.
