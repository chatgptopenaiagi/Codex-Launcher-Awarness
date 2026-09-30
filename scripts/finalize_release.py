"""Bind sanitized test evidence to the exact built revision and artifact bytes."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=ROOT / 'artifacts')
    parser.add_argument('--release', type=Path, default=ROOT / 'dist' / 'release')
    args = parser.parse_args()
    manifest_path = args.release / 'build-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head == manifest['source_commit'] and not manifest['tracked_source_dirty']
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip()
    suites = ET.parse(args.reports / 'pytest-final.xml').findall('.//testsuite')
    counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ['tests', 'failures', 'errors', 'skipped']}
    assert counts['tests'] and counts['failures'] == counts['errors'] == 0
    reports = {}
    for name in ['frozen-smoke', 'wheel-smoke', 'frozen-launch', 'frozen-console', 'package-audit']:
        report = json.loads((args.reports / (name + '.json')).read_text(encoding='utf-8-sig'))
        assert report.get('status', 'PASS') == 'PASS'
        if isinstance(report.get('checks'), list):
            assert all(not isinstance(c, dict) or c.get('status') == 'PASS' for c in report['checks'])
        reports[name] = report
    for item in manifest['artifacts']:
        path = args.release / item['filename']
        assert digest(path) == item['sha256'] and path.stat().st_size == item['size_bytes']
    summary = {'schema_version': 1, 'source_commit': head, 'verified_at_utc': datetime.now(timezone.utc).isoformat(),
               'component_verification': 'PASS', 'end_to_end_codex_acceptance': 'NOT_RUN',
               'blocked_reason': 'Elevated-only desktop; explicit permission for the one elevated live Codex acceptance remains pending. Default unelevated behavior preserved.',
               'live_codex_model_sessions_started': 0, 'pytest': {'status': 'PASS', **counts},
               'test_scope': 'Windows x64 / recorded Python only. Unit/GUI/provider fixtures are synthetic; PowerShell bootstrap uses fake Codex. MCP tests use real SDK transports.',
               'reports': reports,
               'configuration_preservation': {'persistent_integration_applied': False, 'comparison': 'See separate local before/after hash evidence; release contains no user configuration.'},
               'live_context_example': None,
               'limitations': ['No verified real Codex receipt or Codex-driven CLA query is claimed.',
                               'No other Python minor version, Linux desktop, or macOS desktop acceptance was run.',
                               'Binaries are unsigned; licensing decision for CLA is pending.']}
    summary_path = args.release / 'test-summary.json'
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    manifest['verification'] = {'summary': summary_path.name, 'sha256': digest(summary_path),
                                'component_status': 'PASS', 'live_codex_acceptance': 'NOT_RUN / BLOCKED'}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    lines = [f'{digest(p)}  {p.name}' for p in sorted(args.release.iterdir()) if p.is_file() and p.name != 'SHA256SUMS.txt']
    (args.release / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='ascii')
    print(json.dumps({'source_commit': head, 'pytest': counts, 'release_checksums_updated': True}, indent=2))


if __name__ == '__main__':
    main()
