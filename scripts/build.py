"""Repeatable Windows build. Does not publish or write Codex configuration."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"


def run(*args):
    subprocess.run(list(args), cwd=ROOT, check=True)


def file_info(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'filename': path.name, 'size_bytes': path.stat().st_size, 'sha256': digest}


def inventory(destination):
    entries = []
    licenses = destination/'third-party-licenses'
    licenses.mkdir(exist_ok=True)
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata.get('Name','').lower()):
        name = dist.metadata.get('Name','unknown')
        if name == 'codex-launcher-awarness':
            continue
        entries.append({'name':name,'version':dist.version,'license_expression':dist.metadata.get('License-Expression'),
                        'license_metadata':dist.metadata.get('License','not declared')[:1000]})
        for entry in dist.files or []:
            lowered = str(entry).lower()
            if '.dist-info/' in lowered and ('license' in entry.name.lower() or 'copying' in entry.name.lower() or 'notice' in entry.name.lower()):
                source = dist.locate_file(entry)
                if source.is_file() and source.stat().st_size < 2_000_000:
                    parts = Path(entry).parts
                    index = next(i for i, part in enumerate(parts) if part.endswith('.dist-info'))
                    relative = Path(*parts[index+1:])
                    if '..' in relative.parts:
                        continue
                    target = licenses/name/relative
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,target)
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        shutil.copyfile(python_license,licenses/'Python-LICENSE.txt')
    data = {'schema_version':1,'kind':'build-environment dependency inventory (not an attestation)',
            'includes_build_and_test_dependencies':True,'packages':entries}
    (destination/'dependency-inventory.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-freeze', action='store_true', help='Reuse existing frozen folder after separate smoke tests')
    args = parser.parse_args()
    if sys.platform != 'win32' or platform.machine().lower() not in {'amd64','x86_64'}:
        raise SystemExit('This release build requires Windows x64; other platforms are not claimed.')
    release = ROOT/'dist'/'release'
    release.mkdir(parents=True,exist_ok=True)
    run(sys.executable,'-m','build','--outdir',str(release))
    if not args.skip_freeze:
        run(sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(ROOT/'dist'/'portable'),'--workpath',str(ROOT/'build'/'pyinstaller'),str(ROOT/'packaging'/'cla.spec'))
    bundle = ROOT/'dist'/'portable'/f'CLA-{VERSION}-windows-x64'
    for name in ['CLA-Launcher.exe','cla.exe','cla-mcp.exe']:
        if not (bundle/name).is_file():
            raise SystemExit(f'Missing frozen executable: {name}')
    for name in ['README.md','SECURITY.md','CHANGELOG.md','LICENSE-PENDING.md','THIRD-PARTY-NOTICES.md']:
        shutil.copyfile(ROOT/name,bundle/name)
    shutil.copytree(ROOT/'docs',bundle/'docs',dirs_exist_ok=True)
    dependency_inventory = inventory(bundle)
    shutil.copyfile(bundle/'dependency-inventory.json',release/'dependency-inventory.json')
    archive = release/f'CLA-{VERSION}-windows-x64-portable.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as stream:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                stream.write(path,path.relative_to(bundle.parent))
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked_changes = subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
    manifest = {'schema_version':1,'product':'Codex Launcher Awarness','version':VERSION,'experimental':True,
                'built_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':commit,'tracked_source_dirty':bool(tracked_changes.strip()),
                'platform':platform.platform(),'architecture':platform.machine(),'python':platform.python_version(),
                'pyinstaller':importlib.metadata.version('pyinstaller'),'pyside6':importlib.metadata.version('PySide6'),
                'signing':'unsigned','reproducibility':'repeatable scripts; bit-for-bit reproducibility not claimed',
                'executables':[file_info(bundle/name) for name in ['CLA-Launcher.exe','cla.exe','cla-mcp.exe']],
                'artifacts':[file_info(p) for p in sorted(release.iterdir()) if p.suffix in {'.whl','.gz','.zip'}],
                'dependency_inventory':'dependency-inventory.json'}
    (release/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    checksums = [f"{file_info(p)['sha256']}  {p.name}" for p in sorted(release.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt']
    (release/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='ascii')
    print(json.dumps({'release_directory':str(release),'manifest':manifest},indent=2))


if __name__=='__main__':
    main()
