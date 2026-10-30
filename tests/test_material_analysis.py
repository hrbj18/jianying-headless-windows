"""Analysis interfaces: fake paid transport, real local evidence and native plans."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import analysis_store as store
import cloud_asr as cloud
import media_evidence as media
import material_analysis as analysis
import analysis_edit as edit
from local_config import configure_environment


class Response:
    def __init__(self, value, status=200):
        self.value, self.status_code = value, status
    def json(self):
        return self.value


class Cloud:
    def __init__(self):
        self.submissions, self.polls, self.downloads, self.uploads = 0, 0, 0, 0
        self.submit_error, self.poll_error = None, None
        self.payload = {'transcripts': [{'sentences': [{'begin_time': 100, 'end_time': 900,
            'text': '真实测试', 'words': [{'begin_time': 100, 'end_time': 500, 'text': '真实'},
                                      {'begin_time': 500, 'end_time': 900, 'text': '测试'}]}]}]}
    def get(self, url, **kwargs):
        if url.endswith('/uploads'):
            return Response({'data': {'upload_host': 'https://fixture.aliyuncs.com', 'upload_dir': 'fixture',
                             'oss_access_key_id': 'fixture', 'signature': 'fixture', 'policy': 'fixture'}})
        if '/tasks/' in url:
            self.polls += 1
            if self.poll_error:
                raise self.poll_error
            return Response({'output': {'task_status': 'SUCCEEDED', 'results': [{'subtask_status': 'SUCCEEDED',
                'transcription_url': 'https://fixture.aliyuncs.com/result.json'}]}, 'usage': {'input_tokens': 10}})
        self.downloads += 1
        return Response(self.payload)
    def post(self, url, **kwargs):
        if url.endswith('/transcription'):
            self.submissions += 1
            if self.submit_error:
                raise self.submit_error
            return Response({'output': {'task_id': 'fixture-task-' + str(self.submissions)}})
        self.uploads += 1
        return Response({})


def config(chunk_seconds=10):
    return {'key': 'fixture-secret', 'base': 'https://dashscope.aliyuncs.com/api/v1',
            'scope': 'fixture-scope', 'model': cloud.MODEL, 'chunk_seconds': chunk_seconds}


class DurableASR(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-analysis-asr-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.audio = self.root / 'test.wav'; self.audio.write_bytes(b'fake-audio-offline-test')
        self.http, self.config = Cloud(), config()
    def invoke(self):
        return cloud.transcribe(self.audio, self.root / 'operation', self.config, 2, http=self.http, poll_seconds=0)
    def test_completed_reentry_uses_verified_result_without_upload_or_submit(self):
        a, b = self.invoke(), self.invoke()
        self.assertFalse(a['cache_hit']); self.assertTrue(b['cache_hit'])
        self.assertEqual((self.http.submissions, self.http.uploads, self.http.downloads), (1, 1, 1))
        self.assertEqual(a['segments'][0]['words'][0], {'start': .1, 'end': .5, 'text': '真实'})
        for path in (self.root / 'operation').glob('*.json'):
            self.assertNotIn(self.config['key'], path.read_text('utf8'))
    def test_uncertain_post_is_never_automatically_repeated(self):
        self.http.submit_error = TimeoutError('fixture timeout')
        for _ in range(2):
            with self.assertRaises(cloud.ASRError):
                self.invoke()
        self.assertEqual(self.http.submissions, 1)
        self.assertEqual(store.read(self.root / 'operation/task.json')['status'], 'submission_unknown')
    def test_accepted_poll_failure_resumes_original_id(self):
        self.http.poll_error = TimeoutError('poll interrupted')
        with self.assertRaises(cloud.ASRError) as failed:
            self.invoke()
        self.assertTrue(failed.exception.accepted)
        self.assertEqual(failed.exception.task_id, 'fixture-task-1')
        self.http.poll_error = None
        self.assertEqual(self.invoke()['task_id'], 'fixture-task-1')
        self.assertEqual(self.http.submissions, 1)
    def test_corrupt_result_or_changed_account_never_submits(self):
        self.invoke()
        path = self.root / 'operation/transcript.json'; path.write_text('{}', 'utf8')
        with self.assertRaisesRegex(ValueError, 'Cached ASR result changed'):
            self.invoke()
        self.config['scope'] = 'another-account'
        with self.assertRaisesRegex(ValueError, 'account or model changed'):
            self.invoke()
        self.assertEqual(self.http.submissions, 1)
    def test_missing_word_time_is_not_invented(self):
        self.http.payload['transcripts'][0]['sentences'][0]['words'][0].pop('begin_time')
        with self.assertRaises(cloud.ASRError):
            self.invoke()
        with self.assertRaises(cloud.ASRError):
            self.invoke()
        self.assertEqual(self.http.submissions, 1)
    def test_errors_redact_credentials_and_remote_urls(self):
        self.http.submit_error = RuntimeError(self.config['key'] + ' https://fixture.aliyuncs.com/x?' + 'signature=fixture')
        with self.assertRaises(cloud.ASRError) as failed:
            self.invoke()
        self.assertNotIn(self.config['key'], str(failed.exception))
        self.assertNotIn('signature=', str(failed.exception))
    def test_signed_download_requires_vendor_https_without_userinfo(self):
        for url in ['http://fixture.aliyuncs.com/a', 'https://x.aliyuncs.com.evil/a',
                    'https://user@fixture.aliyuncs.com/a', 'https://fixture.aliyuncs.com:444/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                cloud._url(url)
    def test_credential_files_follow_explicit_order_without_mutating_environment(self):
        a, b = self.root / 'first.env', self.root / 'second.env'
        a.write_text('DASHSCOPE_API_KEY=first-fixture\nOTHER_SECRET=not-imported\n', 'utf8')
        b.write_text('DASHSCOPE_API_KEY=second-fixture\n', 'utf8')
        with patch.dict(os.environ, {'DASHSCOPE_API_KEY': '', 'DASHSCOPE_WORKSPACE_ID': ''}):
            value = cloud.configuration({'credential_files': [str(a), str(b)]})
            self.assertEqual(value['key'], 'first-fixture')
            self.assertEqual(os.environ['DASHSCOPE_API_KEY'], '')
            self.assertNotIn('OTHER_SECRET', os.environ)
            self.assertNotIn('first-fixture', str(cloud.public_config(value)))


class SamplingPolicies(unittest.TestCase):
    def test_real_provider_millisecond_boundaries_do_not_round_trip_through_float_seconds(self):
        for start,end in [(31620,32260),(7520,8040),(32240,33680)]:
            payload={'transcripts':[{'sentences':[{'begin_time':start,'end_time':end,'text':'真实边界',
                    'words':[{'begin_time':start,'end_time':end,'text':'真实边界'}]}]}]}
            unit=cloud.normalize(payload,40)[0]
            self.assertEqual(unit['words'][0]['start'],start/1000)
            self.assertEqual(unit['words'][0]['end'],end/1000)
    def test_long_video_read_requires_chapter_selection_before_attaching_images(self):
        task={'status':'review-ready','id':'fixture','request':{'model':'offline','goal':'pick a chapter'}}
        evidence={'chapters':[{'id':'CHAPTER-001','start':0,'end':7200}],
                  'policy':{'whole_video_remote_default':False},
                  'sheets':[{'chapter_id':'CHAPTER-001','file':'sheet.jpg'}],
                  'cells':[{'chapter_id':'CHAPTER-001','id':'CELL-001'}]}
        with patch.object(analysis,'load_task',return_value=(Path.cwd()/'task.json',task,evidence,{'segments':[]})):
            index=analysis.read_task('unused')
            self.assertEqual(index['status'],'chapter-selection-required')
            self.assertEqual((index['sheets'],index['cells']),([],[]))
            selected=analysis.read_task('unused',chapters=['CHAPTER-001'])
            self.assertEqual(len(selected['sheets']),1)
            self.assertEqual(len(selected['cells']),1)
    def test_provider_split_digits_never_wrap_into_misleading_numeric_subtitles(self):
        words = [{'text':'下面进入蓝色水杯的演示这个水杯容量是','start':0,'end':2},
                 {'text':'50','start':2,'end':2.2}, {'text':'0','start':2.2,'end':2.3},
                 {'text':'毫升','start':2.3,'end':2.6}]
        groups = edit._subtitle_groups(words)
        self.assertEqual([''.join(w['text'] for w in g) for g in groups],
                         ['下面进入蓝色水杯的演示这个水杯容量是','500毫升'])
        self.assertEqual((groups[1][0]['start'],groups[1][0]['end']), (2,2.3))
    def test_two_hour_budget_is_chaptered_not_dense_whole_video_vision(self):
        policy, chapters = media.sampling_plan(7200)
        self.assertEqual((policy['chapters'], policy['frame_budget'], policy['rows']), (12, 192, 4))
        self.assertFalse(policy['whole_video_remote_default'])
        self.assertTrue(all(len(row['samples']) == 16 for row in chapters))
        self.assertTrue(all(sum(x['anchor'] for x in row['samples']) >= 8 for row in chapters))
    def test_json_duplicate_keys_and_nonfinite_values_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='jy-json-') as folder:
            path = Path(folder) / 'input.json'
            for text in ['{"a":1,"a":2}', '{"a":NaN}']:
                path.write_text(text, 'utf8')
                with self.assertRaises(ValueError):
                    store.read(path)


class LocalAnalysisFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_environment()
        try:
            ffmpeg, _ = media.binaries()
        except ValueError:
            raise unittest.SkipTest('FFmpeg is required for real local evidence verification')
        cls.temp = tempfile.TemporaryDirectory(prefix='jy-material-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name).resolve() / 'work'; cls.root.mkdir()
        cls.source = cls.root / '原始素材.mp4'
        media.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=22',
                   '-f', 'lavfi', '-i', 'sine=frequency=440:duration=22', '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(cls.source)])
    def setUp(self):
        cache = self.root / ('c-' + store.identity(self.id())[:10])
        self.enterContext(patch.object(analysis, 'workspace_root', return_value=cache))
        self.http = Cloud()
        self.provider = lambda audio, folder, cfg, duration: cloud.transcribe(
            audio, folder, cfg, duration, http=self.http, poll_seconds=0)
        self.job = self.root / ('job-' + self.id().split('.')[-1])
    def prepare(self, goal='Select an evidenced test section', model='offline-test-model'):
        return analysis.prepare(self.source, self.job, goal, model, 'bailian',
                                provider=self.provider, config=config())
    def review(self):
        result = self.prepare()
        self.task = Path(result['task'])
        packet = analysis.read_task(self.task)
        value = deepcopy(packet['submission_template'])
        value.update(reviewed_sheet_ids=[x['id'] for x in packet['sheets']], summary='Offline fixture review',
                     candidates=[{'id': 'CLIP-1', 'start': 0, 'end': 2, 'reason': 'Fixture speech interval',
                                  'evidence_cell_ids': [packet['cells'][0]['id']], 'asr_ids': [packet['transcript'][0]['id']]}])
        path = self.job / 'submission.json'; store.save(path, value)
        analysis.submit(self.task, path)
        return value
    def selection(self):
        self.review()
        detail = analysis.detail(self.task, 'CLIP-1')
        review = store.read(self.job / 'review.json')
        value = {'task_id': review['task_id'], 'review_sha256': review['submission_sha256'], 'subtitles': True,
                 'clips': [{'candidate_id': 'CLIP-1', 'start': .1, 'end': 1.5, 'detail_index': detail['path'],
                            'reviewed_detail_sheet_ids': [s['id'] for s in detail['sheets']], 'audio_review': 'asr-timing'}]}
        path = self.job / 'selection.json'; store.save(path, value)
        return path
    def test_chunk_offsets_and_goal_changes_reuse_cloud_result_and_local_images(self):
        result = self.prepare()
        task = Path(result['task'])
        transcript = store.read(self.job / 'transcript.json')
        self.assertEqual([x['start'] for x in transcript['segments']], [.1, 10.1, 20.1])
        self.assertEqual(self.http.submissions, 3)
        self.prepare()
        self.assertEqual(self.http.submissions, 3)
        other = self.root / ('other-' + self.job.name)
        value = analysis.prepare(self.source, other, 'Different editorial goal', 'other-model', 'bailian',
                                 provider=self.provider, config=config())
        self.assertEqual(self.http.submissions, 3)
        self.assertTrue(all(x['cache_hit'] for x in store.read(other / 'transcript.json')['chunks']))
        self.assertEqual(store.digest_file(self.job / 'evidence/evidence.json'), store.digest_file(other / 'evidence/evidence.json'))
        packet = analysis.read_task(task, query='测试')
        self.assertEqual(packet['matching_units'], 3)
        self.assertEqual(value['status'], 'review-ready')
    def test_forged_evidence_reference_and_conflicting_submission_are_rejected(self):
        value = self.review()
        changed = deepcopy(value); changed['candidates'][0]['evidence_cell_ids'] = ['invented-cell']
        path = self.job / 'bad.json'; store.save(path, changed)
        with self.assertRaisesRegex(ValueError, 'actual image cell'):
            analysis.submit(self.task, path)
        changed = deepcopy(value); changed['summary'] = 'Changed conclusion'; store.save(path, changed)
        with self.assertRaisesRegex(ValueError, 'different review'):
            analysis.submit(self.task, path)
    def test_native_plan_uses_source_word_clock_and_exact_selected_intervals(self):
        path = self.selection()
        plan, audit = edit.compile_selection(self.task, path)
        segment = plan['tracks'][0]['segments'][0]
        self.assertEqual(segment['source_start_us'], 100000)
        self.assertEqual(segment['source_duration_us'], 1400000)
        self.assertEqual(segment['volume'], 1)
        self.assertEqual(plan['tracks'][1]['segments'][0]['text'], '真实测试')
        self.assertEqual(audit['cuts'][0]['asr_ids'], ['ASR-000001'])
        self.assertFalse(audit['speech_time_stretched'])
    def test_detail_is_required_and_cannot_be_replaced_by_overview(self):
        path = self.selection(); selection = store.read(path)
        selection['clips'][0]['reviewed_detail_sheet_ids'] = []; store.save(path, selection)
        with self.assertRaisesRegex(ValueError, 'actually reviewed detail'):
            edit.compile_selection(self.task, path)
    def test_tampered_image_stops_review_or_export_before_cloud(self):
        path = self.selection(); selection = store.read(path)
        detail = store.read(selection['clips'][0]['detail_index'])
        folder = Path(selection['clips'][0]['detail_index']).parent
        (folder / detail['frames'][0]['file']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
            edit.compile_selection(self.task, path)
    def test_same_output_cannot_silently_change_model_or_goal(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'different source, goal, model'):
            self.prepare(goal='Different goal')
    def test_changed_cached_transcript_stops_prepare_without_resubmission(self):
        self.prepare()
        original = self.http.submissions
        (self.job / 'transcript.json').write_text('{}',encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'Evidence bytes changed'):
            self.prepare()
        self.assertEqual(self.http.submissions, original)
    def test_distant_cell_in_same_chapter_cannot_support_candidate(self):
        self.review()
        value = store.read(self.job / 'submission.json')
        packet = analysis.read_task(self.task)
        value['candidates'][0]['evidence_cell_ids'] = [packet['cells'][-1]['id']]
        store.save(self.job / 'bad.json',value)
        with self.assertRaisesRegex(ValueError, 'outside reviewed coverage'):
            analysis.submit(self.task,self.job / 'bad.json')
    def test_changed_saved_assembly_plan_is_rejected_before_native_build_resume(self):
        path = self.selection()
        out = self.root / ('assembly-' + self.job.name)
        def fake_build(plan, folder):
            store.save(folder / 'build.json',{'offline_fixture':True})
        with patch('jy14_headless.build',side_effect=fake_build), patch('jy14_headless.verify_build') as verify:
            edit.assemble(self.task,path,out)
            changed = store.read(out / 'edit.plan.json'); changed['name']='tampered'
            store.save(out / 'edit.plan.json',changed)
            with self.assertRaisesRegex(ValueError,'plan or audit changed'):
                edit.assemble(self.task,path,out)
            verify.assert_not_called()
    def test_silent_analysis_never_requests_cloud(self):
        result = analysis.prepare(self.source, self.job, 'Visual overview', 'offline-test-model', 'none',
                                  provider=lambda *args: self.fail('Cloud must not be called'))
        self.assertEqual(result['asr_segments'], 0)
    def test_outside_candidate_cut_and_fake_silence_are_rejected(self):
        path = self.selection(); selection = store.read(path)
        selection['clips'][0]['end'] = 3; store.save(path, selection)
        with self.assertRaises(ValueError):
            edit.compile_selection(self.task, path)
        selection['clips'][0]['end'] = 1.5; selection['clips'][0]['audio_review'] = 'silent-source'; store.save(path, selection)
        with self.assertRaisesRegex(ValueError, 'cannot be declared absent'):
            edit.compile_selection(self.task, path)
    def test_low_frame_rate_tail_keeps_actual_pts_instead_of_failing_or_inventing_time(self):
        ffmpeg, _ = media.binaries()
        source = self.job / 'one-fps.mp4'; source.parent.mkdir(parents=True)
        media.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=1:d=2',
                   '-c:v', 'libx264', '-g', '1', str(source)])
        row = media._frame(source, 1.75, self.job / 'tail.jpg', 0, 2)
        self.assertEqual(row['requested_seconds'], 1.75)
        self.assertEqual(row['actual_seconds'], 1)


if __name__ == '__main__':
    unittest.main()
