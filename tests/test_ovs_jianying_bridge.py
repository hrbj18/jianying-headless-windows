"""Boundaries that must not silently change the editing promise."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ovs_bridge', Path(__file__).parents[1]/'tools/ovs_jianying_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        html = Path(self.temp.name)/'index.html'
        html.write_text('<html></html>')
        self.edl = {'aspect':'16:9','total_target_sec':1,'tracks':{},'segments':[
            {'id':'a','order':0,'layer':'primary','source':'edit','target_sec':1,
             'spec':{'input_id':'a.mp4','in_sec':2,'out_sec':3}}]}
        self.layout = {'name':'test','canvas':{'width':1920,'height':1080,'fps':30},
                       'background':{'source':'bg.mp4','source_html':str(html),'runtime_version':'test'},
                       'placements':{'a':{'scale':.9,'x':.4,'volume':.5}}}

    def test_source_clock_is_preserved_and_text_stays_editable(self):
        text = {'type':'text','name':'title','segments':[{'text':'可编辑','start_us':0,'duration_us':1000000}]}
        self.layout['text_tracks'] = [text]
        plan, mapping = bridge.compile_plan(self.edl,self.layout)
        self.assertEqual(plan['tracks'][1]['segments'][0]['source_start_us'],2000000)
        self.assertEqual(mapping[0]['target_out_us'],1000000)
        self.assertEqual(plan['tracks'][2],text)

    def test_duration_drift_is_rejected_even_if_upstream_only_warns(self):
        self.edl['total_target_sec']=1.1
        with self.assertRaisesRegex(ValueError,'exactly match'): bridge.compile_plan(self.edl,self.layout)

    def test_fractional_frame_cut_is_rejected(self):
        self.edl['segments'][0]['spec'].update(in_sec=2.01,out_sec=3.01)
        with self.assertRaisesRegex(ValueError,'frame aligned'): bridge.compile_plan(self.edl,self.layout)

    def test_active_audio_is_not_silently_lost(self):
        self.edl['tracks']={'music':{'path':'music.wav'}}
        with self.assertRaisesRegex(ValueError,'explicit adapter'): bridge.compile_plan(self.edl,self.layout)

    def test_speed_or_generated_replacement_is_not_accepted(self):
        self.edl['segments'][0]['source']='generate'
        with self.assertRaisesRegex(ValueError,'deterministic'): bridge.compile_plan(self.edl,self.layout)

    def test_aspect_change_is_not_silent(self):
        self.edl['aspect']='9:16'
        with self.assertRaisesRegex(ValueError,'aspect mismatch'): bridge.compile_plan(self.edl,self.layout)

    def test_extra_layout_cannot_override_source_identity(self):
        self.layout['placements']['a']['source']='replacement.mp4'
        with self.assertRaisesRegex(ValueError,'Unsupported placement'): bridge.compile_plan(self.edl,self.layout)


if __name__=='__main__': unittest.main()
