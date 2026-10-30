"""Style interface checks use real immutable records and no paid model calls."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import analysis_store as store
import material_analysis as analysis
import media_evidence as media
import editing_style as style


class EditingStyle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-style-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'work'; self.root.mkdir()
        self.tasks = [self.make_task(i) for i in range(3)]
        self.ids = [store.read(x)['id'] for x in self.tasks]
        self.refs = self.root / 'references.json'
        store.save(self.refs, {'name': 'Offline reference style', 'tasks': [str(x) for x in self.tasks],
                               'holdout_task_ids': [self.ids[2]]})
        self.study = Path(style.prepare(self.refs, self.root / 'study')['study'])
        self.submission = {'study_id': store.read(self.study)['id'], 'version': 1, 'model': 'offline-test-reviewer',
            'summary': 'Fixture conditional rules, not a claimed real creator style.', 'unknowns': ['No source playback in this test'],
            'reviewed_sheets': [{'task_id': task_id, 'sheet_ids': ['S-1']} for task_id in self.ids],
            'rules': [{'id': 'RULE-1', 'dimension': 'subtitles', 'when': 'Speech carries the important explanation',
                       'action': 'Keep short source-clock subtitles', 'avoid': 'Do not invent unspoken claims',
                       'support': ['EX-1', 'EX-2'], 'parameters': {'subtitle_max_chars': [4, 10], 'video_scale': [1, 1.1]}}],
            'examples': [{'id': 'EX-' + str(i + 1), 'task_id': self.ids[i], 'start': 0, 'end': 4,
                          'cell_ids': ['S-1:R1C1'], 'asr_ids': ['ASR-1'],
                          'observation': 'Fixture word timing with a short numeric token'} for i in range(2)],
            'holdout_evaluations': [{'task_id': self.ids[2], 'observations': 'Same rule is inspectable on this unused fixture',
                                     'rule_ids': ['RULE-1'], 'cell_ids': ['S-1:R1C1'], 'asr_ids': ['ASR-1']}]}
        self.submission_path = self.root / 'distillation.json'; store.save(self.submission_path, self.submission)

    def make_task(self, i):
        folder = self.root / ('task-' + str(i)); folder.mkdir()
        source = self.root / ('source-' + str(i) + '.mp4'); source.write_bytes(b'fixture-source-' + bytes([i]))
        evidence_folder = folder / 'evidence'; evidence_folder.mkdir()
        (evidence_folder / 'frame.jpg').write_bytes(b'fixture-frame-' + bytes([i]))
        (evidence_folder / 'sheet.jpg').write_bytes(b'fixture-sheet-' + bytes([i]))
        frame = {'id': 'F1', 'file': 'frame.jpg', 'sha256': store.digest_file(evidence_folder / 'frame.jpg'),
                 'actual_seconds': 1, 'chapter_id': 'CH-1', 'selected': True}
        sheet = {'id': 'S-1', 'file': 'sheet.jpg', 'sha256': store.digest_file(evidence_folder / 'sheet.jpg'),
                 'chapter_id': 'CH-1'}
        evidence = {'schema': media.VERSION, 'source_sha256': store.digest_file(source),
                    'media': {'duration': 5, 'width': 720, 'height': 1520, 'audio': True},
                    'policy': {'whole_video_remote_default': True}, 'chapters': [{'id': 'CH-1', 'start': 0, 'end': 5}],
                    'frames': [frame], 'sheets': [sheet],
                    'cells': [{'id': 'S-1:R1C1', 'frame_id': 'F1', 'sheet_id': 'S-1', 'chapter_id': 'CH-1', 'actual_seconds': 1}]}
        store.save(evidence_folder / 'evidence.json', evidence)
        words = [{'text': '容量是', 'start': .3, 'end': 1}, {'text': '50', 'start': 1, 'end': 1.3},
                 {'text': '0', 'start': 1.3, 'end': 1.5}, {'text': '毫升', 'start': 1.5, 'end': 2},
                 {'text': '可以倒水', 'start': 2.1, 'end': 3}]
        transcript = {'segments': [{'id': 'ASR-1', 'start': .3, 'end': 3, 'text': '容量是500毫升可以倒水', 'words': words}]}
        store.save(folder / 'transcript.json', transcript)
        request = {'source': store.file_record(source), 'goal': 'Fixture selection', 'model': 'offline-test', 'asr': {'provider': 'fixture'}}
        task = {'schema': analysis.SCHEMA, 'id': store.identity(request), 'request': request, 'status': 'review-ready',
                'evidence_sha256': store.digest_file(evidence_folder / 'evidence.json'),
                'transcript_sha256': store.digest_file(folder / 'transcript.json')}
        store.save(folder / 'task.json', task)
        return folder / 'task.json'

    def profile(self):
        return Path(style.distill(self.study, self.submission_path, self.root / 'profile')['profile'])

    def selected(self):
        folder = self.tasks[0].parent
        submission = {'task_id': self.ids[0], 'model': 'offline-test', 'reviewed_sheet_ids': ['S-1'],
                      'summary': 'Fixture original source selection', 'unknowns': [],
                      'candidates': [{'id': 'C1', 'start': 0, 'end': 4, 'reason': 'Fixture complete sentence',
                                      'evidence_cell_ids': ['S-1:R1C1'], 'asr_ids': ['ASR-1']}]}
        path = folder / 'review-submission.json'; store.save(path, submission); analysis.submit(self.tasks[0], path)
        index = store.read(folder / 'evidence/evidence.json')
        detail = folder / 'details/D1'; detail.mkdir(parents=True)
        for name in ('frame.jpg', 'sheet.jpg'):
            (detail / name).write_bytes((folder / 'evidence' / name).read_bytes())
        index.update(candidate_id='C1', start=0, end=4)
        store.save(detail / 'evidence.json', index)
        selection = {'task_id': self.ids[0], 'review_sha256': store.read(folder / 'review.json')['submission_sha256'],
                     'subtitles': True, 'clips': [{'candidate_id': 'C1', 'start': 0, 'end': 4,
                     'detail_index': str(detail / 'evidence.json'), 'reviewed_detail_sheet_ids': ['S-1'], 'audio_review': 'asr-timing'}]}
        path = folder / 'selection.json'; store.save(path, selection)
        return path

    def treatment(self, profile):
        text = {'size': 7, 'y': -.65, 'color': '#FFFFFF', 'border_color': '#000000', 'border_width': .05}
        value = {'profile_id': store.read(profile)['id'], 'rule_ids': ['RULE-1'], 'notes': 'Select the complete statement then preserve voice.',
                 'subtitle': {**text, 'max_chars': 4}, 'titles': [{**text, 'text': '容量演示', 'start': 0, 'end': 2, 'y': .65}],
                 'video_scale': 1.05, 'name': '粤仔01-容量演示'}
        path = self.root / 'treatment.json'; store.save(path, value)
        return path

    def test_distillation_is_immutable_and_binds_clock_and_holdout(self):
        profile = self.profile(); value = style.inspect(profile, verify_references=True)
        self.assertEqual(value['payload']['bound_examples'][0]['speech'][0]['words'][1]['text'], '50')
        self.assertEqual(value['payload']['generalization_status'], 'agent-reviewed-holdout')
        self.assertEqual(style.distill(self.study, self.submission_path, profile.parent)['profile_id'], value['id'])
        changed = deepcopy(self.submission); changed['summary'] = 'different revision'; store.save(self.submission_path, changed)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            style.distill(self.study, self.submission_path, profile.parent)

    def test_training_needs_two_sources_and_excludes_holdout(self):
        for change in ('single', 'holdout'):
            value = deepcopy(self.submission)
            value['examples'][1]['task_id'] = self.ids[0 if change == 'single' else 2]
            store.save(self.submission_path, value)
            with self.assertRaisesRegex(ValueError, 'distinct training|cannot use holdout'):
                self.profile()

    def test_forged_image_or_asr_clock_stops_distillation(self):
        for change in ('image', 'speech'):
            value = deepcopy(self.submission)
            if change == 'image':
                value['examples'][0]['start'], value['examples'][0]['end'] = 3.5, 4
            else:
                value['examples'][0]['asr_ids'] = ['ASR-INVENTED']
            store.save(self.submission_path, value)
            with self.assertRaisesRegex(ValueError, 'coverage|ASR IDs'):
                self.profile()

    def test_source_image_mutation_fails_research_but_frozen_profile_reuses(self):
        profile = self.profile()
        (self.tasks[1].parent / 'evidence/frame.jpg').write_bytes(b'mutated')
        self.assertEqual(style.inspect(profile)['schema'], style.PROFILE)
        with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
            style.inspect(profile, verify_references=True)

    def test_style_treatment_preserves_audio_and_number_clock(self):
        profile = self.profile(); selection = self.selected(); treatment = self.treatment(profile)
        plan, audit = style.compile_style(self.tasks[0], selection, profile, treatment)
        self.assertEqual(plan['name'], '粤仔01-容量演示')
        self.assertEqual(plan['tracks'][0]['segments'][0]['volume'], 1)
        self.assertEqual(plan['tracks'][0]['segments'][0]['speed'], 1)
        cues = plan['tracks'][1]['segments']
        self.assertEqual([x['text'] for x in cues], ['容量是', '500', '毫升', '可以倒水'])
        self.assertEqual(cues[1]['start_us'], 1000000)
        self.assertEqual(cues[1]['duration_us'], 500000)
        self.assertEqual(audit['style']['applied_rule_ids'], ['RULE-1'])
        self.assertFalse(audit['speech_time_stretched'])

    def test_ranges_unknown_fields_and_rule_revision_fail_closed(self):
        profile = self.profile(); selection = self.selected(); path = self.treatment(profile); original = store.read(path)
        for change in ('range', 'unknown', 'revision', 'time'):
            value = deepcopy(original)
            if change == 'range': value['video_scale'] = 1.2
            if change == 'unknown': value['filter'] = 'not-accepted'
            if change == 'revision': value['profile_id'] = 'wrong'
            if change == 'time': value['titles'][0]['end'] = 10
            store.save(path, value)
            with self.assertRaises(ValueError):
                style.compile_style(self.tasks[0], selection, profile, path)

    def test_subtitle_corrections_are_id_bound_and_keep_original_audio(self):
        profile = self.profile(); selection = self.selected(); path = self.treatment(profile); value = store.read(path)
        value['subtitle_replacements'] = [{'from': '容量', 'to': '容量', 'asr_ids': ['ASR-1'], 'reason': 'invalid no-op'}]
        store.save(path, value)
        with self.assertRaisesRegex(ValueError, 'Bind subtitle corrections'):
            style.compile_style(self.tasks[0], selection, profile, path)
        value['subtitle_replacements'] = [{'from': '倒水', 'to': '装水', 'asr_ids': ['ASR-1'],
                                           'reason': 'Offline fixture source review correction declaration'}]
        store.save(path, value)
        plan, audit = style.compile_style(self.tasks[0], selection, profile, path)
        self.assertEqual(plan['tracks'][1]['segments'][-1]['text'], '可以装水')
        self.assertEqual(plan['tracks'][1]['segments'][-1]['start_us'], 2100000)
        self.assertEqual(plan['tracks'][0]['segments'][0]['volume'], 1)
        value['subtitle_replacements'][0]['asr_ids'] = ['ASR-OTHER']; store.save(path, value)
        with self.assertRaisesRegex(ValueError, 'actual unique source ASR IDs'):
            style.compile_style(self.tasks[0], selection, profile, path)

    def test_export_uses_existing_native_assembly_seam(self):
        profile = self.profile(); selection = self.selected(); treatment = self.treatment(profile)
        with patch.object(style.edit, 'assemble_plan', return_value={'status': 'fixture-native-dispatch'}) as native:
            result = style.assemble(self.tasks[0], selection, profile, treatment, self.root / 'assembly', True)
        self.assertEqual(result['status'], 'fixture-native-dispatch')
        self.assertTrue(native.call_args.args[-1])
        self.assertIn('style', native.call_args.args[1])

    def test_profile_tampering_cannot_reuse(self):
        profile = self.profile(); value = store.read(profile); value['payload']['name'] = 'forged'; store.save(profile, value)
        with self.assertRaisesRegex(ValueError, 'profile identity changed'):
            style.inspect(profile)

    def test_recomputed_hash_cannot_bypass_frozen_schema_or_holdout_semantics(self):
        profile = self.profile(); original = store.read(profile)
        for change in ('parameter', 'support', 'holdout', 'clock', 'status', 'source'):
            value = deepcopy(original); payload = value['payload']
            if change == 'parameter': payload['submission']['rules'][0]['parameters']['video_scale'] = [1, 99]
            if change == 'support': payload['submission']['rules'][0]['support'] = ['EX-1']
            if change == 'holdout': payload['submission']['examples'][0]['task_id'] = self.ids[2]
            if change == 'clock': payload['frozen_references'][0]['speech'][0]['words'][0]['end'] = 88
            if change == 'status': payload['generalization_status'] = 'proved-viral'
            if change == 'source': payload['frozen_references'][1]['source_sha256'] = payload['frozen_references'][0]['source_sha256']
            value['id'] = store.identity(payload); store.save(profile, value)
            with self.assertRaises(ValueError):
                style.inspect(profile)

    def test_omitted_music_asr_has_explicit_reason_and_keeps_original_audio(self):
        profile = self.profile(); selection = self.selected(); path = self.treatment(profile); value = store.read(path)
        value['subtitle_omissions'] = [{'asr_ids': ['ASR-1'], 'reason': 'Fixture music segment has unreliable ASR; omit the whole unit'}]
        store.save(path, value)
        plan, audit = style.compile_style(self.tasks[0], selection, profile, path)
        self.assertEqual(plan['tracks'][0]['segments'][0]['volume'], 1)
        self.assertEqual(plan['tracks'][0]['segments'][0]['speed'], 1)
        self.assertEqual(audit['subtitle_count'], 0)
        self.assertEqual(audit['subtitle_omissions'][0]['source_range_seconds'], [.3, 3])
        self.assertEqual(audit['cuts'][0]['omitted_subtitle_asr_ids'], ['ASR-1'])
        self.assertEqual(audit['style']['subtitle_omissions'], audit['subtitle_omissions'])
        self.assertEqual(plan['tracks'][1]['name'], 'Explicit style title overlays')

    def test_omission_rejects_unknown_unselected_and_conflicting_ids(self):
        profile = self.profile(); selection = self.selected(); path = self.treatment(profile); original = store.read(path)
        original['subtitle_omissions'] = [{'asr_ids': ['ASR-1'], 'reason': 'Fixture uncertain music'}]
        for change in ('unknown', 'unselected', 'conflict', 'duplicate', 'empty_reason'):
            value = deepcopy(original)
            selected = store.read(selection)
            if change == 'unknown': value['subtitle_omissions'][0]['asr_ids'] = ['ASR-UNKNOWN']
            if change == 'unselected': selected['clips'][0].update(start=3.2, end=4, audio_review='playback')
            if change == 'conflict': value['subtitle_replacements'] = [
                {'from': '倒水', 'to': '装水', 'asr_ids': ['ASR-1'], 'reason': 'Fixture correction'}]
            if change == 'duplicate': value['subtitle_omissions'].append(deepcopy(value['subtitle_omissions'][0]))
            if change == 'empty_reason': value['subtitle_omissions'][0]['reason'] = ''
            store.save(path, value); store.save(selection, selected)
            with self.assertRaises(ValueError):
                style.compile_style(self.tasks[0], selection, profile, path)
            selected['clips'][0].update(start=0, end=4, audio_review='asr-timing'); store.save(selection, selected)

    def test_subtitle_corrections_never_expand_text_or_change_numeric_claims(self):
        profile = self.profile(); selection = self.selected(); path = self.treatment(profile); value = store.read(path)
        for before, after in [('倒水', '倒入水'), ('500', '600')]:
            value['subtitle_replacements'] = [{'from': before, 'to': after, 'asr_ids': ['ASR-1'], 'reason': 'Fixture source review'}]
            store.save(path, value)
            with self.assertRaisesRegex(ValueError, 'same-length reviewed text'):
                style.compile_style(self.tasks[0], selection, profile, path)

    def test_cross_word_name_replacement_retains_outer_word_clock(self):
        import analysis_edit as edit
        source = [{'text': '粤', 'start': 1, 'end': 1.2}, {'text': '子', 'start': 1.2, 'end': 1.5}]
        corrected = edit._reviewed_word_replacements(source, [{'from': '粤子', 'to': '粤仔'}])
        self.assertEqual(corrected, [{'text': '粤仔', 'start': 1, 'end': 1.5}])
        self.assertEqual(source[1]['text'], '子')

    def test_real_asr374_question_laugh_and_seventy_reply_never_share_a_cue(self):
        import analysis_edit as edit
        # Exact first 21 provider words from the real ASR-000374. This is a
        # transcript excerpt with its original absolute source-second clocks.
        tokens = [
            ('你', 1552.9, 1553.14), ('啊', 1553.14, 1553.3), ('应该', 1553.62, 1553.94),
            ('3', 1553.94, 1554.14), ('0', 1554.14, 1554.34), ('岁', 1554.34, 1554.66),
            ('哈哈哈', 1555.1, 1556.18), ('7', 1556.78, 1556.96), ('0', 1556.96, 1557.14),
            ('岁', 1557.14, 1557.3), ('啦', 1557.3, 1557.38), ('你', 1557.54, 1558.1),
            ('我', 1558.3, 1558.5), ('一点', 1558.5, 1558.82), ('都', 1558.82, 1559.02),
            ('看不出', 1559.02, 1559.5), ('你这么', 1559.5, 1559.98), ('年轻', 1559.98, 1560.74),
            ('是不是', 1560.9, 1561.14), ('啊', 1561.14, 1561.18), ('谢谢', 1561.26, 1562.14)]
        words = [{'text': text, 'start': start, 'end': end} for text, start, end in tokens]
        unit = {'text': '你啊，应该30岁，哈哈哈，70岁啦，你，我一点都看不出你这么年轻，是不是啊，谢谢。', 'words': words}
        boundaries = edit._sentence_breaks(unit)
        groups = edit._subtitle_groups(words, 10, break_after=boundaries)
        cues = [''.join(x['text'] for x in group) for group in groups]
        self.assertEqual(cues[:5], ['你啊', '应该30岁', '哈哈哈', '70岁啦', '你'])
        self.assertEqual(cues[-2:], ['是不是啊', '谢谢'])
        self.assertFalse(any('30' in cue and '70' in cue for cue in cues))
        self.assertEqual([(g[0]['start'], g[-1]['end']) for g in groups[:4]],
                         [(1552.9, 1553.3), (1553.62, 1554.66), (1555.1, 1556.18), (1556.78, 1557.38)])
        partial = edit._subtitle_groups(words[2:], 10, break_after=boundaries)
        self.assertEqual([''.join(x['text'] for x in g) for g in partial[:3]], ['应该30岁', '哈哈哈', '70岁啦'])

    def test_punctuation_only_maps_when_the_complete_word_text_matches(self):
        import analysis_edit as edit
        words = [{'text': '你好', 'start': 0, 'end': .4}, {'text': '谢谢', 'start': .45, 'end': .85}]
        boundaries = edit._sentence_breaks({'text': '你好，谢谢。', 'words': words})
        self.assertEqual(boundaries, {400000, 850000})
        self.assertEqual(len(edit._subtitle_groups(words, 10, break_after=boundaries)), 2)
        self.assertEqual(edit._sentence_breaks({'text': '您好，谢谢。', 'words': words}), set())
        # No splitting one original provider word into fabricated character times.
        whole = [{'text': '你好谢谢', 'start': 0, 'end': .85}]
        self.assertEqual(edit._sentence_breaks({'text': '你好，谢谢。', 'words': whole}), {850000})
        self.assertEqual(len(edit._subtitle_groups(whole, 10, break_after={850000})), 1)

    def test_real_pause_laughter_and_decimal_number_boundaries(self):
        import analysis_edit as edit
        words = [{'text': '50', 'start': 0, 'end': .3}, {'text': '0', 'start': .3, 'end': .5},
                 {'text': '毫升', 'start': .5, 'end': .8}, {'text': '好啊', 'start': 1.08, 'end': 1.5},
                 {'text': '哈哈', 'start': 1.5, 'end': 2}, {'text': '谢谢', 'start': 2, 'end': 2.5}]
        cues = [''.join(x['text'] for x in g) for g in edit._subtitle_groups(words, 10)]
        self.assertEqual(cues, ['500毫升', '好啊', '哈哈', '谢谢'])
        decimal = [{'text': '3', 'start': 0, 'end': .2}, {'text': '.', 'start': .2, 'end': .2},
                   {'text': '14', 'start': .2, 'end': .5}]
        unit = {'text': '3.14。', 'words': decimal}
        self.assertEqual(edit._sentence_breaks(unit), {500000})
        self.assertEqual(''.join(x['text'] for x in edit._subtitle_groups(decimal, 2,
                          break_after=edit._sentence_breaks(unit))[0]), '3.14')


if __name__ == '__main__':
    unittest.main()
