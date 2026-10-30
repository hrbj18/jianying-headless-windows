"""Translate a bounded OVS edit EDL + local art direction into the existing native plan.

No editor, renderer, account, model, or automatic task runner is introduced.
OVS validates intent/reference boundaries; jy14_headless validates media and native fields.
Only deterministic, contiguous 1x source edits are accepted. Unsupported EDL features fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compile_plan(edl, layout):
    fps = layout['canvas']['fps']
    require(fps in (24, 25, 30, 50, 60), 'Unsupported fps')
    def us(seconds):
        frames = seconds * fps
        require(abs(frames - round(frames)) < 0.0001, 'All times must be frame aligned')
        return round(round(frames) * 1000000 / fps)
    require(not edl.get('tracks'), 'Active OVS audio/caption tracks need an explicit adapter; use native layout tracks')
    require(set(layout) <= {'name', 'canvas', 'background', 'placements', 'text_tracks', 'audio_tracks'}, 'Unknown layout field')
    segments = sorted(edl['segments'], key=lambda s: s['order'])
    require(len({s['order'] for s in segments}) == len(segments), 'Duplicate segment order')
    require(set(layout['placements']) == {s['id'] for s in segments}, 'Placements must cover exactly all EDL segments')
    visuals, mapping, cursor_frames = [], [], 0
    for s in segments:
        require(s['layer'] == 'primary' and s['source'] == 'edit', 'Only primary deterministic source edits are supported')
        spec = s['spec']
        require(set(spec) <= {'input_id', 'in_sec', 'out_sec'}, 'Unsupported edit spec; no silent drop')
        span = s['target_sec']
        require(abs(spec['out_sec'] - spec['in_sec'] - span) < 1e-7, 'Only 1x source edits are supported')
        us(span); us(spec['in_sec']); us(spec['out_sec'])
        start = round(cursor_frames * 1000000 / fps)
        cursor_frames += round(span * fps)
        end = round(cursor_frames * 1000000 / fps)
        placement = layout['placements'][s['id']]
        require(set(placement) <= {'x', 'y', 'scale', 'volume', 'opacity', 'keyframes'}, 'Unsupported placement')
        visuals.append({'source': spec['input_id'], 'source_start_us': us(spec['in_sec']),
                        'source_duration_us': end-start, 'start_us': start, 'duration_us': end-start,
                        'speed': 1, 'volume': 1, **placement})
        mapping.append({'id': s['id'], 'source': spec['input_id'], 'source_in_us': us(spec['in_sec']),
                        'target_in_us': start, 'target_out_us': end, 'reason': s.get('reason')})
    total = round(cursor_frames * 1000000 / fps)
    require(total == us(edl['total_target_sec']), 'EDL duration must exactly match the requested duration')
    w, h = map(int, edl['aspect'].split(':'))
    require(layout['canvas']['width'] * h == layout['canvas']['height'] * w, 'EDL and native canvas aspect mismatch')
    background = layout['background']
    require(set(background) == {'source', 'source_html', 'runtime_version'}, 'Background needs source, source_html, runtime_version')
    require(Path(background['source_html']).is_file(), 'Keep the editable HyperFrames HTML source')
    tracks = [
        {'type': 'video', 'name': 'HyperFrames · 可重渲动态图形底板', 'segments': [
            {'source': background['source'], 'start_us': 0, 'duration_us': total,
             'source_start_us': 0, 'source_duration_us': total, 'speed': 1, 'volume': 0}]},
        {'type': 'video', 'name': '实拍 · 每段可裁剪替换', 'segments': visuals},
    ]
    for track in layout.get('text_tracks', []):
        require(track['type'] == 'text', 'text_tracks must contain native text only')
        tracks.append(track)
    for track in layout.get('audio_tracks', []):
        require(track['type'] == 'audio', 'audio_tracks must contain native audio only')
        tracks.append(track)
    return {'schema': 'jy14-headless-plan/v1', 'name': layout['name'], 'canvas': layout['canvas'], 'tracks': tracks}, mapping


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--edl', type=Path, required=True)
    p.add_argument('--layout', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='New output directory; never overwrite prior plans')
    args = p.parse_args()
    require(not args.out.exists(), 'Output already exists; choose a new revision directory')
    provenance = ROOT / 'integrations/orkas-video-studio/provenance.json'
    upstream = load(provenance)
    for record in upstream['files']:
        require(digest(provenance.parent / record['path']) == record['sha256'], 'Pinned OVS source changed')
    validated = subprocess.run(['node', str(ROOT/'tools/validate_ovs_edl.mjs'), str(args.edl)],
                               capture_output=True, text=True, encoding='utf-8', check=False)
    require(validated.returncode == 0, 'OVS rejected EDL: ' + validated.stdout + validated.stderr)
    edl, layout = load(args.edl), load(args.layout)
    plan, mapping = compile_plan(edl, layout)
    from local_config import configure_environment
    configure_environment()
    from jy14_headless import validate_plan
    media, duration, fonts = validate_plan(plan)
    require(not media[str(Path(layout['background']['source']).resolve())]['has_audio'], 'HyperFrames background must be silent')
    args.out.mkdir(parents=True)
    report = {'status': 'compiled-and-media-validated', 'ovs_commit': upstream['commit'],
              'ovs_validation': json.loads(validated.stdout), 'edl_sha256': digest(args.edl),
              'layout_sha256': digest(args.layout), 'duration_us': duration, 'mapping': mapping,
              'hyperframes': {**layout['background'], 'html_sha256': digest(layout['background']['source_html'])},
              'media': media, 'editable': {'source_segments': len(mapping),
              'native_text_segments': sum(len(t['segments']) for t in layout.get('text_tracks', [])),
              'graphics': 'rendered video plus retained editable HTML; not native vector nodes'},
              'rendered': False, 'opened_in_editor': False}
    for filename, data in [('production.plan.json', plan), ('bridge-audit.json', report)]:
        (args.out/filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'duration_us': duration, 'output': str(args.out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
