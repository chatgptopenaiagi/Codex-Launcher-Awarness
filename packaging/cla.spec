# Build with the repository Python environment on Windows x64.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files('codex_launcher_awarness', includes=['resources/*'])
for distribution in ['mcp','pydantic','psutil','platformdirs','tomlkit','httpx','PyYAML','codex-launcher-awarness']:
    datas += copy_metadata(distribution)
datas = [(source, destination) for source, destination in datas if Path(source).name != 'direct_url.json']
a = Analysis([str(root/'packaging'/'entrypoint.py')], pathex=[str(root/'src')],
             binaries=[], datas=datas,
             hiddenimports=['codex_launcher_awarness.gui', 'codex_launcher_awarness.cli', 'codex_launcher_awarness.mcp.server'],
             hookspath=[], runtime_hooks=[],
             excludes=['torch','tensorflow','cupy','numpy','pandas','matplotlib','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','PySide6.Qt3DCore'],
             noarchive=False, optimize=0)
# copy_metadata may add whole directories: remove editable-install provenance
# after Analysis expands them, so no development-machine URL enters the bundle.
a.datas = [item for item in a.datas if Path(item[0]).name != 'direct_url.json']
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='CLA-Launcher', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='cla', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=True)
mcp = EXE(pyz, a.scripts, [], exclude_binaries=True, name='cla-mcp', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=True)
collect = COLLECT(gui, cli, mcp, a.binaries, a.datas, strip=False, upx=False, name='CLA-0.1.0-windows-x64')
