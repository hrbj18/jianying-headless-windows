"""The SDK can swallow enum errors; reject them before native dispatch."""
from pathlib import Path
from copy import deepcopy
import json,shutil,subprocess,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_dsp_graph as dsp


@unittest.skipUnless(shutil.which('node'),'Node is required for the pure transport validator')
class Transport(unittest.TestCase):
    def accepts(self,inputs):
        module=(Path(__file__).resolve().parents[1]/'engine/windows_audio_feature_client.mjs').as_uri()
        source='import {validate} from '+json.dumps(module)+';\n'
        source+='const inputs='+json.dumps(inputs,ensure_ascii=False)+';\n'
        source+='console.log(JSON.stringify(inputs.map(x=>{try{validate(x);return true;}catch{return false;}})));'
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',source],
                              capture_output=True,text=True,encoding='utf-8',check=True)
        return json.loads(result.stdout)
    def request(self,operation,params):
        return dict(endpoint=r'\\.\pipe\jy-native-feature-test',timeoutMs=1000,boundSessionId='owned',
                    request=dict(id='test',protocolVersion=1,domain='edit',operation=operation,
                                 targetId='owned',params=params))
    def test_string_native_enum_cannot_silently_truncate_the_request(self):
        good=self.request('video.setBasicColor',dict(seg_id='clip',is_keyframe=False,
                          material=dict(type=69,hsl_params=dict(hsl_color_type=1,hue=0,saturation=-30,lightness=0))))
        bad=deepcopy(good);bad['request']['params']['material']['type']='hsl'
        alias=deepcopy(good);alias['request']['params']['segId']=alias['request']['params'].pop('seg_id')
        self.assertEqual(self.accepts([good,bad,alias]),[True,False,False])
    def test_five_audio_controls_and_owned_session(self):
        good=self.request('audio.setVoiceEffect',dict(segment_id='audio',resource_id=dsp.RESOURCE_ID,
             resource_path=r'D:\owned\studio',source_platform=0,audio_effect_type=1,vc_type=0,
             audio_adjust_params=dsp.parameters()))
        bad_enum=deepcopy(good);bad_enum['request']['params']['audio_effect_type']='audio_effect'
        wrong_session=deepcopy(good);wrong_session['request']['targetId']='other'
        wrong_port=deepcopy(good);wrong_port['request']['params']['audio_adjust_params'][0]['portIndex']=9
        duplicate=deepcopy(good);duplicate['request']['params']['audio_adjust_params'][-1]=deepcopy(duplicate['request']['params']['audio_adjust_params'][0])
        self.assertEqual(self.accepts([good,bad_enum,wrong_session,wrong_port,duplicate]),[True,False,False,False,False])
    def test_effect_edit_is_flat_and_bound_to_known_parameter(self):
        good=self.request('audio.setVoiceEffectParams',dict(segment_id='audio',resource_id=dsp.RESOURCE_ID,
                parameterIndex=2,portIndex=1,effect_adjust_value=.5,is_keyframe=False))
        nested=deepcopy(good);nested['request']['params']['audioAdjustParam']={'value':.5}
        outside=deepcopy(good);outside['request']['params']['effect_adjust_value']=1.1
        self.assertEqual(self.accepts([good,nested,outside]),[True,False,False])
    def test_preview_endpoint_and_arbitrary_edit_cannot_be_used(self):
        one=self.request('audio.setVoiceEffectParams',{})
        other=deepcopy(one);other['request']['operation']='raw'
        one['endpoint']=r'\\.\pipe\jy-native-preview-test'
        self.assertEqual(self.accepts([one,other]),[False,False])


if __name__=='__main__':unittest.main()
