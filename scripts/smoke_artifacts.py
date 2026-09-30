"""Test frozen entrypoints from an unrelated private directory, without model calls."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    bundle=args.bundle.resolve()
    results=[]
    with tempfile.TemporaryDirectory(prefix='cla-frozen-') as folder:
        work=Path(folder)
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CLA_PROJECT_ROOT','CLA_SESSION_ID'}}
        env.update(CLA_DATA_DIR=str(work/'private'),QT_QPA_PLATFORM='offscreen')
        for command in [[str(bundle/'cla.exe'),'--version'],[str(bundle/'cla.exe'),'scan','--json','--demo']]:
            run=subprocess.run(command,cwd=work,env=env,capture_output=True,text=True,timeout=30)
            assert run.returncode==0,run.stderr
            results.append({'check':Path(command[0]).name+' '+' '.join(command[1:]),'status':'PASS'})
        gui=subprocess.run([str(bundle/'CLA-Launcher.exe'),'--demo','--smoke-test'],cwd=work,env=env,timeout=30)
        assert gui.returncode==0
        results.append({'check':'frozen windowed GUI demo startup/event loop/clean exit','status':'PASS'})
        async def mcp_check():
            server=StdioServerParameters(command=str(bundle/'cla-mcp.exe'),args=[],cwd=str(work),env=env)
            async with stdio_client(server) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    init=await session.initialize()
                    assert init.serverInfo.name=='cla_awareness'
                    assert len((await session.list_tools()).tools)==11
                    value=await session.call_tool('pc_summary',{})
                    assert not value.isError,value
                    assert value.structuredContent['snapshot']['capabilities']
        anyio.run(mcp_check)
        results.append({'check':'frozen console MCP handshake/list/call/shutdown','status':'PASS'})
        eof=subprocess.run([str(bundle/'cla-mcp.exe')],input='',capture_output=True,text=True,cwd=work,env=env,timeout=15)
        assert eof.returncode==0 and eof.stdout==''
        results.append({'check':'frozen MCP EOF and clean stdout','status':'PASS'})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'schema_version':1,'checks':results,'model_sessions_started':0},indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
