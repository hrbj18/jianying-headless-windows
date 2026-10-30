"""Reject serialized effects which would silently render unchanged audio."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys, unittest, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_audio_processing as audio
import native_dsp_graph as dsp


def fixture():
    node=dict(id='effect',type='audio_effect',source_platform=0,sub_type=1,
              path='local-package',resource_id=dsp.RESOURCE_ID,
              audio_adjust_params=dsp.parameters())
    return dict(materials=dict(audio_effects=[node],audios=[dict(id='voice',check_flag=3)]),
                tracks=[dict(type='audio',segments=[dict(id='segment',material_id='voice',
                             extra_material_refs=['effect'],speed=1)])])


class AudioProcessing(unittest.TestCase):
    def validate(self,timeline):
        with patch.object(audio,'verify_resource'):
            return audio.validate(timeline)
    def test_native_five_controls_and_activation_flag(self):
        t=fixture();before=deepcopy(t)
        self.assertEqual(self.validate(t)['audio_effects'],1)
        self.assertEqual(t,before)

    def test_two_categories_cannot_share_persistent_parameter_identity(self):
        t=fixture();nodes=t['materials']['audio_effects'];nodes.clear()
        for part,rid,subtype in [('eq',dsp.EQ_RESOURCE_ID,0),('dynamics',dsp.DYNAMICS_RESOURCE_ID,1)]:
            nodes.append(dict(id=part,type='audio_effect',source_platform=0,sub_type=subtype,
                path='local-package',resource_id=rid,constant_material_id='same-native-key',
                audio_adjust_params=dsp.split_parameters(part)))
        t['tracks'][0]['segments'][0]['extra_material_refs']=['eq','dynamics']
        with self.assertRaisesRegex(ValueError,'parameter identity'):self.validate(t)
        nodes[1]['constant_material_id']='different-native-key'
        self.assertEqual(self.validate(t)['audio_effects'],2)
    def test_native_gui_compact_fields_preserve_processing(self):
        t=fixture();node=t['materials']['audio_effects'][0];node.pop('source_platform');node['time_range']={}
        for p in node['audio_adjust_params']:
            p.pop('min_value');p.pop('max_value')
            if p['portIndex']==0:p.pop('portIndex')
        self.assertEqual(self.validate(t)['audio_effects'],1)
    def test_missing_primary_voice_flag_cannot_pass_as_working_effect(self):
        for flag in [None,0,1,2,True]:
            t=fixture();t['materials']['audios'][0]['check_flag']=flag
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'VoiceChangeFlag'):
                self.validate(t)
    def test_wrong_resource_type_or_platform_is_rejected(self):
        for field,value in [('sub_type',0),('sub_type',True),('source_platform',1),
                            ('resource_id','unknown-resource')]:
            t=fixture();t['materials']['audio_effects'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.validate(t)
    def test_ports_parameters_metadata_and_nonfinite_values_are_not_arbitrary(self):
        for field,value in [('portIndex',2),('parameterIndex',3),('parameterIndex',True),
                            ('value',float('nan')),('value',True),('value',1.01),
                            ('default_value',True),('max_value',20),('name','unreviewed')]:
            t=fixture();t['materials']['audio_effects'][0]['audio_adjust_params'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.validate(t)
    def test_duplicate_or_missing_controls_are_rejected(self):
        for duplicate in [False,True]:
            t=fixture();params=t['materials']['audio_effects'][0]['audio_adjust_params']
            if duplicate:params[-1]=deepcopy(params[0])
            else:params.pop()
            with self.subTest(duplicate=duplicate),self.assertRaises(ValueError):self.validate(t)
    def test_orphan_video_or_nonunity_clock_is_rejected(self):
        for change in ['orphan','video','speed','primary']:
            t=fixture();s=t['tracks'][0]['segments'][0]
            if change=='orphan':s['extra_material_refs']=[]
            elif change=='video':t['tracks'][0]['type']='video'
            elif change=='speed':s['speed']=1.5
            else:s['material_id']='effect'
            with self.subTest(change=change),self.assertRaises(ValueError):self.validate(t)
    def test_authored_bundle_is_byte_verified_and_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=dsp.write_bundle(Path(tmp)/'studio')
            entry=audio.entry_for_node('audio_effects',{'resource_id':dsp.RESOURCE_ID})
            audio.verify_resource(folder,entry)
            (folder/'mdsp_preset.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'bytes changed'):audio.verify_resource(folder,entry)
    def test_control_physical_units_map_back_to_native_ranges(self):
        self.assertAlmostEqual(20*1000**dsp.normalize('frequency',1000),1000)
        self.assertAlmostEqual(-70+70*dsp.normalize('threshold',-18)**.5,-18)
        self.assertAlmostEqual(1+39*dsp.normalize('ratio',3)**2.5,3)
        self.assertAlmostEqual(-24+24*dsp.normalize('ceiling',-2)**.75,-2)
        self.assertAlmostEqual(-20+40*dsp.normalize('gain',6),6)
        for kind,value in [('frequency',0),('ratio',41),('gain',True),('threshold',float('inf'))]:
            with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):dsp.normalize(kind,value)


    def test_silent_native_graph_failure_is_not_successful_audio_processing(self):
        with self.assertRaisesRegex(ValueError,'despite completed encoding'):
            audio.validate_render_log('JY_WINDOWS_NATIVE_EXPORT_DONE\n[Mdsp] load mdsp preset failed')
        audio.validate_render_log('JY_WINDOWS_NATIVE_EXPORT_DONE\nSAMICore loaded preset')

    def test_native_checkbox_mode_is_accepted_without_opening_unknown_algorithms(self):
        t=fixture();t['materials']['audio_effects']=[]
        node=dict(id='noise',type='realtime_denoise',is_denoise=True,denoise_mode=1,
                  denoise_rate=.85,path='reviewed-model',sami_name='denoise_v2',sami_version='1.0',
                  sami_type=2,is_from_hd_sounds=False)
        t['materials']['realtime_denoises']=[node]
        t['tracks'][0]['segments'][0]['extra_material_refs']=['noise']
        with patch.object(audio,'model_identity',return_value={'sha256':audio.MODEL_SHA256}):
            for mode in [0,1]:
                node['denoise_mode']=mode
                self.assertEqual(audio.validate(t)['enabled'],1)
            compact=deepcopy(t);compact['materials']['realtime_denoises'][0].pop('is_denoise')
            compact['materials']['realtime_denoises'][0].pop('denoise_mode')
            self.assertEqual(audio.validate(compact)['enabled'],0)
            for key,value in [('denoise_mode',2),('denoise_mode',True),('sami_type',1),
                              ('sami_name','rnnoise'),('is_from_hd_sounds',True),('is_denoise',0)]:
                bad=deepcopy(t);bad['materials']['realtime_denoises'][0][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):audio.validate(bad)


if __name__=='__main__':unittest.main()
