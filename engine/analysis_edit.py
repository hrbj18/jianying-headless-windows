"""Compile reviewed source evidence into the existing native Jianying workflow."""
from __future__ import annotations

import math
from pathlib import Path
import re
import unicodedata

import analysis_store as store
import material_analysis as analysis
import media_evidence as media


def _normalized_speech(text):
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P'))


def _sentence_breaks(unit):
    """Map punctuation to existing full-unit word tails, never character clocks.

    Provider sentence text and words can differ. In that case only real pauses
    and reaction tokens are used. Cuts never renormalize a partial sentence.
    """
    words = unit['words']; sentence = unit['text']
    if _normalized_speech(sentence) != _normalized_speech(''.join(x['text'] for x in words)):
        return set()
    tails, cursor = {}, 0
    for word in words:
        cursor += len(_normalized_speech(word['text']))
        tails[cursor] = round(word['end'] * 1e6)
    boundaries, cursor = set(), 0
    for i, character in enumerate(sentence):
        if character in ',，。.!！?？;；:：、…\n':
            # A decimal point or thousands separator is part of a number,
            # rather than a new speaker/phrase boundary.
            numeric = character in '.,，' and i > 0 and i + 1 < len(sentence) and sentence[i - 1].isdigit() and sentence[i + 1].isdigit()
            if not numeric and cursor in tails:
                boundaries.add(tails[cursor])
        cursor += len(_normalized_speech(character))
    return boundaries


def _laughter(word):
    return (bool(re.fullmatch(r'[哈呵嘿嘻]{2,}', _normalized_speech(word['text']))) or
            word['text'].strip() in {'[笑声]', '（笑声）', '(笑声)', '[laughter]'})


def _pack_subtitle_words(words, limit):
    # Providers may timestamp "500" as "50" + "0". Keep adjacent numeric
    # pieces together before wrapping, retaining the first/last real clock.
    atomic = []
    for word in words:
        text = word['text']
        numeric = text and all(c in '0123456789.,%' for c in text)
        if numeric and atomic and atomic[-1]['text'] and all(c in '0123456789.,%' for c in atomic[-1]['text']):
            atomic[-1] = {**atomic[-1], 'end': word['end'], 'text': atomic[-1]['text'] + text}
        else:
            atomic.append(dict(word))
    groups, group, length = [], [], 0
    for word in atomic:
        if group and length + len(word['text']) > limit:
            groups.append(group); group, length = [], 0
        group.append(word); length += len(word['text'])
    if group:
        groups.append(group)
    # If a character-budget wrap strands a very short suffix, move one whole
    # real timed token from the previous cue. Never split a token or invent a
    # per-character time to obtain a nominal minimum duration.
    for i in range(1, len(groups)):
        while groups[i][-1]['end'] - groups[i][0]['start'] < .3 - 1e-8 and len(groups[i - 1]) > 1:
            moved = groups[i - 1][-1]
            if sum(len(x['text']) for x in groups[i]) + len(moved['text']) > limit:
                break
            if groups[i - 1][-2]['end'] - groups[i - 1][0]['start'] < .3 - 1e-8:
                break
            groups[i - 1].pop(); groups[i].insert(0, moved)
    return groups


