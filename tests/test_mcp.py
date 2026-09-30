import json
import os
import subprocess
import sys
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_mcp_initialize_list_call_and_errors(tmp_path):
    async def scenario():
        server = StdioServerParameters(command=sys.executable, args=["-m", "codex_launcher_awarness.mcp.server"], env={**os.environ, "CLA_DATA_DIR": str(tmp_path)})
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "cla_awareness"
                listing = await session.list_tools()
                assert len(listing.tools) == 11
                for tool in listing.tools:
                    assert tool.annotations.readOnlyHint
                    result = await session.call_tool(tool.name, {})
                    assert not result.isError, result
                    assert result.structuredContent["schema_version"] == 1
                invalid = await session.call_tool("pc_summary", {"path": "C:/private"})
                assert invalid.isError
                assert invalid.structuredContent["ok"] is False
                missing = await session.call_tool("pc_installed_engines", {"engine_id": "not-approved"})
                assert missing.isError
                result = await session.call_tool("pc_summary", {"refresh": True, "max_age_seconds": 0})
                assert result.structuredContent["snapshot"]["capabilities"]
    anyio.run(scenario)


def test_eof_shutdown_and_clean_stdout(tmp_path):
    result = subprocess.run([sys.executable, "-m", "codex_launcher_awarness.mcp.server"], input="", capture_output=True, text=True,
                            env={**os.environ, "CLA_DATA_DIR": str(tmp_path)}, timeout=8)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
