"""Compile an agent-reviewed story treatment into an undecorated native plan.

The compiler checks provenance and clocks, not whether a story is good. Word
ranges are zero-based and half-open. Source and target edits use a 30 fps grid;
the original ASR word times remain in the audit, including rounding deltas.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from analysis_edit import _sentence_breaks, _subtitle_groups
import analysis_store as store


SCHEMA = 'jy-story-treatment/v1'
FPS = 30
_HALF_FRAME = .5 / FPS
_EPSILON = 1e-8
_MOTIVES = {'role', 'new_information', 'expectation', 'payoff', 'why_kept'}
_RETENTION_KINDS = {'dialogue', 'action', 'reaction', 'hold', 'bridge'}
_REVIEW_STAGES = ('clean_rough_cut', 'packaged_export')
_REVIEW_METHODS = {'sampled_frames', 'continuous_playback', 'subjective_listening', 'signal_analysis'}
_SUBTITLE_DEFAULTS = {'size': 6, 'y': -.74, 'color': '#FFFFFF',
                      'border_color': '#000000', 'border_width': .05}


def _fields(value, required, optional, label):
    store.require(isinstance(value, dict) and required <= set(value)
                  and set(value) <= required | optional, label + ' has missing or unsupported fields')


def _text(value, label):
    store.require(isinstance(value, str) and 0 < len(value.strip()) <= 8000,
                  label + ' must be nonempty text')
    return value


def _integer(value, minimum, label):
    store.require(type(value) is int and value >= minimum, label + ' must be an integer >= ' + str(minimum))
    return value


def _frame(seconds):
    return math.floor(seconds * FPS + .5 + _EPSILON)


def _us(frame):
    return round(frame * 1_000_000 / FPS)


def _bound_file(value, base, label):
    _fields(value, {'path', 'sha256'}, set(), label)
    _text(value['path'], label + ' path')
    store.require(isinstance(value['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', value['sha256']),
                  label + ' requires a lowercase SHA256')
    path = Path(value['path']).expanduser()
    if not path.is_absolute():
        path = base / path
    record = store.file_record(path)
    store.require(record['size'] > 0 and record['sha256'] == value['sha256'], label + ' SHA256 changed')
    return record


def _transcript(value, source_hash):
    store.require(isinstance(value, dict) and value.get('schema') == 'jy-material-transcript/v1'
                  and value.get('source_sha256') == source_hash,
                  'Transcript must bind the verified source SHA256')
    store.require(value.get('timestamp_unit') in {'source seconds', 'seconds'},
                  'Transcript requires source-second word timestamps')
    units = value.get('segments')
    store.require(isinstance(units, list) and units, 'Transcript requires actual ASR segments')
    by_id, all_words = {}, []
    for unit in units:
        store.require(isinstance(unit, dict), 'Invalid source ASR unit')
        unit_id = _text(unit.get('id'), 'ASR ID')
        store.require(unit_id not in by_id, 'Duplicate source ASR ID')
        _text(unit.get('text'), 'ASR text')
        start = store.number(unit.get('start'), 0, 1e9, 'ASR start')
        end = store.number(unit.get('end'), start, 1e9, 'ASR end')
        words = unit.get('words')
        store.require(isinstance(words, list) and words, 'ASR words and their real clocks are required')
        previous = start
        for index, word in enumerate(words):
            store.require(isinstance(word, dict), 'Invalid source ASR word')
            # Providers also time spaces between English tokens. Preserve
            # those bytes and original indices rather than rewriting speech.
            store.require(isinstance(word.get('text'), str) and 0 < len(word['text']) <= 8000,
                          'ASR word text must be a nonempty string')
            a = store.number(word.get('start'), start, end, 'word start')
            b = store.number(word.get('end'), a, end, 'word end')
            store.require(b > a and a >= previous - _EPSILON, 'ASR words must have positive ordered clocks')
            previous = b
            all_words.append((unit_id, index, word))
        by_id[unit_id] = unit
    return by_id, all_words


def _omissions(rows, units):
    store.require(isinstance(rows, list) and len(rows) <= 1000, 'omissions must be a list')
    result = {}
    for index, row in enumerate(rows):
        _fields(row, {'asr_id', 'word_start', 'word_end', 'reason'}, set(), 'Subtitle omission')
        unit = units.get(row['asr_id']) if isinstance(row['asr_id'], str) else None
        store.require(unit is not None, 'Subtitle omission requires an actual ASR ID')
        a = _integer(row['word_start'], 0, 'omission word_start')
        b = _integer(row['word_end'], a + 1, 'omission word_end')
        store.require(b <= len(unit['words']), 'Subtitle omission exceeds the ASR word range')
        _text(row['reason'], 'omission reason')
        for word_index in range(a, b):
            key = (row['asr_id'], word_index)
            store.require(key not in result, 'Subtitle omission word ranges overlap')
            result[key] = index
    return result


def _cut_is_whole(frame, words):
    cut = frame / FPS
    for asr_id, index, word in words:
        if not word['text'].strip():
            continue  # A provider's timed formatting space is not a spoken word.
        a, b = word['start'], word['end']
        if a + _EPSILON < cut < b - _EPSILON:
            store.require(min(cut - a, b - cut) <= _HALF_FRAME + _EPSILON,
                          f'Cut frame {frame} is inside ASR word {asr_id}[{index}]')


def _selected(word, first, last):
    # A tolerated near-edge cut belongs to the side containing the word's
    # midpoint, so adjacent clips cannot duplicate a very short source token.
    a, b = first / FPS, last / FPS
    middle = (word['start'] + word['end']) / 2
    return (a <= middle < b and word['start'] >= a - _HALF_FRAME - _EPSILON
            and word['end'] <= b + _HALF_FRAME + _EPSILON)


def _word_record(unit_id, index, word):
    return {'asr_id': unit_id, 'word_index': index, 'text': word['text'],
            'source_start_seconds': word['start'], 'source_end_seconds': word['end']}


def _subtitle_style(treatment, base):
    """Allow readable static captions while preserving ASR text and timing."""
    style = treatment.get('subtitle_style', {})
    _fields(style, set(), {'size', 'x', 'y', 'color', 'border_color', 'border_width', 'font_path'},
            'Subtitle style')
    result, font = {**_SUBTITLE_DEFAULTS, **style}, None
    for key, low, high in [('size', 1, 100), ('x', -1, 1), ('y', -1, 1), ('border_width', 0, 1)]:
        if key in result:
            store.number(result[key], low, high, 'Subtitle style ' + key)
    for key in ('color', 'border_color'):
        store.require(isinstance(result[key], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', result[key]),
                      'Subtitle style colors must use #RRGGBB')
    if 'font_path' in style:
        provided = Path(_text(style['font_path'], 'Subtitle font_path'))
        path = provided.expanduser()
        # Keep an explicit absolute spelling stable for exact native-plan comparisons.
        if not provided.is_absolute():
            if not path.is_absolute():
                path = base / path
            result['font_path'] = str(path.resolve())
        font = store.file_record(path)
        store.require(font['size'] > 0, 'Subtitle font must not be empty')
    return result, font


def _editorial_contract(treatment, clips):
    """Validate declared event membership and coverage, not the truth of a theme."""
    theme = treatment.get('theme')
    has_contributions = any('contribution' in clip for clip in clips)
    if theme is None:
        store.require('theme' not in treatment and not has_contributions and 'retention_review' not in treatment,
                      'contribution and retention_review require a theme')
        return None
    _fields(theme, {'statement', 'viewer_question', 'payoff', 'events'}, set(), 'Theme')
    for key in ('statement', 'viewer_question', 'payoff'):
        _text(theme[key], 'Theme ' + key)
    events = theme['events']
    store.require(isinstance(events, list) and 1 <= len(events) <= 1000, 'Theme requires 1..1000 events')
    by_event = {}
    for event in events:
        _fields(event, {'id', 'source_start_frame', 'source_end_frame', 'observation', 'supports_theme'},
                set(), 'Theme event')
        identifier = _text(event['id'], 'Event ID')
        store.require(identifier not in by_event, 'Duplicate theme event ID')
        first = _integer(event['source_start_frame'], 0, 'event source_start_frame')
        _integer(event['source_end_frame'], first + 1, 'event source_end_frame')
        for key in ('observation', 'supports_theme'):
            _text(event[key], 'Event ' + key)
        by_event[identifier] = event
    used, by_clip, contributions = set(), {}, []
    cursor = 0
    for index, clip in enumerate(clips):
        identifier = clip.get('id', f'STORY-{index + 1:04d}')
        contribution = clip.get('contribution')
        _fields(contribution, {'event_id', 'theme_link', 'focus', 'remove_cost'}, set(), 'Segment contribution')
        for key in contribution:
            _text(contribution[key], 'Contribution ' + key)
        event = by_event.get(contribution['event_id'])
        store.require(event is not None, 'Contribution requires a declared theme event')
        first, last = clip['source_start_frame'], clip['source_end_frame']
        store.require(event['source_start_frame'] <= first < last <= event['source_end_frame'],
                      'Story segment must lie inside its declared source event')
        used.add(contribution['event_id'])
        by_clip[identifier] = (clip, cursor)
        contributions.append({'segment_id': identifier, **contribution,
                              'source_range_frames': [first, last],
                              'target_range_frames': [cursor, cursor + last - first]})
        cursor += last - first
    store.require(used == set(by_event), 'Every theme event must contribute retained footage')
    result = {'theme': theme, 'contributions': contributions,
              'evidence_limit': 'Event observations, theme support and retention motives are agent declarations; '
                                'valid bounds do not establish semantic truth, speaker identity or quality.',
              'retention_review': {'status': 'not-provided', 'spans': []}}
    if 'retention_review' not in treatment:
        return result
    review = treatment['retention_review']
    _fields(review, {'spans'}, {'reviews'}, 'Retention review')
    spans = review['spans']
    store.require(isinstance(spans, list) and 1 <= len(spans) <= 10000,
                  'Retention review requires 1..10000 spans')
    grouped = {identifier: [] for identifier in by_clip}
    for span in spans:
        _fields(span, {'segment_id', 'source_start_frame', 'source_end_frame', 'kind',
                       'focus', 'why_kept', 'delete_cost'}, set(), 'Retention span')
        identifier = _text(span['segment_id'], 'Retention segment ID')
        store.require(identifier in by_clip, 'Retention span requires a retained segment ID')
        store.require(isinstance(span['kind'], str) and span['kind'] in _RETENTION_KINDS,
                      'Retention kind must be dialogue, action, reaction, hold or bridge')
        for key in ('focus', 'why_kept', 'delete_cost'):
            _text(span[key], 'Retention ' + key)
        first = _integer(span['source_start_frame'], 0, 'retention source_start_frame')
        last = _integer(span['source_end_frame'], first + 1, 'retention source_end_frame')
        clip, target = by_clip[identifier]
        store.require(clip['source_start_frame'] <= first < last <= clip['source_end_frame'],
                      'Retention span must lie inside its retained segment')
        begin = target + first - clip['source_start_frame']
        end = begin + last - first
        grouped[identifier].append({**span, 'event_id': clip['contribution']['event_id'],
            'source_range_frames': [first, last], 'target_range_frames': [begin, end],
            'source_range_us': [_us(first), _us(last)], 'target_range_us': [_us(begin), _us(end)],
            'review_target_frames': sorted({begin, (begin + end - 1) // 2, end - 1})})
    mapped = []
    for identifier, (clip, _) in by_clip.items():
        cursor = clip['source_start_frame']
        for span in grouped[identifier]:
            store.require(span['source_start_frame'] == cursor,
                          'Retention spans must continuously cover each segment in source order without gaps or overlaps')
            cursor = span['source_end_frame']
            mapped.append(span)
        store.require(cursor == clip['source_end_frame'],
                      'Retention spans must cover every retained frame of every segment')
    result['retention_review'] = {'status': 'declared-coverage-validated', 'spans': mapped}
    return result


def _review_evidence(treatment, base, plan):
    """Check immutable stage evidence without promoting declarations to aesthetic approval."""
    rows = treatment.get('retention_review', {}).get('reviews', [])
    store.require(isinstance(rows, list) and len(rows) <= 2, 'Stage reviews must be a list of at most two records')
    result, seen = [], set()
    for row in rows:
        _fields(row, {'stage', 'plan', 'export', 'report'}, set(), 'Stage review')
        stage = row['stage']
        store.require(isinstance(stage, str) and stage in _REVIEW_STAGES and stage not in seen,
                      'Stage review requires a unique clean_rough_cut or packaged_export stage')
        if stage == 'packaged_export':
            store.require(result and result[0]['stage'] == 'clean_rough_cut'
                          and result[0]['declared_decision'] == 'accepted_for_scope',
                          'Packaged review requires the accepted clean rough-cut review first')
        plan_record = _bound_file(row['plan'], base, 'Review plan')
        export_record = _bound_file(row['export'], base, 'Review export')
        report_record = _bound_file(row['report'], base, 'Review report')
        reviewed_plan = store.read(plan_record['path'])
        if stage == 'clean_rough_cut':
            store.require(store.identity(reviewed_plan) == store.identity(plan),
                          'Clean review plan does not match the current compiled story')
        else:
            store.require(isinstance(reviewed_plan, dict) and reviewed_plan.get('schema') == 'jy14-headless-plan/v1',
                          'Packaged review requires a native production plan')
        report = store.read(report_record['path'])
        _fields(report, {'schema', 'stage', 'plan_sha256', 'export_sha256', 'decision',
                         'methods', 'findings', 'remaining_limits'}, {'rough_plan_sha256'}, 'Story review report')
        store.require(report['schema'] == 'jy-story-review/v1' and report['stage'] == stage
                      and report['plan_sha256'] == plan_record['sha256']
                      and report['export_sha256'] == export_record['sha256'],
                      'Story review report must bind the exact stage, plan and export SHA256')
        if stage == 'packaged_export':
            store.require(report.get('rough_plan_sha256') == result[0]['plan']['sha256'],
                          'Packaged review must bind the accepted rough plan SHA256')
        elif 'rough_plan_sha256' in report:
            store.require(report['rough_plan_sha256'] == plan_record['sha256'],
                          'Clean review rough_plan_sha256 must match its plan')
        store.require(isinstance(report['decision'], str)
                      and report['decision'] in {'revise', 'accepted_for_scope'},
                      'Story review decision must be revise or accepted_for_scope')
        methods = report['methods']
        store.require(isinstance(methods, list) and methods
                      and all(isinstance(method, str) and method in _REVIEW_METHODS for method in methods)
                      and len(set(methods)) == len(methods), 'Story review requires explicit, unique inspection methods')
        for key in ('findings', 'remaining_limits'):
            store.require(isinstance(report[key], list) and len(report[key]) <= 1000,
                          'Story review ' + key + ' must be a list')
            for value in report[key]:
                _text(value, 'Story review ' + key)
        if not {'continuous_playback', 'subjective_listening'} <= set(methods):
            store.require(report['remaining_limits'],
                          'A review without continuous playback and subjective listening must state its remaining limits')
        store.require(report['decision'] != 'revise' or report['findings'],
                      'A revise decision requires a finding')
        store.require(store.digest_file(plan_record['path']) == plan_record['sha256']
                      and store.digest_file(report_record['path']) == report_record['sha256'],
                      'Review plan or report changed during compilation')
        info = Path(export_record['path']).stat()
        store.require((info.st_size, info.st_mtime_ns) == (export_record['size'], export_record['mtime_ns']),
                      'Review export changed during compilation')
        result.append({'stage': stage, 'plan': plan_record, 'export': export_record, 'report': report_record,
                       'declared_decision': report['decision'], 'declared_methods': methods,
                       'findings': report['findings'], 'remaining_limits': report['remaining_limits'],
                       'status': 'hash-bindings-validated-not-aesthetic-certification'})
        seen.add(stage)
    return result


def compile_plan(treatment_path):
    """Return (native plan, audit), without writing or invoking a renderer."""
    treatment_path = store.regular(Path(treatment_path).absolute())
    treatment_record = store.file_record(treatment_path)
    treatment = store.read(treatment_path)
    _fields(treatment, {'schema', 'name', 'source', 'transcript', 'canvas', 'segments',
                       'promise', 'overlay_decisions', 'omissions'},
            {'subtitle_max_chars', 'subtitle_style', 'theme', 'retention_review'}, 'Story treatment')
    store.require(treatment['schema'] == SCHEMA, 'Unsupported story treatment schema')
    name = _text(treatment['name'], 'name')
    store.require(name.strip() == name and len(name.encode()) < 200 and name not in {'.', '..'}
                  and not name.startswith('.') and not any(c in name for c in '/\\\x00\n\r'),
                  'Story name must be a visible single directory component')
    _text(treatment['promise'], 'promise')
    canvas = treatment['canvas']
    _fields(canvas, {'width', 'height', 'fps'}, set(), 'Canvas')
    for key in ('width', 'height'):
        store.require(_integer(canvas[key], 16, key) <= 8192, 'Canvas dimension exceeds 8192')
    store.require(type(canvas['fps']) is int and canvas['fps'] == FPS, 'Story compilation requires 30 fps')
    limit = treatment.get('subtitle_max_chars', 20)
    store.require(type(limit) is int and 2 <= limit <= 32, 'subtitle_max_chars must be an integer in 2..32')
    subtitle_style, subtitle_font = _subtitle_style(treatment, treatment_path.parent)
    decisions = treatment['overlay_decisions']
    store.require(isinstance(decisions, list) and 1 <= len(decisions) <= 100,
                  'Explicit counterfactual overlay_decisions are required')
    for row in decisions:
        _fields(row, {'decision', 'added_information', 'attention_cost', 'delete_test'}, set(), 'Overlay decision')
        for key in row:
            _text(row[key], 'Overlay ' + key)
    clips = treatment['segments']
    store.require(isinstance(clips, list) and 1 <= len(clips) <= 1000, 'Story requires 1..1000 segments')
    # Validate narrative declarations before reading the potentially large source.
    identifiers, previous_start, selected_ranges = set(), None, []
    for index, clip in enumerate(clips):
        _fields(clip, {'source_start_frame', 'source_end_frame'} | _MOTIVES,
                {'id', 'reuse_reason', 'contribution'}, 'Story segment')
        for key in _MOTIVES:
            _text(clip[key], 'Segment ' + key)
        identifier = clip.get('id', f'STORY-{index + 1:04d}')
        _text(identifier, 'segment ID')
        store.require(identifier not in identifiers, 'Duplicate story segment ID')
        identifiers.add(identifier)
        first = _integer(clip['source_start_frame'], 0, 'source_start_frame')
        last = _integer(clip['source_end_frame'], first + 1, 'source_end_frame')
        overlaps = any(first < b and last > a for a, b in selected_ranges)
        reordered = previous_start is not None and first < previous_start
        if overlaps or reordered:
            _text(clip.get('reuse_reason'), 'Reordered or repeated source requires reuse_reason')
        elif 'reuse_reason' in clip:
            _text(clip['reuse_reason'], 'reuse_reason')
        selected_ranges.append((first, last))
        previous_start = first
    editorial = _editorial_contract(treatment, clips)
    source = _bound_file(treatment['source'], treatment_path.parent, 'Source')
    transcript_record = _bound_file(treatment['transcript'], treatment_path.parent, 'Transcript')
    transcript = store.read(transcript_record['path'])
    units, words = _transcript(transcript, source['sha256'])
    omitted = _omissions(treatment['omissions'], units)
    used_omissions, selected_omitted = set(), set()
    video, subtitles, cuts, subtitle_audit, omitted_audit = [], [], [], [], []
    cursor = 0
    for index, clip in enumerate(clips):
        first, last = clip['source_start_frame'], clip['source_end_frame']
        _cut_is_whole(first, words)
        _cut_is_whole(last, words)
        target_end = cursor + last - first
        identifier = clip.get('id', f'STORY-{index + 1:04d}')
        a, b, target_a, target_b = _us(first), _us(last), _us(cursor), _us(target_end)
        video.append({'source': source['path'], 'source_start_us': a, 'source_duration_us': b - a,
                      'start_us': target_a, 'duration_us': target_b - target_a, 'speed': 1, 'volume': 1})
        cut = {'id': identifier, 'source_start_frame': first, 'source_end_frame': last,
               'target_start_frame': cursor, 'target_end_frame': target_end,
               'source_range_us': [a, b], 'target_range_us': [target_a, target_b],
               **{key: clip[key] for key in sorted(_MOTIVES)}, 'subtitle_indices': []}
        if 'reuse_reason' in clip:
            cut['reuse_reason'] = clip['reuse_reason']
        for unit_id, unit in units.items():
            runs, run = [], []
            for word_index, word in enumerate(unit['words']):
                included = _selected(word, first, last)
                key = (unit_id, word_index)
                if included and key in omitted:
                    used_omissions.add(omitted[key])
                    selected_omitted.add(key)
                    omitted_audit.append({'segment_id': identifier, 'omission_index': omitted[key],
                                          **_word_record(unit_id, word_index, word)})
                if included and key not in omitted:
                    run.append((word_index, word))
                elif run:
                    runs.append(run)
                    run = []
            if run:
                runs.append(run)
            for run in runs:
                groups = _subtitle_groups([word for _, word in run], limit,
                                          break_after=_sentence_breaks(unit))
                for group in groups:
                    # The shared packer can join provider-split numeric tokens.
                    # Recover all original indices from its enclosing real span.
                    originals = [(wi, w) for wi, w in run if w['start'] >= group[0]['start'] - _EPSILON
                                 and w['end'] <= group[-1]['end'] + _EPSILON]
                    text = ''.join(w['text'] for _, w in originals)
                    store.require(originals and text == ''.join(w['text'] for w in group),
                                  'Subtitle grouping changed source word text')
                    store.require(text.strip(), 'A whitespace-only ASR cue requires an explicit word-range omission')
                    source_first = max(first, _frame(originals[0][1]['start']))
                    source_last = min(last, _frame(originals[-1][1]['end']))
                    begin, finish = cursor + source_first - first, cursor + source_last - first
                    store.require(finish > begin, 'An ASR cue has no complete display frame; review its word range')
                    start_us, finish_us = _us(begin), _us(finish)
                    store.require(not subtitles or start_us >= subtitles[-1]['start_us'] + subtitles[-1]['duration_us'],
                                  'Overlapping source subtitle cues require an explicit word-range review')
                    cue_index = len(subtitles)
                    subtitles.append({'text': text, 'start_us': start_us, 'duration_us': finish_us - start_us,
                                      **subtitle_style})
                    cut['subtitle_indices'].append(cue_index)
                    original_start, original_end = originals[0][1]['start'], originals[-1][1]['end']
                    subtitle_audit.append({'subtitle_index': cue_index, 'segment_id': identifier,
                        'asr_id': unit_id, 'word_start': originals[0][0], 'word_end': originals[-1][0] + 1,
                        'text': text, 'source_asr_text': unit['text'],
                        'source_word_range_seconds': [original_start, original_end],
                        'source_display_range_frames': [source_first, source_last],
                        'target_range_frames': [begin, finish], 'target_range_us': [start_us, finish_us],
                        'rounding_delta_seconds': [source_first / FPS - original_start, source_last / FPS - original_end],
                        'words': [_word_record(unit_id, wi, w) for wi, w in originals]})
        cuts.append(cut)
        cursor = target_end
    store.require(used_omissions == set(range(len(treatment['omissions']))) and selected_omitted == set(omitted),
                  'Every declared omission word must occur in a selected source interval')
    # Check the bytes read as JSON against the initial fingerprint as well.
    store.require(store.digest_file(treatment_path) == treatment_record['sha256']
                  and store.digest_file(transcript_record['path']) == transcript_record['sha256'],
                  'Treatment or transcript changed during compilation')
    info = Path(source['path']).stat()
    store.require((info.st_size, info.st_mtime_ns) == (source['size'], source['mtime_ns']),
                  'Source changed during compilation')
    plan = {'schema': 'jy14-headless-plan/v1', 'name': name, 'canvas': dict(canvas),
            'tracks': [{'type': 'video', 'name': 'Story original source 1x', 'segments': video}]}
    if subtitles:
        plan['tracks'].append({'type': 'text', 'name': 'Unattributed original ASR words', 'segments': subtitles})
    stage_reviews = _review_evidence(treatment, treatment_path.parent, plan) if editorial is not None else []
    audit = {'schema': 'jy-story-compile-audit/v1', 'treatment': treatment_record,
             'treatment_sha256': treatment_record['sha256'], 'treatment_content_sha256': store.identity(treatment),
             'source': source, 'source_sha256': source['sha256'], 'transcript': transcript_record,
             'transcript_sha256': transcript_record['sha256'], 'promise': treatment['promise'],
             'fps': FPS, 'duration_frames': cursor, 'duration_us': _us(cursor), 'cuts': cuts,
             'subtitles': subtitle_audit, 'subtitle_count': len(subtitles),
             'omissions': treatment['omissions'], 'omitted_words': omitted_audit,
             'overlay_decisions': decisions, 'overlays_applied': [], 'source_audio_preserved': True,
             'speech_time_stretched': False, 'speaker_attribution_generated': False,
             'plan_content_sha256': store.identity(plan),
             'clock_policy': '30 fps source/target grid; whole ASR words; at most half-frame edge quantization; no character clocks',
             'review_status': 'requires-agent-audiovisual-and-story-review',
             'limits': ['Compilation validates provenance and execution clocks, not artistic quality.',
                        'ASR text and anonymous voices do not prove a visible speaker identity.',
                        'No media playback, native render, source-duration probe or aesthetic scoring was performed.']}
    if editorial is not None:
        audit['editorial_contract'] = {**editorial, 'stage_reviews': stage_reviews,
            'review_requirements': [
                {'stage': 'clean_rough_cut', 'plan_content_sha256': store.identity(plan),
                 'status': 'evidence-bound' if stage_reviews else 'pending',
                 'check': 'Review the full undecorated progression, every cut, all retained holds and the ending.'},
                {'stage': 'packaged_export',
                 'status': 'evidence-bound' if len(stage_reviews) == 2 else 'pending',
                 'check': 'Compare to the accepted rough cut; inspect emphasis entry/hold/exit, faces, hands, '
                          'action/reaction source clocks, readable text and sound.'}]}
    if 'subtitle_style' in treatment:
        if subtitle_font:
            store.verify_source(subtitle_font, full=True)
        audit['subtitle_style'] = {'resolved': subtitle_style, 'font': subtitle_font,
                                   'scope': 'Static ordinary ASR captions; no text, clock or animation changes.'}
    return plan, audit


def compile_treatment(treatment_path, out):
    """Write plan.json and audit.json to an exclusively new output directory."""
    out = Path(out).expanduser().absolute()
    store.require(not out.exists() and not out.is_symlink(), 'Story output must be a fresh directory')
    plan, audit = compile_plan(treatment_path)
    out.mkdir(parents=True, exist_ok=False)
    store.save(out / 'plan.json', plan)
    store.save(out / 'audit.json', audit)
    return {'schema': 'jy-story-compile-result/v1', 'status': 'compiled-for-agent-review',
            'plan': str(out / 'plan.json'), 'audit': str(out / 'audit.json'),
            'plan_sha256': store.digest_file(out / 'plan.json'), 'audit_sha256': store.digest_file(out / 'audit.json'),
            'duration_frames': audit['duration_frames'], 'duration_us': audit['duration_us'],
            'subtitle_count': audit['subtitle_count']}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    compile_command = commands.add_parser('compile', help='Compile a reviewed treatment without native rendering')
    compile_command.add_argument('--treatment', type=Path, required=True)
    compile_command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(arguments)
    result = compile_treatment(args.treatment, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
