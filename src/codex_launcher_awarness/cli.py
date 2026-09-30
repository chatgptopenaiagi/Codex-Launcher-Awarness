"""Headless CLI. GUI imports occur only for the explicit gui command."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .settings import load_settings, save_settings, app_dir, write_private_json
from .evidence.redact import redact


def emit(value):
    print(json.dumps(redact(value), ensure_ascii=False, indent=2, allow_nan=False))


def parser():
    root = argparse.ArgumentParser(prog="cla", description="Codex Launcher Awarness — experimental Windows awareness and launcher")
    root.add_argument("--version", action="version", version=f"CLA {__version__} experimental")
    commands = root.add_subparsers(dest="command", required=True)
    gui = commands.add_parser("gui", help="Open the desktop application")
    gui.add_argument("--demo", action="store_true")
    gui.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    gui.add_argument("--screenshot", type=Path, help="Synthetic demo screenshot output (requires --demo)")
    scan = commands.add_parser("scan", help="Observe inventory without executing discovered programs by default")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--project", type=Path)
    scan.add_argument("--probe", action="store_true", help="Run fixed probes of previously trusted executable paths")
    scan.add_argument("--demo", action="store_true")
    scan.add_argument("--export", type=Path, help="Write sanitized export, replacing local paths")
    for name in ("brief", "launch"):
        sub = commands.add_parser(name)
        sub.add_argument("--project", required=True, type=Path)
        sub.add_argument("--task", default="Help me with this project.")
        sub.add_argument("--filter", choices=["general", "coding", "symbolic-math", "blender", "gpu"], default="general")
        sub.add_argument("--probe", action="store_true")
        if name == "launch":
            sub.add_argument("--dry-run", action="store_true")
            sub.add_argument("--approve-context", action="store_true", help="Explicitly approve sending the previewed context to Codex")
            sub.add_argument("--codex", type=Path)
            sub.add_argument("--powershell", type=Path)
            sub.add_argument("--conda", type=Path)
            sub.add_argument("--conda-env")
            sub.add_argument("--permissions", choices=["inherit", "read-only", "workspace-write", "full-access-no-approval"], default="inherit")
            sub.add_argument("--profile")
            sub.add_argument("--model")
            sub.add_argument("--allow-elevated", action="store_true", help="Explicitly allow this session to use the current elevated Windows token when no unelevated desktop shell is available")
    commands.add_parser("doctor", help="Read-only CLA configuration and dependency diagnostics")
    commands.add_parser("mcp", help="Start read-only MCP on stdio")
    smoke = commands.add_parser("_launch-smoke", help=argparse.SUPPRESS)
    smoke.add_argument("--powershell", type=Path, required=True)
    smoke.add_argument("--allow-elevated", action="store_true")
    smoke.add_argument("--interactive-console", action="store_true", help=argparse.SUPPRESS)
    integration = commands.add_parser("integrate", help="Preview/apply/remove only CLA-owned configuration")
    actions = integration.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preview", action="store_true")
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--remove", action="store_true")
    integration.add_argument("--scope", choices=["user", "project"], help="Required for writes; preview defaults to user")
    integration.add_argument("--project", type=Path)
    trust = commands.add_parser("trust", help="Explicitly configure CLA-only trusted paths; no system changes")
    trust.add_argument("--executable", action="append", default=[], metavar="ID=ABSOLUTE_PATH")
    trust.add_argument("--project", action="append", default=[], type=Path)
    trust.add_argument("--endpoint", action="append", default=[])
    trust.add_argument("--enable-approved-probes", action="store_true")
    return root


def _settings_for_project(settings, project):
    if project is not None:
        path = project.expanduser().resolve()
        if not path.is_dir():
            raise ValueError("Project must be an existing directory")
        if str(path) not in settings.approved_project_roots:
            settings.approved_project_roots.append(str(path))
        return path
    return None


def main(argv=None):
    # Windows redirected streams may default to a legacy code page. Preserve
    # Unicode projects/tasks in JSON and briefs; windowed GUI streams are None.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import main as gui_main
            forwarded = []
            if args.demo:
                forwarded.append("--demo")
            if args.smoke_test:
                forwarded.append("--smoke-test")
            if args.screenshot:
                forwarded += ["--screenshot", str(args.screenshot)]
            return gui_main(forwarded)
        if args.command == "mcp":
            from .mcp.server import main as mcp_main
            mcp_main()
            return 0
        if args.command == "_launch-smoke":
            from .launch.acceptance import run_fake_launch_acceptance, start_console_launch_acceptance
            checker = start_console_launch_acceptance if args.interactive_console else run_fake_launch_acceptance
            result = checker(str(args.powershell), allow_elevated=args.allow_elevated)
            emit(result)
            return 0 if result.get("status") == ("STARTED" if args.interactive_console else "PASS") else 1
        settings = load_settings()
        if args.command == "trust":
            for entry in args.executable:
                identifier, sep, raw = entry.partition("=")
                if not sep or not identifier.isidentifier():
                    raise ValueError("Use --executable ID=ABSOLUTE_PATH")
                path = Path(raw)
                if not path.is_absolute() or not path.is_file():
                    raise ValueError("Trust requires an existing absolute executable path")
                settings.trusted_executables[identifier] = str(path.resolve())
            for project in args.project:
                _settings_for_project(settings, project)
            settings.local_endpoints = list(dict.fromkeys(settings.local_endpoints + args.endpoint))
            if args.enable_approved_probes:
                settings.probe_enabled = True
            save_settings(settings)
            emit({"ok": True, "settings_path": str(app_dir() / "settings.toml"), "trusted_ids": sorted(settings.trusted_executables), "note": "Only CLA private settings changed."})
            return 0
        if args.command == "integrate":
            from .integration import IntegrationManager
            manager = IntegrationManager(settings)
            if (args.apply or args.remove) and not args.scope:
                raise ValueError("Persistent writes require explicit --scope user or --scope project")
            scope = args.scope or "user"
            if args.remove:
                emit(manager.remove(scope, args.project))
            else:
                plan = manager.preview(scope, args.project)
                emit(manager.apply(plan) if args.apply else plan)
            return 0
        if args.command == "doctor":
            from .integration import build_mcp_command, config_inventory
            from importlib.metadata import version
            emit({"schema_version": 1, "version": __version__, "platform": sys.platform, "python": sys.version.split()[0],
                  "settings": "validated", "data_dir": str(app_dir()), "mcp_command": build_mcp_command(),
                  "dependencies": {name: version(name) for name in ["mcp", "pydantic", "psutil", "platformdirs", "tomlkit"]},
                  "codex_configuration": config_inventory(), "limitations": ["No third-party MCP handshake or Codex/model session was started."]})
            return 0
        from .discovery import DiscoveryService
        project = _settings_for_project(settings, getattr(args, "project", None))
        if getattr(args, "demo", False):
            from .evidence.demo import demo_snapshot
            snapshot = demo_snapshot()
        else:
            snapshot = DiscoveryService(settings).scan(project=project, allow_probes=args.probe, force=True)
        if args.command == "scan":
            if args.export:
                args.export.write_text(json.dumps(snapshot.sanitized(public=True), indent=2), encoding="utf-8")
            if args.json:
                emit(snapshot.sanitized())
            else:
                print("DEMO synthetic observations" if snapshot.demo else "CLA timestamped observations")
                for cap in snapshot.capabilities:
                    print(f"{cap.id}: installed={cap.installation}; ready={cap.effective_readiness()}; evidence={cap.evidence_id}")
            return 0
        from .briefing import make_briefing
        if args.command == "brief":
            print(make_briefing(snapshot, project, args.task, filter=args.filter, max_chars=settings.briefing_max_chars))
            return 0
        from .launch import LaunchManager, LaunchRequest
        # Explicit CLI path arguments approve only this invocation, never global settings.
        for identifier, selected in (("codex", args.codex), ("powershell", args.powershell), ("conda", args.conda)):
            if selected is not None:
                settings.trusted_executables[identifier] = str(selected.resolve())
        codex = str(args.codex or settings.trusted_executables.get("codex", ""))
        powershell = str(args.powershell or settings.trusted_executables.get("powershell", ""))
        if not codex or not powershell:
            raise ValueError("Select Codex/PowerShell in the GUI, trust their paths, or pass --codex and --powershell")
        request = LaunchRequest(project=str(project), task=args.task, codex_path=codex, powershell_path=powershell,
                                conda_path=str(args.conda) if args.conda else settings.trusted_executables.get("conda"),
                                conda_env=args.conda_env, permission_mode=args.permissions, profile=args.profile, model=args.model, task_filter=args.filter,
                                allow_elevated=args.allow_elevated)
        manager = LaunchManager(settings)
        prepared = manager.prepare(request, snapshot)
        if args.dry_run or not args.approve_context:
            emit({"dry_run": True, "preview": prepared.preview, "exact_prompt": prepared.prompt,
                  "notice": "No terminal opened. Approved context can leave the PC. Use GUI Preview/Start or explicit --approve-context."})
            return 0 if args.dry_run else 2
        emit(manager.launch(prepared))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps(redact({"ok": False, "error": type(exc).__name__, "message": str(exc)})), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