def _subtitle_groups(words, limit=20, *, break_after=None):
    """Respect observed pauses, mapped clause boundaries and reaction words."""
    break_after = break_after or set()
    blocks, current = [], []
    boundary_is_hard = False
    for word in words:
        if current:
            previous = current[-1]
            hard = (word['start'] - previous['end'] >= .28 - 1e-8 or
                    _laughter(word) != _laughter(previous))
            punctuation = round(previous['end'] * 1e6) in break_after
            if hard or punctuation:
                blocks.append({'words': current, 'hard_before': boundary_is_hard})
                current, boundary_is_hard = [], hard
        current.append(dict(word))
    if current:
        blocks.append({'words': current, 'hard_before': boundary_is_hard})
    # Merge only short punctuation fragments across soft boundaries. A real
    # pause or isolated laugh remains a boundary even when the text is short.
    i = 0
    while i < len(blocks):
        block = blocks[i]; group = block['words']
        # A genuine brief multi-character reply remains its own turn (e.g.
        # "是不是啊" in .28s followed by another person's "谢谢"). Only a
        # stranded one-character punctuation fragment may join its neighbor.
        short = (group[-1]['end'] - group[0]['start'] < .3 - 1e-8 and
                 len(_normalized_speech(''.join(x['text'] for x in group))) <= 1)
        if short and i + 1 < len(blocks) and not blocks[i + 1]['hard_before']:
            following = blocks[i + 1]
            if sum(len(x['text']) for x in group + following['words']) <= limit:
                following['words'] = group + following['words']; following['hard_before'] = block['hard_before']
                blocks.pop(i); continue
        if short and i > 0 and not block['hard_before']:
            preceding = blocks[i - 1]
            if sum(len(x['text']) for x in preceding['words'] + group) <= limit:
                preceding['words'] += group; blocks.pop(i); continue
        i += 1
    return [group for block in blocks for group in _pack_subtitle_words(block['words'], limit)]


def _reviewed_word_replacements(words, replacements):
    """Replace same-length reviewed names on the original whole-word span.

    A replacement spanning several provider words becomes one indivisible
    cue token with their outer start/end. No character timestamps are inferred.
    """
    words = [dict(x) for x in words]
    for correction in replacements:
        joined = ''.join(x['text'] for x in words)
        before, after = correction['from'], correction['to']
        store.require(joined.count(before) == 1, 'Reviewed subtitle correction must match exactly once in the selected ASR unit')
        begin = joined.index(before); finish = begin + len(before)
        cursor, indices = 0, []
        for i, word in enumerate(words):
            end = cursor + len(word['text'])
            if cursor < finish and end > begin:
                indices.append((i, cursor, end))
            cursor = end
        first, last = indices[0][0], indices[-1][0]
        replacement = {'start': words[first]['start'], 'end': words[last]['end'],
                       'text': joined[indices[0][1]:begin] + after + joined[finish:indices[-1][2]]}
        words[first:last + 1] = [replacement]
    return words


