"""Evidence-first source understanding: cloud ASR, contact sheets and reviewed cuts."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import shutil
import sys

import analysis_store as store
import cloud_asr
from local_config import workspace_root
import media_evidence as media

SCHEMA = 'jy-material-analysis/v1'
ID = re.compile(r'[A-Za-z0-9_-]{1,80}')


def _folder(path):
    path = Path(path).expanduser()
    store.require(path.is_absolute() and str(path).isascii() and 'work' in {x.lower() for x in path.parts}
                  and '..' not in path.parts and not path.is_symlink(), 'Use an absolute ASCII job directory under work/')
    return path.resolve()


def load_task(task_path, *, full=False):
    path = store.regular(task_path)
    task = store.read(path)
    store.require(task.get('schema') == SCHEMA and task.get('id') == store.identity(task.get('request')),
                  'Analysis task identity changed')
    store.verify_source(task['request']['source'], full=full)
    root = path.parent
    if task.get('evidence_sha256'):
        evidence = store.read(store.owned_file(root, 'evidence/evidence.json', task['evidence_sha256']))
        media.verify_evidence(root / 'evidence', evidence)
    else:
        evidence = None
    if task.get('transcript_sha256'):
        transcript = store.read(store.owned_file(root, 'transcript.json', task['transcript_sha256']))
    else:
        transcript = {'segments': []}
    return path, task, evidence, transcript


def _transcribe(root, task, evidence, config, *, provider=None):
    source = store.verify_source(task['request']['source'])
    store.require(evidence['media']['audio'], 'This source has no audio; prepare with --asr none')
    provider = provider or cloud_asr.transcribe
    public = cloud_asr.public_config(config)
    store.require(public == task['request']['asr'], 'ASR account, model or chunk settings changed')
    duration = evidence['media']['duration']
    chunk_seconds = config['chunk_seconds']
    segments, chunks = [], []
    for i in range(math.ceil(duration / chunk_seconds)):
        start, span = i * chunk_seconds, min(chunk_seconds, duration - i * chunk_seconds)
        key = store.identity({'source': task['request']['source']['sha256'], 'start': start, 'duration': span,
                              'provider': public, 'audio': 'pcm16-mono16k-v1'})
        cache = _folder(task['cache_root']) / 'asr' / key
        cache.mkdir(parents=True, exist_ok=True)
        # The whole chunk is locked including extraction. The provider keeps a
        # distinct inner lock for the accepted-task submission boundary.
        with store.lock(cache):
            audio = media.extract_audio(source, cache / 'audio.wav', start, span)
            result = provider(audio, cache / 'provider', config, span)
        for sentence in result['segments']:
            end = min(duration, start + sentence['end'])
            begin = start + sentence['start']
            if end <= begin:
                continue
            row = {'id': 'ASR-' + str(len(segments) + 1).zfill(6), 'start': begin, 'end': end,
                   'text': sentence['text'], 'chunk': i + 1, 'words': [
                       {**word, 'start': start + word['start'], 'end': min(duration, start + word['end'])}
                       for word in sentence['words'] if start + word['start'] < duration]}
            segments.append(row)
        chunks.append({'index': i + 1, 'start': start, 'duration': span, 'task_id': result['task_id'],
                       'usage': result['usage'], 'cache_hit': result['cache_hit'], 'cost_cny': None})
        task['completed_asr_chunks'] = chunks
        store.save(root / 'task.json', task)
    store.verify_source(task['request']['source'])
    transcript = {'schema': 'jy-material-transcript/v1', 'source_sha256': task['request']['source']['sha256'],
                  'provider': public, 'segments': segments, 'chunks': chunks, 'timestamp_unit': 'source seconds'}
    store.save(root / 'transcript.json', transcript)
    task['transcript_sha256'] = store.digest_file(root / 'transcript.json')


def prepare(source, out, goal, model, asr='none', *, provider=None, config=None):
    source = store.regular(source)
    root = _folder(out)
    store.require(not source.is_relative_to(root),
                  'Analysis output cannot contain the source video')
    store.require(isinstance(goal, str) and 1 <= len(goal) <= 4000 and isinstance(model, str) and 1 <= len(model) <= 200,
                  'Specify an analysis goal and caller model identifier')
    store.require(asr in {'none', 'bailian'}, 'Unknown ASR provider')
    config = (config or cloud_asr.configuration()) if asr == 'bailian' else None
    request = {'source': store.file_record(source), 'goal': goal, 'model': model,
               'asr': cloud_asr.public_config(config) if config else {'provider': 'none'}}
    root.mkdir(parents=True, exist_ok=True)
    with store.lock(root):
        path = root / 'task.json'
        if path.exists():
            task = store.read(path)
            store.require(task.get('schema') == SCHEMA and task.get('id') == store.identity(request),
                          'Output already belongs to a different source, goal, model or ASR configuration')
        else:
            store.require(set(p.name for p in root.iterdir()) <= {'.analysis.lock'}, 'Output directory is not empty')
            task = {'schema': SCHEMA, 'id': store.identity(request), 'request': request, 'status': 'preparing',
                    'cache_root': str(_folder(workspace_root() / 'analysis-cache')),
                    'evidence_sha256': None, 'transcript_sha256': None}
            store.save(path, task)
        try:
            cache = Path(task['cache_root']) / 'overview' / (request['source']['sha256'] + '-v1')
            with store.lock(cache):
                media.overview(request['source'], cache)
                if not (root / 'evidence').exists():
                    shutil.copytree(cache, root / 'evidence', ignore=shutil.ignore_patterns('.analysis.lock'))
            evidence = store.read(root / 'evidence/evidence.json')
            media.verify_evidence(root / 'evidence', evidence)
            digest = store.digest_file(root / 'evidence/evidence.json')
            store.require(not task['evidence_sha256'] or task['evidence_sha256'] == digest, 'Analysis evidence changed')
            task['evidence_sha256'] = digest
            store.save(path, task)
            if config and not task.get('transcript_sha256'):
                _transcribe(root, task, evidence, config, provider=provider)
            if task.get('transcript_sha256'):
                store.owned_file(root, 'transcript.json', task['transcript_sha256'])
            task.update(status='review-ready', error=None)
            store.save(path, task)
        except Exception as error:
            task.update(status='incomplete', error=cloud_asr.safe_error(error, config or {}))
            store.save(path, task)
            raise
    return {'status': task['status'], 'task': str(path), 'task_id': task['id'],
            'chapters': evidence['chapters'], 'sample_frames': len(evidence['frames']),
            'contact_sheets': len(evidence['sheets']), 'asr_segments': len(store.read(root / 'transcript.json')['segments'])
            if task['transcript_sha256'] else 0, 'next': 'analyze read --task <task> [--chapters ...] [--query ...]'}


def read_task(task_path, chapters=None, query=None, text_budget=6000):
    path, task, evidence, transcript = load_task(task_path)
    store.require(task['status'] == 'review-ready' and evidence, 'Analysis is incomplete; resume the original prepare command')
    known = {row['id'] for row in evidence['chapters']}
    selected = set(chapters or known)
    store.require(selected and selected <= known, 'Unknown chapter selection')
    windows = [row for row in evidence['chapters'] if row['id'] in selected]
    chapter_index = not chapters and not evidence['policy']['whole_video_remote_default']
    units = [row for row in transcript['segments'] if any(row['start'] < c['end'] and row['end'] > c['start'] for c in windows)
             and (not query or query.casefold() in row['text'].casefold())]
    shown, size = [], 0
    for row in units:
        if size + len(row['text']) > text_budget:
            break
        shown.append({k: row[k] for k in ('id', 'start', 'end', 'text')}); size += len(row['text'])
    sheets = [] if chapter_index else [row for row in evidence['sheets'] if row['chapter_id'] in selected]
    return {'status': 'chapter-selection-required' if chapter_index else 'evidence-ready-for-agent-review',
            'task_id': task['id'], 'model': task['request']['model'],
            'goal': task['request']['goal'], 'coverage': windows, 'whole_video_sampled': selected == known,
            'read_scope': 'chapter-index' if chapter_index else 'selected-chapter-evidence',
            'sheets': [{**row, 'path': str(path.parent / 'evidence' / row['file'])} for row in sheets],
            'cells': [] if chapter_index else [row for row in evidence['cells'] if row['chapter_id'] in selected],
            'transcript': shown, 'matching_units': len(units), 'returned_units': len(shown),
            'limits': ['Contact sheets are discrete visual samples; inspect actual images.',
                       'Cloud transcript is speech evidence, not visual evidence.',
                       'Candidates require detail review before native assembly.'],
            'next': 'Select chapter IDs with read --chapters ... before loading long-video images.' if chapter_index
                    else 'Inspect returned images, then submit real evidence references.',
            'submission_template': {'task_id': task['id'], 'model': task['request']['model'],
                'reviewed_sheet_ids': [], 'summary': '', 'unknowns': [], 'candidates': [
                    {'id': 'CLIP-001', 'start': 0, 'end': 1, 'reason': '', 'evidence_cell_ids': [], 'asr_ids': []}]}}


def submit(task_path, submission):
    path, task, evidence, transcript = load_task(task_path)
    store.require(task['status'] == 'review-ready', 'Analysis is not ready for review')
    value = store.read(submission)
    required = {'task_id', 'model', 'reviewed_sheet_ids', 'summary', 'unknowns', 'candidates'}
    store.require(isinstance(value, dict) and set(value) == required and value['task_id'] == task['id']
                  and value['model'] == task['request']['model'], 'Review identity or fields differ from the task')
    sheets = {row['id'] for row in evidence['sheets']}
    reviewed = value['reviewed_sheet_ids']
    store.require(isinstance(reviewed, list) and reviewed and len(set(reviewed)) == len(reviewed)
                  and set(reviewed) <= sheets, 'Declare the actual reviewed sheet IDs')
    store.require(isinstance(value['summary'], str) and 0 < len(value['summary']) <= 6000
                  and isinstance(value['unknowns'], list) and all(isinstance(x, str) for x in value['unknowns']),
                  'Review requires a summary and explicit unknowns')
    cells = {row['id']: row for row in evidence['cells']}
    units = {row['id']: row for row in transcript['segments']}
    chapters = {row['id']: row for row in evidence['chapters']}
    candidates = value['candidates']
    store.require(isinstance(candidates, list) and 1 <= len(candidates) <= 100, 'Supply 1..100 reviewed candidates')
    seen = set()
    for row in candidates:
        store.require(isinstance(row, dict) and set(row) == {'id', 'start', 'end', 'reason', 'evidence_cell_ids', 'asr_ids'},
                      'Candidate fields differ from the review contract')
        store.require(isinstance(row['id'], str) and ID.fullmatch(row['id']) and row['id'] not in seen, 'Invalid candidate ID')
        seen.add(row['id'])
        store.number(row['start'], 0, evidence['media']['duration'], 'candidate start')
        store.number(row['end'], row['start'] + .2, evidence['media']['duration'], 'candidate end')
        store.require(isinstance(row['reason'], str) and 0 < len(row['reason']) <= 2000, 'Candidate requires a reason')
        refs, speech = row['evidence_cell_ids'], row['asr_ids']
        store.require(isinstance(refs, list) and refs and all(isinstance(x, str) and x in cells for x in refs),
                      'Candidate requires actual image cell references')
        store.require(all(cells[x]['sheet_id'] in reviewed and chapters[cells[x]['chapter_id']]['start'] < row['end']
                          and chapters[cells[x]['chapter_id']]['end'] > row['start']
                          and row['start'] - 1.1 <= cells[x]['actual_seconds'] <= row['end'] + 1.1 for x in refs),
                      'Candidate image evidence is outside reviewed coverage')
        store.require(isinstance(speech, list) and all(isinstance(x, str) and x in units and
                      units[x]['start'] < row['end'] and units[x]['end'] > row['start'] for x in speech),
                      'Candidate speech evidence does not overlap its source interval')
    report = {'schema': 'jy-material-review/v1', 'task_id': task['id'], 'status': 'candidates-reviewed',
              'submission': value, 'submission_sha256': store.identity(value),
              'evidence_sha256': task['evidence_sha256'], 'transcript_sha256': task['transcript_sha256']}
    with store.lock(path.parent):
        target = path.parent / 'review.json'
        if target.exists():
            store.require(store.read(target) == report, 'A different review already exists; prepare a new goal/model revision')
        else:
            store.save(target, report)
    return {'status': report['status'], 'review': str(target), 'candidates': candidates}


def reviewed(task_path):
    path, task, evidence, transcript = load_task(task_path)
    value = store.read(store.owned_file(path.parent, 'review.json'))
    store.require(value.get('task_id') == task['id'] and value.get('evidence_sha256') == task['evidence_sha256']
                  and value.get('transcript_sha256') == task['transcript_sha256']
                  and value.get('submission_sha256') == store.identity(value.get('submission')),
                  'Reviewed candidate identity changed')
    return path, task, evidence, transcript, value


def detail(task_path, candidate_id, start=None, end=None, fps=2):
    path, task, evidence, _, review = reviewed(task_path)
    candidates = [row for row in review['submission']['candidates'] if row['id'] == candidate_id]
    store.require(len(candidates) == 1, 'Unknown reviewed candidate')
    candidate = candidates[0]
    start = candidate['start'] if start is None else start
    end = candidate['end'] if end is None else end
    store.require(candidate['start'] <= start < end <= candidate['end'], 'Detail interval must be inside the candidate')
    with store.lock(path.parent):
        result = media.detail(task['request']['source'], path.parent, evidence['media'], candidate_id, start, end, fps)
    folder = Path(result['path']).parent
    return {**result, 'sheets': [{**row, 'path': str(folder / row['file'])} for row in result['sheets']],
            'next': 'Inspect detail images; verify ASR timing or play original audio, and declare the actual audio review method.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    p = sub.add_parser('prepare')
    p.add_argument('--source', required=True); p.add_argument('--out', required=True)
    p.add_argument('--goal', required=True); p.add_argument('--model', required=True)
    p.add_argument('--asr', choices=['none', 'bailian'], default='none')
    p = sub.add_parser('read')
    p.add_argument('--task', required=True); p.add_argument('--chapters', nargs='+'); p.add_argument('--query')
    p.add_argument('--text-budget', type=int, default=6000)
    p = sub.add_parser('submit')
    p.add_argument('--task', required=True); p.add_argument('--submission', required=True)
    p = sub.add_parser('detail')
    p.add_argument('--task', required=True); p.add_argument('--candidate', required=True)
    p.add_argument('--start', type=float); p.add_argument('--end', type=float); p.add_argument('--fps', type=float, default=2)
    p = sub.add_parser('assemble')
    p.add_argument('--task', required=True); p.add_argument('--selection', required=True); p.add_argument('--out', required=True)
    p.add_argument('--render', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        result = {'status': 'analysis-ready', 'media_tools': dict(zip(('ffmpeg', 'ffprobe'), media.binaries())),
                  'asr': cloud_asr.public_config(cloud_asr.configuration()), 'network_called': False}
    elif args.command == 'prepare':
        result = prepare(args.source, args.out, args.goal, args.model, args.asr)
    elif args.command == 'read':
        store.number(args.text_budget, 100, 30000, 'text budget')
        result = read_task(args.task, args.chapters, args.query, args.text_budget)
    elif args.command == 'submit':
        result = submit(args.task, args.submission)
    elif args.command == 'detail':
        result = detail(args.task, args.candidate, args.start, args.end, args.fps)
    else:
        from analysis_edit import assemble
        result = assemble(args.task, args.selection, args.out, args.render)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as error:
        print('Material analysis failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
