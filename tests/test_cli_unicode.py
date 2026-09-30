import os
from pathlib import Path
import subprocess
import sys


def test_redirected_ascii_environment_preserves_unicode_brief(tmp_path):
    project = tmp_path / "project 日本"
    project.mkdir()
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "ascii"
    environment["CLA_DATA_DIR"] = str(tmp_path / "private")
    result = subprocess.run([sys.executable, "-m", "codex_launcher_awarness", "brief",
                             "--project", str(project), "--task", "Inspect 日本"],
                            capture_output=True, encoding="utf-8", env=environment,
                            cwd=tmp_path, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 0, result.stderr
    assert "Inspect 日本" in result.stdout
    assert str(project) in result.stdout
