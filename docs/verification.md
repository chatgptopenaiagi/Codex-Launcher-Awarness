# Verification record and resume point

Use the release's `test-summary.json` and `build-manifest.json` for the exact source revision, final test totals, tested artifact digests and statuses. Older smoke reports do not certify a later binary.

## Corrected test failures

Two intermediate discovery tests, `test_service_response_redacts_metadata` and `test_service_malformed_and_cancel`, failed while the provider moved from `urllib.request` to an owned, deadline-bounded `http.client` connection. Their old mocks no longer intercepted the implementation. The fixtures now exercise `HTTPConnection` and `read1`, with malformed response, redaction and cancellation assertions retained. The original intermediate tracebacks were not retained; this record does not invent their exception text.

A later PowerShell argument test revealed loss of Unicode in redirected output. The fixed probe wrapper explicitly uses UTF-8 in its child process and preserves the literal argument vector through a named array splat. The final full-suite result includes these regression tests.

## Separate acceptance boundaries

- Unit/provider/GUI tests include synthetic fixtures and fake backends. They test behavior without model requests.
- Fake-Codex bootstrap tests use real PowerShell and verify argument transfer, project selection, child-only environment handling and lifecycle. They do not establish that a real model received context.
- Real MCP SDK clients initialize CLA, list/call its tools, validate errors and close stdio. This is CLA awareness evidence, separate from any Blender MCP connection.
- Installed Codex's `mcp list --json` accepts CLA per-invocation overrides. This is a configuration check, not a server handshake or model session.
- Frozen startup and clean wheel installation are tested outside the checkout. Their reports identify the final artifacts.
- Real interactive Codex, approved briefing receipt, and a Codex-driven `pc_summary` call remain **NOT_RUN / BLOCKED** on the elevated-only test desktop, pending an explicit elevated acceptance opt-in or a functioning unelevated desktop. No live model acceptance was substituted by a mock or `codex exec` run.

## Resume the bounded live check

First resolve the explicit elevation choice; do not change UAC or other security settings. Open the final portable GUI, choose a trusted existing Codex and PowerShell installation, select an approved project, inspect fresh inventory, and prepare a short task asking Codex to query CLA `pc_summary` using the shown session ID. Review and approve the exact prompt, then press Start once. Verify the real response and returned CLA evidence/session ID. Record that private acceptance separately, with no credentials or workstation inventory in release assets. Do not run a repeated paid acceptance loop.

Persistent integration is unnecessary for this test. Compare the existing Codex configuration hash before and after; do not rely solely on having recorded a baseline. Until the real response is verified, describe the end-to-end launcher workflow as unverified.