def compile_selection(task_path, selection_path, *, subtitle_max_chars=20, subtitle_replacements=None,
                      subtitle_omissions=None):
    store.require(type(subtitle_max_chars) is int and 2 <= subtitle_max_chars <= 32,
                  'Subtitle wrapping needs an integer character budget in 2..32')
    path, task, evidence, transcript, review = analysis.reviewed(task_path)
    corrections = subtitle_replacements if subtitle_replacements is not None else []
    omissions = subtitle_omissions if subtitle_omissions is not None else []
    store.require(isinstance(corrections, list) and len(corrections) <= 100
                  and isinstance(omissions, list) and len(omissions) <= 100, 'Invalid explicit subtitle review declarations')
    units_by_id = {x['id']: x for x in transcript['segments']}
    for row in corrections:
        store.require(isinstance(row, dict) and set(row) == {'from', 'to', 'asr_ids', 'reason'}
                      and isinstance(row['asr_ids'], list) and row['asr_ids']
                      and all(isinstance(x, str) for x in row['asr_ids'])
                      and len(row['asr_ids']) == len(set(row['asr_ids']))
                      and all(x in units_by_id for x in row['asr_ids']), 'Subtitle correction needs actual unique source ASR IDs')
        store.require(all(isinstance(row[x], str) and row[x].strip() for x in ('from', 'to', 'reason'))
                      and row['from'] != row['to'] and len(row['from']) == len(row['to']) <= 50
                      and len(row['reason']) <= 4000
                      and re.findall(r'[0-9]+', row['from']) == re.findall(r'[0-9]+', row['to']),
                      'Subtitle corrections require same-length reviewed text without changing numeric claims')
    omitted = {}
    for row in omissions:
        store.require(isinstance(row, dict) and set(row) == {'asr_ids', 'reason'}
                      and isinstance(row['reason'], str) and 0 < len(row['reason'].strip()) <= 4000
                      and isinstance(row['asr_ids'], list) and row['asr_ids']
                      and all(isinstance(x, str) for x in row['asr_ids'])
                      and len(row['asr_ids']) == len(set(row['asr_ids']))
                      and all(x in units_by_id and x not in omitted for x in row['asr_ids']),
                      'Subtitle omissions need actual unique source ASR IDs and a review reason')
        omitted.update({unit_id: row['reason'] for unit_id in row['asr_ids']})
    store.require(not set(omitted) & {unit_id for row in corrections for unit_id in row['asr_ids']},
                  'An ASR unit cannot be both corrected and omitted')
    used_omissions = set()
    used_corrections = set()
    store.verify_source(task['request']['source'], full=True)
    selection = store.read(selection_path)
    store.require(isinstance(selection, dict) and set(selection) == {'task_id', 'review_sha256', 'subtitles', 'clips'}
                  and selection['task_id'] == task['id'] and selection['review_sha256'] == review['submission_sha256']
                  and type(selection['subtitles']) is bool, 'Selection does not bind the current reviewed analysis')
    clips = selection['clips']
    store.require(not (corrections or omissions) or selection['subtitles'],
                  'Explicit subtitle edits require enabled source subtitles')
    store.require(isinstance(clips, list) and 1 <= len(clips) <= 100, 'Select 1..100 candidate intervals')
    candidates = {x['id']: x for x in review['submission']['candidates']}
    fps, cursor, video, subtitles, audit = 30, 0, [], [], []
    for clip in clips:
        store.require(isinstance(clip, dict) and set(clip) == {'candidate_id', 'start', 'end', 'detail_index',
                      'reviewed_detail_sheet_ids', 'audio_review'}, 'Invalid selected clip fields')
        candidate = candidates.get(clip['candidate_id'])
        store.require(candidate, 'Selection references an unreviewed candidate')
        start, end = clip['start'], clip['end']
        store.number(start, candidate['start'], candidate['end'] - .1, 'cut start')
        store.number(end, start + .1, candidate['end'], 'cut end')
        detail_path = Path(clip['detail_index'])
        if not detail_path.is_absolute():
            detail_path = path.parent / detail_path
        store.require(detail_path.resolve().is_relative_to(path.parent / 'details'), 'Detail evidence must belong to this task')
        detail = store.read(store.owned_file(path.parent, str(detail_path.relative_to(path.parent))))
        media.verify_evidence(detail_path.parent, detail)
        store.require(detail['candidate_id'] == candidate['id'] and detail['source_sha256'] == task['request']['source']['sha256']
                      and detail['start'] <= start < end <= detail['end'], 'Detail evidence does not cover the selected cut')
        reviewed = clip['reviewed_detail_sheet_ids']
        expected = {x['id'] for x in detail['sheets']}
        store.require(isinstance(reviewed, list) and len(reviewed) == len(expected) and set(reviewed) == expected,
                      'Declare all actually reviewed detail contact sheets')
        audio_review = clip['audio_review']
        store.require(audio_review in {'asr-timing', 'playback', 'silent-source'}, 'Specify the actual audio review method')
        if evidence['media']['audio']:
            store.require(audio_review != 'silent-source', 'An audio stream cannot be declared absent')
        if audio_review == 'asr-timing':
            speech = [x for x in transcript['segments'] if x['id'] in candidate['asr_ids']
                      and x['start'] < end and x['end'] > start]
            store.require(speech, 'ASR timing review requires real overlapping speech evidence')
        # The final cut is inside the reviewed interval and aligned to the
        # output frame grid. Source and target durations retain forward 1x.
        first, last = math.ceil(start * fps - 1e-8), math.floor(end * fps + 1e-8)
        store.require(last > first, 'Selected interval is shorter than a complete output frame')
        a, b = round(first * 1_000_000 / fps), round(last * 1_000_000 / fps)
        span = b - a
        video.append({'source': task['request']['source']['path'], 'source_start_us': a,
                      'source_duration_us': span, 'start_us': cursor, 'duration_us': span, 'speed': 1, 'volume': 1})
        cue_ids = []
        cut_omissions = []
        if selection['subtitles']:
            for unit in transcript['segments']:
                if unit['start'] * 1e6 >= b or unit['end'] * 1e6 <= a:
                    continue
                if unit['id'] in omitted:
                    used_omissions.add(unit['id']); cut_omissions.append(unit['id'])
                    continue
                words = [w for w in unit['words'] if a <= round(w['start'] * 1e6) and round(w['end'] * 1e6) <= b]
                applicable = [(i, row) for i, row in enumerate(corrections) if unit['id'] in row['asr_ids']]
                if applicable:
                    store.require(words, 'Subtitle correction requires source word timestamps')
                    words = _reviewed_word_replacements(words, [row for _, row in applicable])
                    used_corrections.update((i, unit['id']) for i, _ in applicable)
                groups = _subtitle_groups(words, subtitle_max_chars, break_after=_sentence_breaks(unit))
                fallback_limit = 32 if subtitle_max_chars == 20 else subtitle_max_chars
                if not groups and a <= round(unit['start'] * 1e6) and round(unit['end'] * 1e6) <= b and len(unit['text']) <= fallback_limit:
                    groups = [[{'start': unit['start'], 'end': unit['end'], 'text': unit['text']}]]
                for group in groups:
                    begin, finish = round(group[0]['start'] * 1e6), round(group[-1]['end'] * 1e6)
                    begin = max(begin, a, a + (subtitles[-1]['start_us'] + subtitles[-1]['duration_us'] - cursor)
                                if subtitles else a)
                    text = ''.join(w['text'] for w in group).strip()
                    if finish > begin and text:
                        subtitles.append({'text': text, 'start_us': cursor + begin - a, 'duration_us': finish - begin,
                                          'size': 6, 'y': -.74, 'color': '#FFFFFF', 'border_color': '#000000', 'border_width': .05})
                        cue_ids.append(unit['id'])
        audit.append({'candidate_id': candidate['id'], 'requested_range': [start, end], 'source_range_us': [a, b],
                      'target_start_us': cursor, 'detail_index_sha256': store.digest_file(detail_path),
                      'evidence_cells': candidate['evidence_cell_ids'], 'asr_ids': candidate['asr_ids'],
                      'subtitle_asr_ids': sorted(set(cue_ids)), 'audio_review': audio_review})
        if omissions:
            audit[-1]['omitted_subtitle_asr_ids'] = cut_omissions
        cursor += span
    key = store.identity(selection)
    expected_corrections = {(i, unit_id) for i, row in enumerate(corrections) for unit_id in row['asr_ids']}
    store.require(used_corrections == expected_corrections, 'Subtitle correction references no selected source ASR unit')
    store.require(used_omissions == set(omitted), 'Subtitle omission references no selected source ASR unit')
    plan = {'schema': 'jy14-headless-plan/v1', 'name': 'analysis-' + task['id'][:10] + '-' + key[:8],
            'canvas': {'width': evidence['media']['width'], 'height': evidence['media']['height'], 'fps': fps},
            'tracks': [{'type': 'video', 'name': 'Reviewed original source intervals', 'segments': video}]}
    if subtitles:
        plan['tracks'].append({'type': 'text', 'name': 'Source ASR word clock', 'segments': subtitles})
    report = {'schema': 'jy-analysis-selection-audit/v1', 'task_id': task['id'], 'selection_sha256': key,
                  'review_sha256': review['submission_sha256'], 'source_sha256': task['request']['source']['sha256'],
                  'cuts': audit, 'source_audio_preserved': True, 'speech_time_stretched': False,
                  'subtitle_count': len(subtitles), 'duration_us': cursor}
    if omissions:
        report['subtitle_omissions'] = [{'asr_id': unit_id, 'source_range_seconds': [units_by_id[unit_id]['start'],
                                        units_by_id[unit_id]['end']], 'reason': reason}
                                       for unit_id, reason in omitted.items()]
    if corrections:
        report['subtitle_replacements'] = {'declarations': corrections,
            'clock_policy': 'Same-length text, unchanged digits, original enclosing word span; no invented character timestamps'}
    return plan, report


