import json
import os
import shutil
from pathlib import Path

import pytest

from codex_launcher_awarness.discovery.specialists import run_wrapper


@pytest.mark.skipif(os.name != "nt" or not shutil.which("pwsh.exe"), reason="Real PowerShell wrapper argument handling")
def test_powershell_script_receives_separate_literal_arguments(tmp_path):
    fake = tmp_path / "fake wrapper ' 日本.ps1"
    fake.write_text("@{ count=$args.Count; arguments=@($args) } | ConvertTo-Json -Depth 8\n", encoding="utf-8")
    arguments = ["-c", 'mcp_servers.cla_awareness.command="C:\\Program Files\\runtime.exe"',
                 "-c", 'mcp_servers.cla_awareness.args=["-m", "module"]',
                 "mcp", "list", "--json", "O'Brien; $($literal) [brackets] 日本"]
    result = run_wrapper(fake, arguments, Path(shutil.which("pwsh.exe")), timeout=5)
    assert result.error is None
    output = json.loads(result.stdout)
    assert output["count"] == len(arguments)
    assert output["arguments"] == arguments
