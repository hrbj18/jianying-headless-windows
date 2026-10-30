"""Offline story compiler: evidence, whole words and undecorated execution."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import analysis_store as store
import story_edit as story


class StoryCompilation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-story-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'offline-original-source-fixture')
        self.transcript = self.root / 'transcript.json'
        self.units = [{'id': 'ASR-000001', 'start': .1, 'end': 2.2, 'text': '你好，真的可以！',
                       'words': [{'start': .1, 'end': .5, 'text': '你好'},
                                 {'start': .9, 'end': 1.3, 'text': '真的'},
                                 {'start': 1.3, 'end': 2.2, 'text': '可以'}]},
                      {'id': 'ASR-000002', 'start': 3.01, 'end': 3.59, 'text': '好棒',
                       'words': [{'start': 3.01, 'end': 3.3, 'text': '好'},
                                 {'start': 3.3, 'end': 3.59, 'text': '棒'}]}]
        store.save(self.transcript, {'schema': 'jy-material-transcript/v1',
            'source_sha256': store.digest_file(self.source), 'timestamp_unit': 'source seconds', 'segments': self.units})
        self.treatment_path = self.root / 'treatment.json'
        self.treatment = {'schema': story.SCHEMA, 'name': 'plain-story', 'promise': 'See whether the real reply resolves the attempt.',
            'source': {'path': str(self.source), 'sha256': store.digest_file(self.source)},
            'transcript': {'path': str(self.transcript), 'sha256': store.digest_file(self.transcript)},
            'canvas': {'width': 912, 'height': 1920, 'fps': 30},
            'segments': [self.clip(0, 69), self.clip(90, 111)],
            'overlay_decisions': [{'decision': 'omit reaction inset', 'added_information': 'No new information.',
                                   'attention_cost': 'It would distract from the original action.',
                                   'delete_test': 'The action and response remain clear without it.'}], 'omissions': []}
        self.save()

    def clip(self, first, last):
        return {'source_start_frame': first, 'source_end_frame': last, 'role': 'attempt or response',
                'new_information': 'A real event advances.', 'expectation': 'Will the attempt succeed?',
                'payoff': 'The following reply answers it.', 'why_kept': 'Necessary cause or response.'}

    def save(self):
        store.save(self.treatment_path, self.treatment)

    def compile(self):
        self.save()
        return story.compile_plan(self.treatment_path)

    def themed(self):
        self.treatment['theme'] = {
            'statement': 'A tentative greeting receives a warm reply.',
            'viewer_question': 'Will the person respond?',
            'payoff': 'The reply resolves the uncertainty.',
            'events': [{'id': 'E1', 'source_start_frame': 0, 'source_end_frame': 120,
                        'observation': 'A greeting, a pause, then an answering phrase.',
                        'supports_theme': 'The response is present in the same source event.'}]}
        for i, clip in enumerate(self.treatment['segments']):
            clip['id'] = f'C{i + 1}'
            clip['contribution'] = {'event_id': 'E1', 'theme_link': 'Attempt and its answer.',
                                    'focus': 'The participant and real reply.',
                                    'remove_cost': 'The exchange would lose its cause or response.'}
        self.treatment['retention_review'] = {'spans': [
            self.span('C1', 0, 15, 'dialogue'), self.span('C1', 15, 27, 'hold'),
            self.span('C1', 27, 69, 'action'), self.span('C2', 90, 111, 'reaction')]}

    def span(self, identifier, first, last, kind):
        return {'segment_id': identifier, 'source_start_frame': first, 'source_end_frame': last,
                'kind': kind, 'focus': 'Visible movement or the answering participant.',
                'why_kept': 'Allow the action and response to be understood.',
                'delete_cost': 'The cause or its visible consequence would be missing.'}

    def review_record(self, stage, plan, decision='accepted_for_scope'):
        plan_path = self.root / (stage + '.plan.json')
        export_path = self.root / (stage + '.mp4')
        report_path = self.root / (stage + '.review.json')
        store.save(plan_path, plan)
        export_path.write_bytes(b'offline-render-identity-fixture')
        report = {'schema': 'jy-story-review/v1', 'stage': stage,
                  'plan_sha256': store.digest_file(plan_path), 'export_sha256': store.digest_file(export_path),
                  'decision': decision, 'methods': ['sampled_frames'],
                  'findings': ['The recorded response remains understandable.'],
                  'remaining_limits': ['No continuous playback or subjective listening in this fixture.']}
        if stage == 'packaged_export':
            report['rough_plan_sha256'] = store.digest_file(self.root / 'clean_rough_cut.plan.json')
        store.save(report_path, report)
        return {'stage': stage, **{key: {'path': str(path), 'sha256': store.digest_file(path)}
                                  for key, path in [('plan', plan_path), ('export', export_path),
                                                    ('report', report_path)]}}

    def test_whole_word_mapping_retains_real_text_asr_indices_and_30fps_clocks(self):
        plan, audit = self.compile()
        video = plan['tracks'][0]['segments']
        self.assertEqual(audit['duration_frames'], 90)
        self.assertEqual([x['start_us'] for x in video], [0, 2300000])
        self.assertEqual([x['text'] for x in plan['tracks'][1]['segments']], ['你好', '真的可以', '好棒'])
        cues = audit['subtitles']
        self.assertEqual([(x['asr_id'], x['word_start'], x['word_end']) for x in cues],
                         [('ASR-000001', 0, 1), ('ASR-000001', 1, 3), ('ASR-000002', 0, 2)])
        self.assertEqual(cues[2]['target_range_frames'], [69, 87])
        self.assertEqual(cues[2]['source_word_range_seconds'], [3.01, 3.59])
        self.assertEqual(cues[1]['words'][0]['text'], '真的')
        self.assertEqual(cues[1]['source_asr_text'], self.units[0]['text'])
        self.assertAlmostEqual(cues[2]['rounding_delta_seconds'][0], -.01)

    def test_cut_inside_a_real_word_is_rejected_even_when_subtitle_is_omitted(self):
        self.treatment['segments'][0]['source_end_frame'] = 54  # 1.8 inside 可以, not near either edge.
        self.treatment['omissions'] = [{'asr_id': 'ASR-000001', 'word_start': 2, 'word_end': 3,
                                       'reason': 'Uncertain word; audio still must not be cut in half.'}]
        with self.assertRaisesRegex(ValueError, r'inside ASR word ASR-000001\[2\]'):
            self.compile()

    def test_half_frame_quantization_keeps_the_entire_token_and_records_delta(self):
        self.treatment['segments'] = [self.clip(90, 108)]  # word starts .01 after the grid; end rounds 3.6.
        plan, audit = self.compile()
        self.assertEqual(plan['tracks'][1]['segments'][0]['text'], '好棒')
        self.assertEqual(audit['subtitles'][0]['word_end'], 2)
        self.assertAlmostEqual(audit['subtitles'][0]['rounding_delta_seconds'][1], .01)
        # A cut more than half a frame inside the word is not accepted.
        self.treatment['segments'][0]['source_end_frame'] = 107
        with self.assertRaisesRegex(ValueError, 'inside ASR word'):
            self.compile()

    def test_tolerated_cut_inside_word_tail_records_full_original_word(self):
        value = store.read(self.transcript)
        value['segments'][1]['end'] = 3.61
        value['segments'][1]['words'][1]['end'] = 3.61
        store.save(self.transcript, value)
        self.treatment['transcript']['sha256'] = store.digest_file(self.transcript)
        self.treatment['segments'] = [self.clip(90, 108)]
        plan, audit = self.compile()
        self.assertEqual(plan['tracks'][1]['segments'][0]['text'], '好棒')
        cue = audit['subtitles'][0]
        self.assertEqual(cue['word_end'], 2)
        self.assertEqual(cue['words'][-1]['source_end_seconds'], 3.61)
        self.assertAlmostEqual(cue['rounding_delta_seconds'][1], -.01)

    def test_source_or_transcript_hash_change_cannot_create_output(self):
        for key, path in [('Source', self.source), ('Transcript', self.transcript)]:
            with self.subTest(key=key):
                before = path.read_bytes()
                path.write_bytes(before + b' ')
                out = self.root / ('bad-' + key)
                with self.assertRaisesRegex(ValueError, key + ' SHA256 changed'):
                    story.compile_treatment(self.treatment_path, out)
                self.assertFalse(out.exists())
                path.write_bytes(before)

    def test_transcript_hash_alone_cannot_bind_another_source(self):
        value = store.read(self.transcript)
        value['source_sha256'] = '0' * 64
        store.save(self.transcript, value)
        self.treatment['transcript']['sha256'] = store.digest_file(self.transcript)
        with self.assertRaisesRegex(ValueError, 'bind the verified source'):
            self.compile()

    def test_repeated_or_reordered_source_needs_an_explicit_reason(self):
        original = deepcopy(self.treatment['segments'])
        for clips in [[original[0], deepcopy(original[0])], [original[1], original[0]]]:
            self.treatment['segments'] = deepcopy(clips)
            with self.assertRaisesRegex(ValueError, 'requires reuse_reason'):
                self.compile()
            self.treatment['segments'][1]['reuse_reason'] = 'Explicitly compare the earlier action after the later reply.'
            _, audit = self.compile()
            self.assertIn('reuse_reason', audit['cuts'][1])

    def test_word_range_omission_does_not_join_across_removed_speech_or_edit_audio(self):
        self.treatment['omissions'] = [{'asr_id': 'ASR-000001', 'word_start': 1, 'word_end': 2,
                                       'reason': 'This provider word remains uncertain.'}]
        plan, audit = self.compile()
        self.assertEqual([x['text'] for x in plan['tracks'][1]['segments']], ['你好', '可以', '好棒'])
        self.assertEqual([x['word_index'] for x in audit['omitted_words']], [1])
        self.assertEqual([x['volume'] for x in plan['tracks'][0]['segments']], [1, 1])
        for bad in [{'asr_id': 'invented', 'word_start': 0, 'word_end': 1, 'reason': 'bad'},
                    {'asr_id': 'ASR-000001', 'word_start': 0, 'word_end': 4, 'reason': 'bad'},
                    {'asr_id': 'ASR-000001', 'word_start': 0, 'word_end': 1, 'reason': ''}]:
            self.treatment['omissions'] = [bad]
            with self.assertRaises(ValueError):
                self.compile()

    def test_numeric_packer_preserves_each_original_word_in_audit(self):
        self.units[0]['text'] = '500毫升'
        self.units[0]['words'] = [{'start': .1, 'end': .5, 'text': '50'},
                                  {'start': .5, 'end': .6, 'text': '0'},
                                  {'start': .6, 'end': 2.2, 'text': '毫升'}]
        value = store.read(self.transcript)
        value['segments'] = self.units
        store.save(self.transcript, value)
        self.treatment['transcript']['sha256'] = store.digest_file(self.transcript)
        plan, audit = self.compile()
        self.assertEqual(plan['tracks'][1]['segments'][0]['text'], '500毫升')
        self.assertEqual([w['text'] for w in audit['subtitles'][0]['words']], ['50', '0', '毫升'])
        self.assertEqual(audit['subtitles'][0]['word_end'], 3)

    def test_provider_timed_space_preserves_text_and_original_word_indices(self):
        value = store.read(self.transcript)
        value['segments'][0]['text'] = 'Hello world!'
        value['segments'][0]['words'] = [{'start': .1, 'end': .5, 'text': 'Hello'},
                                       {'start': .5, 'end': .6, 'text': ' '},
                                       {'start': .6, 'end': 2.2, 'text': 'world'}]
        store.save(self.transcript, value)
        self.treatment['transcript']['sha256'] = store.digest_file(self.transcript)
        plan, audit = self.compile()
        self.assertEqual(plan['tracks'][1]['segments'][0]['text'], 'Hello world')
        self.assertEqual([w['word_index'] for w in audit['subtitles'][0]['words']], [0, 1, 2])
        self.assertEqual(audit['subtitles'][0]['words'][1]['text'], ' ')

    def test_no_titles_music_effects_character_attribution_or_score_are_generated(self):
        plan, audit = self.compile()
        self.assertEqual([x['type'] for x in plan['tracks']], ['video', 'text'])
        for segment in plan['tracks'][0]['segments']:
            self.assertEqual(set(segment), {'source', 'source_start_us', 'source_duration_us', 'start_us',
                                            'duration_us', 'speed', 'volume'})
            self.assertEqual((segment['speed'], segment['volume']), (1, 1))
        self.assertEqual(audit['overlays_applied'], [])
        self.assertEqual(audit['review_status'], 'requires-agent-audiovisual-and-story-review')
        self.assertFalse(audit['speaker_attribution_generated'])
        self.assertNotIn('score', audit)
        self.treatment['segments'][0]['text'] = 'An invented line'
        with self.assertRaisesRegex(ValueError, 'unsupported fields'):
            self.compile()

    def test_story_motives_and_counterfactual_decisions_cannot_be_empty(self):
        base = deepcopy(self.treatment)
        for key in ['role', 'new_information', 'expectation', 'payoff', 'why_kept']:
            self.treatment = deepcopy(base)
            self.treatment['segments'][0][key] = ' '
            with self.assertRaisesRegex(ValueError, 'nonempty text'):
                self.compile()
        for key in ['added_information', 'attention_cost', 'delete_test']:
            self.treatment = deepcopy(base)
            self.treatment['overlay_decisions'][0][key] = ''
            with self.assertRaisesRegex(ValueError, 'nonempty text'):
                self.compile()

    def test_fresh_output_has_bound_plan_and_audit_and_never_overwrites(self):
        out = self.root / 'compile'
        result = story.compile_treatment(self.treatment_path, out)
        self.assertEqual(set(p.name for p in out.iterdir()), {'plan.json', 'audit.json'})
        self.assertEqual(result['plan_sha256'], store.digest_file(out / 'plan.json'))
        audit = store.read(out / 'audit.json')
        self.assertEqual(audit['treatment_sha256'], store.digest_file(self.treatment_path))
        self.assertEqual(audit['transcript_sha256'], store.digest_file(self.transcript))
        self.assertEqual(audit['source_sha256'], store.digest_file(self.source))
        with self.assertRaisesRegex(ValueError, 'fresh directory'):
            story.compile_treatment(self.treatment_path, out)

    def test_theme_maps_holds_and_reactions_to_one_source_event_without_changing_plan(self):
        original, old_audit = self.compile()
        self.assertNotIn('editorial_contract', old_audit)
        self.themed()
        plan, audit = self.compile()
        self.assertEqual(plan, original)
        contract = audit['editorial_contract']
        spans = contract['retention_review']['spans']
        self.assertEqual(spans[1]['kind'], 'hold')
        self.assertEqual(spans[1]['source_range_frames'], [15, 27])
        self.assertEqual(spans[1]['review_target_frames'], [15, 20, 26])
        self.assertEqual(spans[-1]['source_range_frames'], [90, 111])
        self.assertEqual(spans[-1]['target_range_frames'], [69, 90])
        self.assertEqual(spans[-1]['target_range_us'], [2300000, 3000000])
        self.assertEqual({x['event_id'] for x in spans}, {'E1'})
        self.assertEqual([x['status'] for x in contract['review_requirements']], ['pending', 'pending'])
        self.assertEqual(contract['stage_reviews'], [])
        self.assertEqual(audit['review_status'], 'requires-agent-audiovisual-and-story-review')

    def test_theme_requires_all_clip_contributions_and_actual_event_membership(self):
        self.themed()
        base = deepcopy(self.treatment)
        for mutate in [
            lambda: self.treatment['segments'][0].pop('contribution'),
            lambda: self.treatment['segments'][0]['contribution'].update(event_id='missing'),
            lambda: self.treatment['theme']['events'][0].update(source_end_frame=80),
            lambda: self.treatment['segments'][0]['contribution'].update(remove_cost=' '),
            lambda: self.treatment['theme']['events'].append({
                'id': 'unused', 'source_start_frame': 500, 'source_end_frame': 600,
                'observation': 'An unselected scene.', 'supports_theme': 'Unselected proof.'}),
        ]:
            self.treatment = deepcopy(base)
            mutate()
            with self.assertRaises(ValueError):
                self.compile()
        self.treatment = deepcopy(base)
        self.treatment.pop('theme')
        with self.assertRaisesRegex(ValueError, 'require a theme'):
            self.compile()

    def test_retention_rejects_missing_frames_overlap_foreign_clips_and_empty_delete_cost(self):
        self.themed()
        base = deepcopy(self.treatment)
        for mutate in [
            lambda rows: rows[1].update(source_start_frame=16),
            lambda rows: rows[1].update(source_start_frame=14),
            lambda rows: rows[1].update(source_end_frame=70),
            lambda rows: rows[0].update(segment_id='unselected'),
            lambda rows: rows.pop(),
            lambda rows: rows[0].update(delete_cost=''),
            lambda rows: rows[0].update(source_start_frame=False),
        ]:
            self.treatment = deepcopy(base)
            mutate(self.treatment['retention_review']['spans'])
            with self.assertRaises(ValueError):
                self.compile()

    def test_long_hold_is_valid_and_does_not_create_mechanical_cuts(self):
        self.themed()
        self.treatment['segments'] = [self.clip(120, 3720)]
        clip = self.treatment['segments'][0]
        clip.update(id='long', contribution={'event_id': 'E1', 'theme_link': 'A complete physical recovery.',
                    'focus': 'The recovering subject.', 'remove_cost': 'Recovery would appear instantaneous.'})
        self.treatment['theme']['events'][0].update(source_start_frame=120, source_end_frame=3720)
        self.treatment['retention_review']['spans'] = [self.span('long', 120, 3720, 'hold')]
        plan, audit = self.compile()
        self.assertEqual(len(plan['tracks'][0]['segments']), 1)
        self.assertEqual(audit['duration_frames'], 3600)
        self.assertEqual(len(audit['editorial_contract']['retention_review']['spans']), 1)

    def test_reused_source_retention_is_mapped_per_occurrence(self):
        self.themed()
        repeated = deepcopy(self.treatment['segments'][0])
        repeated.update(id='again', reuse_reason='Compare an earlier expression after its reply.')
        self.treatment['segments'].append(repeated)
        self.treatment['retention_review']['spans'].append(self.span('again', 0, 69, 'reaction'))
        _, audit = self.compile()
        final = audit['editorial_contract']['retention_review']['spans'][-1]
        self.assertEqual(final['source_range_frames'], [0, 69])
        self.assertEqual(final['target_range_frames'], [90, 159])

    def test_theme_without_retention_is_pending_and_cannot_look_fully_reviewed(self):
        self.themed()
        self.treatment.pop('retention_review')
        _, audit = self.compile()
        self.assertEqual(audit['editorial_contract']['retention_review']['status'], 'not-provided')
        self.assertEqual(audit['editorial_contract']['stage_reviews'], [])

    def test_two_stage_review_binds_files_and_preserves_inspection_limits(self):
        self.themed()
        plan, _ = self.compile()
        clean = self.review_record('clean_rough_cut', plan)
        production = deepcopy(plan)
        production['tracks'].append({'type': 'text', 'name': 'editorial emphasis', 'segments': []})
        packaged = self.review_record('packaged_export', production)
        self.treatment['retention_review']['reviews'] = [clean, packaged]
        _, audit = self.compile()
        stages = audit['editorial_contract']['stage_reviews']
        self.assertEqual([x['declared_decision'] for x in stages], ['accepted_for_scope'] * 2)
        self.assertEqual(stages[1]['declared_methods'], ['sampled_frames'])
        self.assertTrue(stages[1]['remaining_limits'])
        self.assertEqual(audit['review_status'], 'requires-agent-audiovisual-and-story-review')
        self.assertNotIn('aesthetic_passed', audit)
        report = store.read(packaged['report']['path'])
        report['rough_plan_sha256'] = '0' * 64
        store.save(packaged['report']['path'], report)
        packaged['report']['sha256'] = store.digest_file(packaged['report']['path'])
        with self.assertRaisesRegex(ValueError, 'accepted rough plan SHA256'):
            self.compile()
        report['rough_plan_sha256'] = clean['plan']['sha256']
        store.save(packaged['report']['path'], report)
        packaged['report']['sha256'] = store.digest_file(packaged['report']['path'])
        Path(packaged['export']['path']).write_bytes(b'changed export')
        with self.assertRaisesRegex(ValueError, 'Review export SHA256 changed'):
            self.compile()

    def test_review_rejects_wrong_file_binding_stale_rough_cut_and_reversed_stages(self):
        self.themed()
        plan, _ = self.compile()
        clean = self.review_record('clean_rough_cut', plan)
        packaged = self.review_record('packaged_export', plan)
        self.treatment['retention_review']['reviews'] = [packaged]
        with self.assertRaisesRegex(ValueError, 'clean rough-cut review first'):
            self.compile()
        self.treatment['retention_review']['reviews'] = [clean]
        self.treatment['name'] = 'changed-story'
        with self.assertRaisesRegex(ValueError, 'does not match the current compiled story'):
            self.compile()
        self.treatment['name'] = 'plain-story'
        report = store.read(clean['report']['path'])
        report['export_sha256'] = '0' * 64
        store.save(clean['report']['path'], report)
        clean['report']['sha256'] = store.digest_file(clean['report']['path'])
        with self.assertRaisesRegex(ValueError, 'bind the exact stage'):
            self.compile()

    def test_review_with_incomplete_methods_requires_limits_and_revision_needs_findings(self):
        self.themed()
        plan, _ = self.compile()
        clean = self.review_record('clean_rough_cut', plan)
        self.treatment['retention_review']['reviews'] = [clean]
        original = store.read(clean['report']['path'])
        for replacement in [{'remaining_limits': []}, {'methods': ['watched_everything']},
                            {'decision': 'revise', 'findings': []}]:
            report = {**original, **replacement}
            store.save(clean['report']['path'], report)
            clean['report']['sha256'] = store.digest_file(clean['report']['path'])
            with self.assertRaises(ValueError):
                self.compile()

    def test_static_subtitle_style_reproduces_readable_plan_without_changing_words_or_clocks(self):
        expected, old_audit = self.compile()
        font = self.root / 'fixture-font.ttf'
        font.write_bytes(b'offline-font-identity-fixture')
        style = {'size': 11.3, 'y': .68, 'color': '#FFFFFF', 'border_color': '#2B2925',
                 'border_width': .068, 'font_path': font.as_posix()}
        for cue in expected['tracks'][1]['segments']:
            cue.update(style)
        self.treatment['subtitle_style'] = style
        plan, audit = self.compile()
        self.assertEqual(plan, expected)
        self.assertEqual(audit['subtitles'], old_audit['subtitles'])
        self.assertEqual(audit['subtitle_style']['font']['sha256'], store.digest_file(font))
        self.assertEqual(plan['tracks'][1]['segments'][0]['font_path'], font.as_posix())
        self.assertNotIn('x', plan['tracks'][1]['segments'][0])
        self.treatment['subtitle_style']['font_path'] = 'fixture-font.ttf'
        plan, _ = self.compile()
        self.assertEqual(plan['tracks'][1]['segments'][0]['font_path'], str(font))

    def test_subtitle_style_rejects_invalid_coordinates_and_content_or_clock_edits(self):
        for style in [{'size': True}, {'size': 0}, {'size': 101}, {'x': 1.01}, {'y': -1.01},
                      {'border_width': -1}, {'color': 'white'}, {'border_color': '#00000000'},
                      {'text': 'invented speech'}, {'start_us': 5}, {'keyframes': {}},
                      {'font_path': str(self.root / 'missing.ttf')}, None]:
            with self.subTest(style=style):
                self.treatment['subtitle_style'] = style
                with self.assertRaises(ValueError):
                    self.compile()

    def test_readable_rough_cut_review_stays_exact_and_rejects_a_later_style_change(self):
        self.themed()
        self.treatment['subtitle_style'] = {'size': 11.3, 'y': .68}
        plan, _ = self.compile()
        clean = self.review_record('clean_rough_cut', plan)
        self.treatment['retention_review']['reviews'] = [clean]
        _, audit = self.compile()
        self.assertEqual(audit['editorial_contract']['stage_reviews'][0]['declared_decision'],
                         'accepted_for_scope')
        self.treatment['subtitle_style']['size'] = 12
        with self.assertRaisesRegex(ValueError, 'does not match the current compiled story'):
            self.compile()


if __name__ == '__main__':
    unittest.main()