def assemble(task_path, selection_path, out, render=False):
    plan, audit = compile_selection(task_path, selection_path)
    return assemble_plan(plan, audit, out, render)


def assemble_plan(plan, audit, out, render=False):
    """Build a reviewed native plan with the same immutable export checkpoints."""
    from jy14_headless import build, verify_build
    out = analysis._folder(out)
    source = Path(plan['tracks'][0]['segments'][0]['source'])
    store.require(not source.is_relative_to(out), 'Assembly output cannot contain its source')
    out.mkdir(parents=True, exist_ok=True)
    with store.lock(out):
        record_path = out / 'assembly.json'
        if record_path.exists():
            report = store.read(record_path)
            store.require(report['selection_sha256'] == audit['selection_sha256']
                          and report['task_id'] == audit['task_id'] and report['plan_sha256'] == store.identity(plan),
                          'Assembly output belongs to a different immutable selection')
        else:
            store.require(set(p.name for p in out.iterdir()) <= {'.analysis.lock'}, 'Assembly output is not empty')
            store.save(out / 'edit.plan.json', plan); store.save(out / 'selection-audit.json', audit)
            report = {'schema': 'jy-analysis-assembly/v1', 'task_id': audit['task_id'],
                      'selection_sha256': audit['selection_sha256'], 'plan_sha256': store.identity(plan),
                      'status': 'building', 'build': str(out / 'build'), 'native_export': None,
                      'preview': None, 'mouse_keyboard_used': False, 'live_draft_written': False}
            store.save(record_path, report)
        try:
            store.require(store.read(store.owned_file(out, 'edit.plan.json')) == plan
                          and store.read(store.owned_file(out, 'selection-audit.json')) == audit,
                          'Saved assembly plan or audit changed')
            if (out / 'build/build.json').exists():
                verify_build(out / 'build')
            else:
                store.require(not (out / 'build').exists(), 'Partial build retained; inspect it and use a fresh assembly output')
                build(out / 'edit.plan.json', out / 'build')
            report['status'] = 'built-and-verified'
            store.save(record_path, report)
            if render:
                import windows_native_preview as preview
                import native_export
                preview_dir, export_dir = out / 'preview', out / 'export'
                if (preview_dir / 'preview.json').exists():
                    result = store.read(preview_dir / 'preview.json')
                    store.require(result['status'] == 'native-frames-captured', 'Previous preview failed; inspect retained evidence')
                    for row in result['frames']:
                        file = Path(row['png'])
                        store.require(file.resolve().is_relative_to(preview_dir), 'Cached native frame is outside its job')
                        store.require(store.digest_file(file) == row['png_sha256'], 'Cached native frame changed')
                else:
                    positions = [round((row['start_us'] + row['duration_us'] / 2) / 1e6, 6)
                                 for row in plan['tracks'][0]['segments']][:16]
                    result = preview.run(preview_dir, positions, width=640, build=out / 'build')
                store.require(result['status'] == 'native-frames-captured' and result['source_unchanged']
                              and not result['export_used'], 'Native preview failed')
                report['preview'] = str(preview_dir / 'preview.json'); store.save(record_path, report)
                if (export_dir / 'result.json').exists():
                    result = store.read(export_dir / 'result.json')
                    output = Path(result['output'])
                    store.require(output.resolve().is_relative_to(export_dir) and not output.is_symlink()
                                  and result['status'] == 'encoded-and-decoded'
                                  and store.digest_file(output) == result['output_sha256'],
                                  'Previous export failed or changed; preserve it and use a fresh assembly output')
                else:
                    result = native_export.run(out / 'build', export_dir)
                store.require(result['status'] == 'encoded-and-decoded' and result['full_decode_passed'], 'Native export failed')
                report.update(status='assembled-and-rendered', native_export=str(export_dir / 'result.json'),
                              output=result['output'], output_sha256=result['output_sha256'])
            report['error'] = None
        except Exception as error:
            report.update(status='incomplete', error=str(error))
            raise
        finally:
            store.save(record_path, report)
    return report
