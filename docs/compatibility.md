# Compatibility decisions

The installed executables and their help are the authority for this release. Documentation describes mechanisms; it does not prove installation, permission, connectivity or readiness.

## Recorded build baseline

| Component | Inspected baseline | Decision |
| --- | --- | --- |
| Operating system | Windows x64 | Only tested delivery target; no cross-platform desktop claim. |
| Python | 3.14.7 | Dedicated build environment; existing Python/Conda installations remain unchanged. |
| PySide6 | 6.11.2 | Optional GUI dependency; excluded from headless startup imports. |
| PyInstaller | 6.22.3 | One-folder Windows portable bundle; GUI and stdio MCP have distinct executable names. |
| MCP Python SDK | 1.30.0 | Standard maintained v1 SDK, constrained below v2. |
| Codex CLI | 0.156.1 | Explicit selected installation; no upgrade or installation switching. |
| PowerShell | 7.6.6 | Fixed bootstrap with native argument arrays; Windows PowerShell is unsupported. |

The wheel declares Python 3.11–3.14 compatibility. The baseline above is the actual release test interpreter; declaration is not evidence that every Python minor version was tested. Exact dependency versions, source commit, platform and artifact hashes belong to the build manifest and dependency inventory accompanying each build. Consult the release test summary for PASS, FAIL, SKIPPED and NOT_RUN results.

## Live acceptance boundary for this prerelease

The real Codex interactive launch, receipt of its initial context, and a model-driven awareness query are **NOT_RUN / BLOCKED** for this prerelease. No real Codex model session was started for acceptance; model calls are **0**. The default unelevated route is blocked on the tested elevated-only desktop, and an elevated opt-in live model session was not exercised.

Real PowerShell process/bootstrap checks use a fixed **fake Codex script**. Those checks establish argument transfer, project selection and lifecycle behavior, not model receipt or reasoning. Actual MCP client handshakes/tool calls and synthetic GUI smoke tests are separate checks; neither substitutes for the blocked live Codex end-to-end acceptance. The private experimental prerelease retains this limitation explicitly.

## Codex interfaces

Installed help was inspected for the initial prompt, `-C` project selection, `-c` configuration overrides, `-s` sandbox selection, `-a` approval policy, `-p` profile, `-m` model, and `mcp add`. CLA does not assume unsupported flags such as `--no-daemon`.

Default launch inherits effective Codex settings. Explicit permission options are shown in preview; full access with no approval uses `-s danger-full-access -a never` only when selected. Session MCP overrides use the actual installed CLA console runtime. `CODEX_HOME` is respected without reading authentication files or creating a replacement home.

Codex guidance inventory recognizes `AGENTS.override.md` before `AGENTS.md` in the same scope. CLA offers a short guidance block and does not install it automatically. Project trust and managed/invocation settings can affect effective Codex configuration beyond passive inventory.

Relevant primary references:

- [Codex MCP](https://developers.openai.com/codex/mcp/)
- [Codex AGENTS.md discovery](https://developers.openai.com/codex/guides/agents-md/)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference/)
- [Codex CLI reference](https://developers.openai.com/codex/cli/reference/)

Some requested legacy documentation URLs redirected or returned a retrieval error during implementation. Local CLI help and tested arguments remain the compatibility authority; CLA does not infer unsupported behavior from unavailable pages.

## Windows and specialist boundaries

Batch-only Codex wrappers are refused unless a same-directory PowerShell companion exists; the preview discloses that companion. Batch specialist probes use a bounded PowerShell wrapper and reject metacharacters that cannot safely cross `cmd.exe` parsing. Maxima checks pass a fixed private batch file, avoiding the caret loss possible with inline expressions. Arbitrary Maxima build identifiers are preserved without claiming an official-release provenance. Its fixed checks cover arithmetic, factorization equivalence, differentiation and definite integration with user initialization disabled.

The default terminal is unelevated. An elevated launcher can use an existing same-user unelevated desktop token. If the desktop is elevated too, the default safely refuses; the tested restricted-token experiment failed before the bootstrap and is not a production fallback. An explicit per-launch GUI option or `--allow-elevated` permits inheriting the current administrator token. That option is off by default, appears in preview, and does not modify UAC, execution policy or persistent security settings. The bootstrap refuses administrator execution without the explicit manifest choice. Default unelevated acceptance is blocked on an elevated-only desktop; a successful opt-in elevated launch is a separate result.

Blender version evidence does not establish a scene/render check or a connected Blender MCP. Driver-reported CUDA support is separate from toolkit/library presence and successful PyTorch execution. WSL inventory does not launch distributions. Local health/model metadata does not prove a particular model identity or inference capability.

Packaging follows [PyPA's project packaging guidance](https://packaging.python.org/en/latest/tutorials/packaging-projects/). The portable layout follows [PyInstaller one-folder operation](https://pyinstaller.org/en/stable/operating-mode.html). Windows argument decisions are informed by [PowerShell parsing rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing). None of these references imply binary signing or bit-for-bit reproducibility.
