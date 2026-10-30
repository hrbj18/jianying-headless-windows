"""Custom curves must keep the native curve, binding and source/target clock."""
from copy import deepcopy
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_export as export
from runtime_profiles import WINDOWS_1147_PROFILE

def fixture():
    return {'duration':4_000_000,'fps':30,'materials':{
        'videos':[{'id':'video','type':'video','duration':18_000_000}],
        'speeds':[{'id':'speed','type':'speed','mode':1,'speed':1.5,
                   'curve_speed':{'id':'6768730851543880206','name':'自定义',
                                  'speed_points':[{'x':0.,'y':1.},{'x':.5,'y':2.},{'x':1.,'y':1.}]}}]},
        'tracks':[{'type':'video','segments':[{'id':'segment','material_id':'video',
          'extra_material_refs':['speed'],'speed':1.5,'volume':0.,
          'source_timerange':{'start':8_600_000,'duration':6_000_000},
          'target_timerange':{'start':0,'duration':4_000_000}}]}]}

class CurveGate(unittest.TestCase):
    def test_native_compact_unity_speed_is_valid_only_when_curve_and_clock_agree(self):
        t=fixture();node=t['materials']['speeds'][0];segment=t['tracks'][0]['segments'][0]
        node.pop('speed');segment.pop('speed');segment['source_timerange']['duration']=4000000
        node['curve_speed']['speed_points']=[{'x':0.,'y':.7},{'x':.5,'y':1.3},{'x':1.,'y':.7}]
        self.assertEqual(self.features(t)['speed_curves']['curves'],1)
        node['curve_speed']['speed_points'][1]['y']=1.5
        with self.assertRaisesRegex(ValueError,'average'):self.features(t)
    def features(self,t):
        return export.windows_supported_features(t,{'runtime_profile':WINDOWS_1147_PROFILE},
                 {'runtime_profile':WINDOWS_1147_PROFILE,'app_build':'11.4.7.14462'})
    def test_official_saved_custom_curve_is_kept(self):
        t=fixture();before=deepcopy(t);result=self.features(t)
        self.assertEqual(result['speed_curves']['curves'],1)
        self.assertEqual(t,before)
    def test_curve_identity_and_mode_are_not_arbitrary(self):
        for key,value in [('mode',0),('curve_speed',{'id':'unknown','speed_points':[{'x':0,'y':1},{'x':1,'y':1}]})]:
            t=fixture();t['materials']['speeds'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.features(t)
    def test_invalid_points_are_rejected(self):
        for points in [[{'x':0,'y':1}], [{'x':0,'y':1},{'x':0,'y':2},{'x':1,'y':1}],
                       [{'x':.1,'y':1},{'x':1,'y':1}], [{'x':0,'y':0},{'x':1,'y':1}],
                       [{'x':0,'y':True},{'x':1,'y':1}], [{'x':0,'y':1},{'x':1,'y':float('nan')}]]:
            t=fixture();t['materials']['speeds'][0]['curve_speed']['speed_points']=points
            with self.subTest(points=points),self.assertRaises(ValueError):self.features(t)
    def test_uniform_speed_or_wrong_duration_cannot_masquerade_as_curve(self):
        for change in ['average','duration','source']:
            t=fixture()
            if change=='average':t['materials']['speeds'][0]['speed']=1
            elif change=='duration':t['tracks'][0]['segments'][0]['target_timerange']['duration']=6_000_000
            else:t['tracks'][0]['segments'][0]['source_timerange']['duration']=7_000_000
            with self.subTest(change=change),self.assertRaises(ValueError):self.features(t)
    def test_orphan_curve_or_audio_binding_is_refused(self):
        for change in ['orphan','audio','primary','animated']:
            t=fixture();s=t['tracks'][0]['segments'][0]
            if change=='orphan':s['extra_material_refs']=[]
            elif change=='audio':t['tracks'][0]['type']='audio'
            elif change=='primary':s['material_id']='speed'
            else:s['common_keyframes']=[{'id':'arbitrary'}]
            with self.subTest(change=change),self.assertRaises(ValueError):self.features(t)

if __name__=='__main__':unittest.main()
