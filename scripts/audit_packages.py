"""Check release members, private path exclusion, and portable byte integrity."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    private_values = []
    for path in [Path.home(), root]:
        for text in [str(path), path.as_posix(), str(path).replace('\\', '\\\\')]:
            private_values.extend([text.encode('utf-8').lower(), text.encode('utf-16-le').lower()])
    count = 0
    def check(name, data):
        nonlocal count
        parts = Path(name).parts
        assert not any(p in {'private', 'sessions', 'snapshots', 'backups', 'logs', '.venv', '.git', '__pycache__'} for p in parts), name
        assert Path(name).name not in {'auth.json', 'direct_url.json', 'config.toml'}, name
        assert Path(name).name != 'settings.toml' or 'examples' in parts, name
        if Path(name).suffix.lower() in {'.py', '.json', '.toml', '.md', '.txt', '.yaml', '.yml', '.ps1'} or Path(name).name == 'METADATA':
            assert not any(value in data.lower() for value in private_values), 'Private development path in ' + name
        count += 1
    archives = []
    for path in sorted(args.release.iterdir()):
        if path.suffix in {'.whl', '.zip'}:
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    data = archive.read(member)
                    check(member.filename, data)
                    if path.suffix == '.zip':
                        local = args.bundle / Path(member.filename).relative_to(args.bundle.name)
                        assert local.is_file()
                        assert hashlib.sha256(data).digest() == hashlib.sha256(local.read_bytes()).digest(), member.filename
            archives.append(path.name)
        elif path.name.endswith('.tar.gz'):
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        check(member.name, archive.extractfile(member).read())
            archives.append(path.name)
    assert len(archives) == 3, archives
    summary = {'schema_version': 1, 'status': 'PASS', 'archives': archives, 'members_checked': count,
               'checks': ['archive integrity', 'runtime/private member exclusions',
                          'local home/source paths absent from text metadata', 'portable ZIP bytes match tested folder'],
               'limitations': ['Pattern/member audit is defense in depth; not an independent security audit.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
