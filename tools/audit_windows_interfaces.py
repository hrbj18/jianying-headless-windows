#!/usr/bin/env python3
"""Inventory the installed official CLI with read-only help calls and exact identity."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import draftediting_runtime as dr
import enumerate_all_commands as discovery
import windows_runtime
from local_config import configure_environment


def main():
    configure_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New task-owned evidence directory')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or not 5 <= args.timeout <= 120:
        parser.error('Use 1..4 workers and 5..120 seconds per command')
    out = args.out.resolve()
    if out.exists() or not str(out).isascii() or 'work' not in out.parts:
        parser.error('--out must be a new ASCII directory under work')
    runtime = windows_runtime.validate_runtime()
    dr.ensure_editor_running()
    out.mkdir(parents=True)
    cwd = out / 'workspace'
    cwd.mkdir()

    def probe(path):
        label = 'root' if not path else '_'.join(path)
        try:
            value = dr.run_lyra(list(path) + ['--help'], cwd, args.timeout, [cwd])
            (out / (label + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            text = value.get('stdout', '')
            return discovery.ProbeResult('ok', text=text) if text.strip() else discovery.ProbeResult('empty')
        except (ValueError, RuntimeError, OSError) as error:
            message = str(error)
            (out / (label + '.error.txt')).write_text(message, encoding='utf-8')
            state = 'unsupported' if any(token in message for token in ('ExtrasError', 'not expected', 'not implemented', 'not recognized')) else 'failed'
            return discovery.ProbeResult(state, error=message[:1000])

    previous = json.loads((ROOT / 'engine/lyra_commands.json').read_text(encoding='utf-8'))
    candidate = discovery.discover_commands(probe, previous=previous, workers=args.workers)
    candidate.update(runtime=runtime, source='live official CLI --help only',
                     account_commands_executed=False, gui_input_used=False,
                     runtime_trust_overrides=False)
    (out / 'interfaces.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'interfaces-inventoried', 'manifest': str(out / 'interfaces.json'),
                      'app_build': runtime['app_build'], 'leaf_commands': candidate['count'],
                      'help_nodes': candidate.get('discovery', {}).get('probed'),
                      'discovery_evidence': str(out / 'interfaces.json')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
