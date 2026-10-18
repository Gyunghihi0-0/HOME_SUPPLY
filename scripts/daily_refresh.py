"""Bound the daily collection job and preserve validated data on failure."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from scripts.collector import KST
from scripts.pipeline import ROOT, atomic_write, load


def refresh(output, timeout=540):
    output = Path(output)
    try:
        result = subprocess.run(
            [sys.executable, '-u', '-m', 'scripts.pipeline', '--output', str(output.resolve())],
            cwd=ROOT, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        code = 'daily_refresh_timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'daily_refresh_start_failed'
        if output.exists():
            data = load(output)
            # The saved records and their original collection timestamps remain intact.
            data['generated_at'] = datetime.now(KST).isoformat()
            data['data_status'] = 'stale' if data['listings'] else 'error'
            for source in data['sources']:
                source.update(status='not_checked', error_code=code, message=code, records_count=None)
            atomic_write(output, data)
        print('::error::' + code, flush=True)
        return 1
    if result.returncode:
        return result.returncode
    data = load(output)
    failures = [s['id'] for s in data['sources'] if s['status'] in ('error', 'not_configured', 'not_checked')
                or (s.get('error_code') or '').startswith('vworld_')]
    if failures:
        print('::error::Source unavailable: ' + ', '.join(failures), flush=True)
        return 1
    if data['data_status'] != 'ok':
        print('::warning::Partial official data; review the completeness table before using analysis.', flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'docs/data/latest.json')
    args = parser.parse_args()
    raise SystemExit(refresh(args.output))
