"""One shared frozen runtime; distinct case-insensitive-safe executable names."""
import sys
from pathlib import Path


def main():
    stem = Path(sys.executable).stem.lower()
    if stem == "cla-launcher":
        from codex_launcher_awarness.gui import main as run
    elif stem == "cla-mcp":
        from codex_launcher_awarness.mcp.server import main as run
    else:
        from codex_launcher_awarness.cli import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
