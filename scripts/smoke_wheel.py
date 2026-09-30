"""Install the wheel non-editably in a fresh environment, outside the source tree."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    # Kept after the check for repeatable operator inspection, outside the repo.
    work = Path(tempfile.mkdtemp(prefix='cla-wheel-acceptance-'))
    environment = work / 'environment'
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    env = {k: v for k, v in os.environ.items() if k not in
           {'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CLA_PROJECT_ROOT', 'CLA_SESSION_ID'}}
    env['CLA_DATA_DIR'] = str(work / 'private')
    def run(*command):
        return subprocess.run(list(command), cwd=work, env=env, text=True,
                              capture_output=True, timeout=180, check=True)
    run(str(python), '-m', 'pip', 'install', str(wheel))
    run(str(python), '-m', 'pip', 'check')
    code = '''import importlib.resources, json, pathlib, sys
import codex_launcher_awarness as package
from codex_launcher_awarness import cli
from codex_launcher_awarness.mcp import server
assert 'site-packages' in str(pathlib.Path(package.__file__).resolve())
assert not any(n.split('.')[0] in {'PySide6','torch','tensorflow','cupy'} for n in sys.modules)
assert importlib.resources.files('codex_launcher_awarness.resources').joinpath('bootstrap.ps1').is_file()
print(json.dumps({'installed_noneditable':True,'headless_imports':True,'bootstrap_resource':True}))
'''
    checks = json.loads(run(str(python), '-c', code).stdout)
    scripts = python.parent
    suffix = '.exe' if os.name == 'nt' else ''
    assert run(str(scripts / ('cla' + suffix)), '--version').stdout.strip() == 'CLA 0.1.0 experimental'
    scan = json.loads(run(str(scripts / ('cla' + suffix)), 'scan', '--json', '--demo').stdout)
    assert scan['demo'] and scan['schema_version'] == 1
    checks['installed_console_entrypoint'] = True
    mcp_code = '''import anyio
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import os,sys
async def check():
    async with stdio_client(StdioServerParameters(command=sys.argv[1],args=[],env=dict(os.environ))) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            assert (await session.initialize()).serverInfo.name == 'cla_awareness'
            assert len((await session.list_tools()).tools) == 11
            assert not (await session.call_tool('pc_summary',{})).isError
anyio.run(check)
'''
    run(str(python), '-c', mcp_code, str(scripts / ('cla-mcp' + suffix)))
    checks['installed_mcp_handshake_list_call_shutdown'] = True
    summary = {'schema_version': 1, 'status': 'PASS', 'checks': checks,
               'environment': 'fresh venv, non-editable install, unrelated temporary cwd',
               'python': sys.version.split()[0], 'model_sessions_started': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
