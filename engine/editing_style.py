"""Evidence-bound editing style studies, explicit distillation and native reuse.

The Nuwa workflow is adapted as a research contract: multiple references,
conditional rules, timestamped examples and a separate holdout. This module
does not infer style from filenames or mark generated images as reviewed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import analysis_store as store
import material_analysis as analysis
import analysis_edit as edit

STUDY = 'jy-editing-style-study/v1'
PROFILE = 'jy-editing-style-profile/v1'
DIMENSIONS = {'selection', 'narrative', 'pacing', 'subtitles', 'framing', 'audio', 'graphics'}
PARAMETERS = {'subtitle_max_chars': (2, 32), 'subtitle_size': (1, 20), 'subtitle_y': (-1, 1),
              'title_size': (1, 25), 'title_y': (-1, 1), 'video_scale': (1, 1.6)}
TEXT_STYLE = {'size', 'y', 'color', 'border_color', 'border_width'}


def _fields(value, fields, label):
    store.require(isinstance(value, dict) and set(value) == set(fields), label + ' fields differ from the contract')


def _text(value, label, maximum=4000):
    store.require(isinstance(value, str) and value.strip() and len(value) <= maximum, label + ' requires nonempty text')


def _ids(value, allowed, label, *, empty=False):
    store.require(isinstance(value, list) and (value or empty) and all(isinstance(x, str) for x in value)
                  and len(value) == len(set(value)) and set(value) <= set(allowed), 'Invalid ' + label)
    return set(value)


def _identifier(value):
    store.require(isinstance(value, str) and analysis.ID.fullmatch(value), 'Invalid style rule or example ID')
    return value


def _hash(value, label, *, nullable=False):
    store.require((nullable and value is None) or isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value),
                  'Invalid ' + label + ' SHA256')


def _study_record(value):
    _fields(value, {'schema', 'id', 'request'}, 'Style study')
    store.require(value['schema'] == STUDY and value['id'] == store.identity(value['request']), 'Style study identity changed')
    request = value['request']; _fields(request, {'name', 'references', 'holdout_task_ids'}, 'Style study request')
    _text(request['name'], 'Style name', 200)
    store.require(isinstance(request['references'], list) and 2 <= len(request['references']) <= 100, 'Use 2..100 style references')
    tasks, sources = set(), set()
    for reference in request['references']:
        _fields(reference, {'task', 'task_id', 'source_sha256', 'evidence_sha256', 'transcript_sha256'}, 'Study reference')
        _hash(reference['task_id'], 'task identity'); _hash(reference['source_sha256'], 'source')
        _hash(reference['evidence_sha256'], 'evidence'); _hash(reference['transcript_sha256'], 'transcript', nullable=True)
        store.require(isinstance(reference['task'], str) and Path(reference['task']).is_absolute(), 'Reference task must have an absolute trace path')
        store.require(reference['task_id'] not in tasks and reference['source_sha256'] not in sources,
                      'Reference tasks must have distinct source content')
        tasks.add(reference['task_id']); sources.add(reference['source_sha256'])
    holdout = _ids(request['holdout_task_ids'], tasks, 'holdout task IDs', empty=True)
    store.require(len(tasks - holdout) >= 2, 'At least two distinct training references are required')


def _immutable(path, value):
    if path.exists():
        store.require(store.read(path) == value, 'Output already belongs to a different immutable style revision')
    else:
        store.save(path, value)


def prepare(references_list, out):
    value = store.read(references_list)
    store.require(isinstance(value, dict) and {'name', 'tasks'} <= set(value)
                  and set(value) <= {'name', 'tasks', 'holdout_task_ids'}, 'Invalid reference study fields')
    _text(value['name'], 'Style name', 200)
    store.require(isinstance(value['tasks'], list) and 2 <= len(value['tasks']) <= 100, 'Use 2..100 reference tasks')
    references, ids, sources = [], set(), set()
    for task_path in value['tasks']:
        path, task, evidence, _ = analysis.load_task(task_path)
        store.require(task['status'] == 'review-ready' and evidence, 'Reference analysis is incomplete')
        store.require(task['id'] not in ids and task['request']['source']['sha256'] not in sources,
                      'Reference tasks must have distinct source content')
        ids.add(task['id']); sources.add(task['request']['source']['sha256'])
        references.append({'task': str(path), 'task_id': task['id'], 'source_sha256': task['request']['source']['sha256'],
                           'evidence_sha256': task['evidence_sha256'], 'transcript_sha256': task['transcript_sha256']})
    holdout = _ids(value.get('holdout_task_ids', []), ids, 'holdout task IDs', empty=True)
    store.require(len(ids - holdout) >= 2, 'At least two distinct training references are required')
    request = {'name': value['name'], 'references': references, 'holdout_task_ids': sorted(holdout)}
    record = {'schema': STUDY, 'id': store.identity(request), 'request': request}
    root = analysis._folder(out); root.mkdir(parents=True, exist_ok=True)
    with store.lock(root):
        store.require(set(p.name for p in root.iterdir()) <= {'.analysis.lock', 'study.json'}, 'Study output is not empty')
        _immutable(root / 'study.json', record)
    return {'status': 'awaiting-agent-research', 'study': str(root / 'study.json'), 'study_id': record['id'],
            'training_references': len(ids - holdout), 'holdout_references': len(holdout)}


def load_study(study_path):
    path = store.regular(study_path); value = store.read(path)
    _study_record(value)
    loaded = {}
    for reference in value['request']['references']:
        item = analysis.load_task(reference['task'])
        _, task, evidence, _ = item
        store.require(task['id'] == reference['task_id'] and task['status'] == 'review-ready' and evidence
                      and task['request']['source']['sha256'] == reference['source_sha256']
                      and task['evidence_sha256'] == reference['evidence_sha256']
                      and task['transcript_sha256'] == reference['transcript_sha256'], 'Reference evidence revision changed')
        loaded[task['id']] = item
    return path, value, loaded


def read_study(study_path):
    _, study, loaded = load_study(study_path)
    references = []
    for task_id, (path, task, evidence, transcript) in loaded.items():
        references.append({'task_id': task_id, 'task': str(path), 'source': task['request']['source']['path'],
                           'role': 'holdout' if task_id in study['request']['holdout_task_ids'] else 'training',
                           'duration': evidence['media']['duration'], 'contact_sheets': len(evidence['sheets']),
                           'asr_segments': len(transcript['segments']),
                           'read_command': 'analyze read --task "' + str(path) + '"'})
    return {'study_id': study['id'], 'name': study['request']['name'], 'references': references,
            'next': 'Actually inspect reference images and source ASR. Submit rules with timestamped examples from distinct training sources.',
            'submission_template': {'study_id': study['id'], 'version': 1, 'model': 'actual caller model or explicit unreported label',
                'summary': '', 'unknowns': [], 'reviewed_sheets': [{'task_id': references[0]['task_id'], 'sheet_ids': []}],
                'rules': [{'id': 'RULE-001', 'dimension': 'subtitles', 'when': '', 'action': '', 'avoid': '',
                           'support': ['EXAMPLE-001', 'EXAMPLE-002'], 'parameters': {'subtitle_max_chars': [4, 12]}}],
                'examples': [{'id': 'EXAMPLE-001', 'task_id': references[0]['task_id'], 'start': 0, 'end': 1,
                              'cell_ids': [], 'asr_ids': [], 'observation': ''}], 'holdout_evaluations': []}}


def _evidence_refs(item, cell_ids, asr_ids, reviewed, start, end):
    _, _, evidence, transcript = item
    store.number(start, 0, evidence['media']['duration'], 'example start')
    store.number(end, start + .01, evidence['media']['duration'], 'example end')
    cells = {x['id']: x for x in evidence['cells']}; units = {x['id']: x for x in transcript['segments']}
    _ids(cell_ids, cells, 'example image cell IDs')
    _ids(asr_ids, units, 'example ASR IDs', empty=True)
    store.require(all(cells[x]['sheet_id'] in reviewed and start - .05 <= cells[x]['actual_seconds'] <= end + .05
                      for x in cell_ids), 'Example image evidence is outside reviewed source coverage')
    store.require(all(units[x]['start'] < end and units[x]['end'] > start for x in asr_ids),
                  'Example ASR clock is outside its source interval')
    return {'cells': [cells[x] for x in cell_ids], 'speech': [units[x] for x in asr_ids]}


def _validate_submission(study, loaded, value):
    _fields(value, {'study_id', 'version', 'model', 'summary', 'unknowns', 'reviewed_sheets', 'rules', 'examples',
                    'holdout_evaluations'}, 'Distillation')
    store.require(value['study_id'] == study['id'], 'Distillation targets a different study')
    store.require(type(value['version']) is int and value['version'] >= 1, 'Style version must be a positive integer')
    _text(value['model'], 'Research model', 200); _text(value['summary'], 'Style summary', 6000)
    store.require(isinstance(value['unknowns'], list) and all(isinstance(x, str) for x in value['unknowns']),
                  'Declare style uncertainties')
    store.require(isinstance(value['reviewed_sheets'], list), 'Declare actual reference sheets reviewed')
    reviewed = {}
    for row in value['reviewed_sheets']:
        _fields(row, {'task_id', 'sheet_ids'}, 'Reviewed reference')
        store.require(isinstance(row['task_id'], str) and row['task_id'] in loaded and row['task_id'] not in reviewed,
                      'Unknown or repeated reviewed reference')
        reviewed[row['task_id']] = _ids(row['sheet_ids'], {x['id'] for x in loaded[row['task_id']][2]['sheets']},
                                        'reviewed reference sheets')
    holdout = set(study['request']['holdout_task_ids'])
    examples, bound = {}, []
    store.require(isinstance(value['examples'], list) and 2 <= len(value['examples']) <= 1000, 'Supply 2..1000 style examples')
    for example in value['examples']:
        _fields(example, {'id', 'task_id', 'start', 'end', 'cell_ids', 'asr_ids', 'observation'}, 'Style example')
        key = _identifier(example['id']); task_id = example['task_id']
        store.require(isinstance(task_id, str) and key not in examples and task_id in reviewed and task_id not in holdout,
                      'Style training examples must be unique and cannot use holdout references')
        _text(example['observation'], 'Example observation')
        refs = _evidence_refs(loaded[task_id], example['cell_ids'], example['asr_ids'], reviewed[task_id],
                              example['start'], example['end'])
        examples[key] = example
        task = loaded[task_id][1]
        bound.append({'id': key, 'task_id': task_id, 'source_sha256': task['request']['source']['sha256'],
                      'evidence_sha256': task['evidence_sha256'], 'transcript_sha256': task['transcript_sha256'], **refs})
    store.require(isinstance(value['rules'], list) and 1 <= len(value['rules']) <= 100, 'Supply 1..100 conditional style rules')
    rules = {}
    for rule in value['rules']:
        _fields(rule, {'id', 'dimension', 'when', 'action', 'avoid', 'support', 'parameters'}, 'Style rule')
        key = _identifier(rule['id'])
        store.require(key not in rules and isinstance(rule['dimension'], str) and rule['dimension'] in DIMENSIONS,
                      'Unknown dimension or repeated rule')
        for field in ('when', 'action', 'avoid'):
            _text(rule[field], 'Rule ' + field)
        support = _ids(rule['support'], examples, 'rule support')
        store.require(len({examples[x]['task_id'] for x in support}) >= 2,
                      'Each rule needs examples from at least two distinct training sources')
        store.require(isinstance(rule['parameters'], dict) and set(rule['parameters']) <= set(PARAMETERS), 'Unknown style parameter')
        for field, limits in rule['parameters'].items():
            low, high = PARAMETERS[field]
            store.require(isinstance(limits, list) and len(limits) == 2, 'Style parameter needs a bounded range')
            store.number(limits[0], low, high, field); store.number(limits[1], limits[0], high, field)
            if field == 'subtitle_max_chars':
                store.require(all(type(x) is int for x in limits), 'Subtitle character limits must be integers')
        rules[key] = rule
    store.require(isinstance(value['holdout_evaluations'], list), 'Holdout evaluations must be separate observations')
    evaluated = set()
    for row in value['holdout_evaluations']:
        _fields(row, {'task_id', 'observations', 'rule_ids', 'cell_ids', 'asr_ids'}, 'Holdout evaluation')
        key = row['task_id']
        store.require(isinstance(key, str) and key in holdout and key in reviewed and key not in evaluated,
                      'Evaluate each declared holdout separately')
        evaluated.add(key); _text(row['observations'], 'Holdout observations')
        _ids(row['rule_ids'], rules, 'evaluated rule IDs')
        _evidence_refs(loaded[key], row['cell_ids'], row['asr_ids'], reviewed[key], 0, loaded[key][2]['media']['duration'])
    return bound, evaluated


def _freeze_references(study, loaded, submission):
    """Keep the evidence needed to revalidate rules without reopening videos."""
    used = {task_id: {'cells': set(), 'speech': set()} for task_id in loaded}
    for row in submission['examples'] + submission['holdout_evaluations']:
        used[row['task_id']]['cells'].update(row['cell_ids'])
        used[row['task_id']]['speech'].update(row['asr_ids'])
    result = []
    for reference in study['request']['references']:
        task_id = reference['task_id']; _, _, evidence, transcript = loaded[task_id]
        result.append({**reference, 'duration': evidence['media']['duration'],
                       'sheet_ids': [x['id'] for x in evidence['sheets']],
                       'cells': [x for x in evidence['cells'] if x['id'] in used[task_id]['cells']],
                       'speech': [x for x in transcript['segments'] if x['id'] in used[task_id]['speech']]})
    return result


def _frozen_loaded(study, snapshots):
    """Validate local snapshot semantics, including clocks and distinct sources."""
    _study_record(study)
    references = {x['task_id']: x for x in study['request']['references']}
    store.require(isinstance(snapshots, list) and len(snapshots) == len(references), 'Frozen reference count differs from study')
    loaded = {}
    for row in snapshots:
        _fields(row, {'task', 'task_id', 'source_sha256', 'evidence_sha256', 'transcript_sha256',
                      'duration', 'sheet_ids', 'cells', 'speech'}, 'Frozen reference')
        key = row['task_id']
        store.require(isinstance(key, str) and key in references and key not in loaded, 'Unknown or repeated frozen reference')
        store.require({k: row[k] for k in references[key]} == references[key], 'Frozen reference differs from study manifest')
        duration = store.number(row['duration'], .1, 86400, 'frozen source duration')
        sheets = _ids(row['sheet_ids'], row['sheet_ids'], 'frozen sheet IDs')
        store.require(isinstance(row['cells'], list) and isinstance(row['speech'], list), 'Frozen evidence must contain lists')
        store.require(row['transcript_sha256'] is not None or not row['speech'], 'Frozen speech requires a source transcript identity')
        cells = set()
        for cell in row['cells']:
            _fields(cell, {'id', 'frame_id', 'sheet_id', 'chapter_id', 'actual_seconds'}, 'Frozen image cell')
            _text(cell['id'], 'Frozen cell ID', 200); _text(cell['frame_id'], 'Frozen frame ID', 200)
            _text(cell['chapter_id'], 'Frozen chapter ID', 200)
            store.require(isinstance(cell['sheet_id'], str) and cell['sheet_id'] in sheets and cell['id'] not in cells,
                          'Frozen image cell has an unknown sheet or repeated identity')
            store.number(cell['actual_seconds'], 0, duration + 1.1, 'frozen image PTS'); cells.add(cell['id'])
        speech = set()
        for unit in row['speech']:
            required = {'id', 'start', 'end', 'text', 'words'}
            store.require(isinstance(unit, dict) and required <= set(unit) and set(unit) <= required | {'chunk'},
                          'Frozen ASR unit fields differ from the contract')
            _text(unit['id'], 'Frozen ASR ID', 100)
            store.require(unit['id'] not in speech and isinstance(unit['text'], str) and isinstance(unit['words'], list),
                          'Invalid or repeated frozen ASR unit')
            store.number(unit['start'], 0, duration, 'frozen ASR start')
            store.number(unit['end'], unit['start'] + .000001, duration, 'frozen ASR end')
            for word in unit['words']:
                _fields(word, {'start', 'end', 'text'}, 'Frozen ASR word')
                store.require(isinstance(word['text'], str), 'Frozen word text must be text')
                store.number(word['start'], unit['start'] - .000001, unit['end'] + .000001, 'frozen word start')
                store.number(word['end'], word['start'], unit['end'] + .000001, 'frozen word end')
            speech.add(unit['id'])
        task = {'request': {'source': {'sha256': row['source_sha256']}},
                'evidence_sha256': row['evidence_sha256'], 'transcript_sha256': row['transcript_sha256']}
        evidence = {'media': {'duration': duration}, 'cells': row['cells'], 'sheets': [{'id': x} for x in row['sheet_ids']]}
        loaded[key] = (None, task, evidence, {'segments': row['speech']})
    return loaded


def distill(study_path, submission, out):
    path, study, loaded = load_study(study_path)
    value = store.read(submission); bound, evaluated = _validate_submission(study, loaded, value)
    payload = {'study': str(path), 'study_sha256': store.digest_file(path), 'study_id': study['id'],
               'name': study['request']['name'], 'submission': value, 'bound_examples': bound,
               'frozen_study': study, 'frozen_references': _freeze_references(study, loaded, value),
               'generalization_status': 'agent-reviewed-holdout' if evaluated else 'not-yet-checked-on-holdout'}
    result = {'schema': PROFILE, 'id': store.identity(payload), 'payload': payload}
    root = analysis._folder(out); root.mkdir(parents=True, exist_ok=True)
    with store.lock(root):
        store.require(set(p.name for p in root.iterdir()) <= {'.analysis.lock', 'profile.json'}, 'Profile output is not empty')
        _immutable(root / 'profile.json', result)
    return {'status': 'style-distilled', 'profile': str(root / 'profile.json'), 'profile_id': result['id'],
            'name': payload['name'], 'rules': len(value['rules']), 'examples': len(bound),
            'generalization_status': payload['generalization_status'], 'semantic_judgments': 'agent-authored, evidence-bound'}


def inspect(profile_path, *, verify_references=False):
    path = store.regular(profile_path); value = store.read(path)
    _fields(value, {'schema', 'id', 'payload'}, 'Style profile')
    store.require(value.get('schema') == PROFILE and value.get('id') == store.identity(value.get('payload')),
                  'Style profile identity changed')
    payload = value['payload']
    _fields(payload, {'study', 'study_sha256', 'study_id', 'name', 'submission', 'bound_examples', 'frozen_study', 'frozen_references',
                       'generalization_status'}, 'Frozen style profile')
    _hash(payload['study_sha256'], 'study bytes')
    frozen_study = payload['frozen_study']; loaded_snapshot = _frozen_loaded(frozen_study, payload['frozen_references'])
    store.require(payload['study_id'] == frozen_study['id'] and payload['name'] == frozen_study['request']['name'],
                  'Frozen style study identity changed')
    frozen_bound, evaluated = _validate_submission(frozen_study, loaded_snapshot, payload['submission'])
    store.require(payload['bound_examples'] == frozen_bound, 'Frozen bound examples differ from validated evidence')
    expected_status = 'agent-reviewed-holdout' if evaluated else 'not-yet-checked-on-holdout'
    store.require(payload['generalization_status'] == expected_status, 'Holdout status differs from evaluated evidence')
    # Reuse validates the frozen artifact, rather than requiring the reference
    # library to remain mounted forever. Explicit research audits can re-read
    # the original images and transcripts with --verify-references.
    if verify_references:
        study_path = store.regular(payload['study'])
        store.require(store.digest_file(study_path) == payload['study_sha256'], 'Style study bytes changed')
        _, study, loaded = load_study(study_path)
        bound, _ = _validate_submission(study, loaded, payload['submission'])
        store.require(payload['study_id'] == study['id'] and payload['bound_examples'] == bound, 'Bound style examples changed')
    return value


def _style(value, maximum):
    _fields(value, TEXT_STYLE, 'Native text style')
    store.number(value['size'], 1, maximum, 'text size'); store.number(value['y'], -1, 1, 'text y')
    store.number(value['border_width'], 0, .2, 'text border width')
    for field in ('color', 'border_color'):
        store.require(isinstance(value[field], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value[field]), 'Use #RRGGBB text colors')


def compile_style(task_path, selection_path, profile_path, treatment_path):
    profile = inspect(profile_path); treatment = store.read(treatment_path)
    required = {'profile_id', 'rule_ids', 'notes', 'subtitle', 'titles', 'video_scale'}
    store.require(isinstance(treatment, dict) and required <= set(treatment) and set(treatment) <=
                  required | {'name', 'font_path', 'subtitle_replacements', 'subtitle_omissions'},
                  'Style treatment fields differ from the contract')
    store.require(treatment['profile_id'] == profile['id'], 'Treatment targets another style revision')
    rules = {x['id']: x for x in profile['payload']['submission']['rules']}
    active = _ids(treatment['rule_ids'], rules, 'applied style rules')
    _text(treatment['notes'], 'Explain editorial rule application')
    subtitle = treatment['subtitle']
    _fields(subtitle, TEXT_STYLE | {'max_chars'}, 'Subtitle treatment')
    _style({k: subtitle[k] for k in TEXT_STYLE}, 20)
    store.require(type(subtitle['max_chars']) is int and 2 <= subtitle['max_chars'] <= 32, 'Subtitle character budget must be 2..32')
    store.number(treatment['video_scale'], 1, 1.6, 'video scale')
    titles = treatment['titles']; store.require(isinstance(titles, list) and len(titles) <= 30, 'Use at most 30 title overlays')
    values = {'subtitle_max_chars': [subtitle['max_chars']], 'subtitle_size': [subtitle['size']],
              'subtitle_y': [subtitle['y']], 'video_scale': [treatment['video_scale']], 'title_size': [], 'title_y': []}
    for title in titles:
        _fields(title, TEXT_STYLE | {'text', 'start', 'end'}, 'Title overlay')
        _style({k: title[k] for k in TEXT_STYLE}, 25); _text(title['text'], 'Title overlay text', 100)
        values['title_size'].append(title['size']); values['title_y'].append(title['y'])
    for key in active:
        for field, (low, high) in rules[key]['parameters'].items():
            store.require(values[field], 'Treatment omitted an applied style parameter: ' + field)
            for value in values[field]:
                store.number(value, low, high, 'Applied rule ' + key + ' ' + field)
    corrections = treatment.get('subtitle_replacements', [])
    store.require(isinstance(corrections, list) and len(corrections) <= 100, 'Invalid reviewed subtitle corrections')
    for correction in corrections:
        _fields(correction, {'from', 'to', 'asr_ids', 'reason'}, 'Reviewed subtitle correction')
        _text(correction['from'], 'Original ASR text', 50); _text(correction['to'], 'Verified correction text', 50)
        _text(correction['reason'], 'Correction source-audio review evidence')
        store.require(correction['from'] != correction['to'] and isinstance(correction['asr_ids'], list)
                      and correction['asr_ids'] and all(isinstance(x, str) for x in correction['asr_ids']),
                      'Bind subtitle corrections to actual source ASR units')
    omissions = treatment.get('subtitle_omissions', [])
    store.require(isinstance(omissions, list), 'Subtitle omissions must be an explicit list of reviewed ASR units')
    plan, audit = edit.compile_selection(task_path, selection_path, subtitle_max_chars=subtitle['max_chars'],
                                         subtitle_replacements=corrections,
                                         subtitle_omissions=omissions)
    duration = audit['duration_us'] / 1e6
    for segment in plan['tracks'][0]['segments']:
        segment['scale'] = treatment['video_scale']
    text_style = {k: subtitle[k] for k in TEXT_STYLE}
    for track in plan['tracks'][1:]:
        for segment in track['segments']:
            segment.update(text_style)
    previous = 0; overlays = []
    for title in titles:
        start = store.number(title['start'], previous, duration, 'title start')
        end = store.number(title['end'], start + .033334, duration, 'title end')
        # Round to the same output clock, while ensuring overlays remain inside
        # the assembled main track. Titles never rewrite source speech text.
        first, last = round(start * 30), round(end * 30)
        a, b = round(first * 1e6 / 30), min(audit['duration_us'], round(last * 1e6 / 30))
        store.require(b > a, 'Title is shorter than one output frame')
        overlays.append({**{k: title[k] for k in TEXT_STYLE | {'text'}}, 'start_us': a, 'duration_us': b - a})
        previous = end
    if overlays:
        plan['tracks'].append({'type': 'text', 'name': 'Explicit style title overlays', 'segments': overlays})
    font_record = None
    if 'font_path' in treatment:
        _text(treatment['font_path'], 'Standalone font path')
        font = store.regular(treatment['font_path'])
        store.require(font.suffix.casefold() == '.ttf', 'Use a standalone native-accepted TTF font')
        font_record = store.file_record(font)
        for track in plan['tracks'][1:]:
            for segment in track['segments']:
                segment['font_path'] = str(font)
    treatment_hash = store.identity(treatment)
    plan['name'] = 'style-' + profile['id'][:8] + '-' + audit['task_id'][:8] + '-' + treatment_hash[:8]
    if 'name' in treatment:
        name = treatment['name']
        _text(name, 'Draft name', 200)
        store.require(len(name.encode('utf8')) < 200 and name.strip() == name and not name.startswith('.')
                      and not any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
                      and not name.endswith(('.', ' ')), 'Draft name must be one safe directory component')
        plan['name'] = name
    audit['style'] = {'profile_id': profile['id'], 'profile_sha256': store.digest_file(profile_path),
                      'name': profile['payload']['name'], 'version': profile['payload']['submission']['version'],
                      'applied_rule_ids': sorted(active), 'treatment_sha256': treatment_hash, 'treatment': treatment,
                      'font': font_record, 'subtitle_corrections': 'Same-length reviewed text on original whole-word spans; no character-clock inference',
                      'subtitle_omissions': audit.get('subtitle_omissions', []),
                      'automatically_enforced': 'Numeric ranges, source clock, original audio and explicit native text/scale fields',
                      'editorial_declaration': 'Rule choice, selection and title claims require agent judgment; not automatic visual inference'}
    # Bind treatment into assembly identity; a normal analyze selection can be
    # reused with different style profiles only in a fresh output directory.
    audit['selection_sha256'] = store.identity({'source_selection': audit['selection_sha256'],
                                              'profile_id': profile['id'], 'treatment': treatment_hash})
    return plan, audit


def assemble(task_path, selection_path, profile_path, treatment_path, out, render=False):
    plan, audit = compile_style(task_path, selection_path, profile_path, treatment_path)
    return edit.assemble_plan(plan, audit, out, render)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--references-list', required=True); p.add_argument('--out', required=True)
    p = commands.add_parser('read'); p.add_argument('--study', required=True)
    p = commands.add_parser('distill')
    p.add_argument('--study', required=True); p.add_argument('--submission', required=True); p.add_argument('--out', required=True)
    p = commands.add_parser('inspect'); p.add_argument('--profile', required=True); p.add_argument('--verify-references', action='store_true')
    p = commands.add_parser('assemble')
    for key in ('task', 'selection', 'profile', 'treatment', 'out'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--render', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        result = prepare(args.references_list, args.out)
    elif args.command == 'read':
        result = read_study(args.study)
    elif args.command == 'distill':
        result = distill(args.study, args.submission, args.out)
    elif args.command == 'inspect':
        result = inspect(args.profile, verify_references=args.verify_references)
    else:
        result = assemble(args.task, args.selection, args.profile, args.treatment, args.out, args.render)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as error:
        import json
        print(json.dumps({'status': 'stopped', 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(2)
