"""Plan requests must survive as editable native parameters and owned assets."""
from pathlib import Path
from copy import deepcopy
import sys,tempfile,unittest,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_av_plan as av
import native_dsp_graph as dsp
from runtime_profiles import WINDOWS_1147_PROFILE


def material_index(materials):
    return {n['id']:(bucket,n) for bucket,nodes in materials.items() for n in nodes}


class NativeAVPlan(unittest.TestCase):
    def test_custom_cube_binds_original_and_canonical_hashes_with_owned_posix_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'owned.cube'
            original=('TITLE "My own SDR"\nLUT_3D_SIZE 33\n'+'0.1 0.2 0.3\n'*35937).encode('ascii')
            source.write_bytes(original)
            spec={'grade':{'version':2,'lut':{'file':str(source),'value':.4}}}
            plan={'tracks':[{'segments':[spec]}]}
            av.bind_lut_sources(plan);av.validate_spec(spec,'video')
            lut=spec['grade']['lut'];self.assertNotEqual(lut['sha256'],lut['source_sha256'])
            self.assertEqual(source.read_bytes(),original)
            self.assertIs(spec['grade']['hsl']['red']['interacting'],True)
            target=root/'future-project';node=next(n for _,n in av.nodes_for(spec,target) if n['type']=='lut')
            cube,feature=node['path'].split(';')
            self.assertEqual(Path(cube).name,lut['sha256']+'.cube')
            self.assertTrue(Path(cube).is_relative_to(target/'Resources'))
            self.assertNotIn('\\',node['path'])
            self.assertEqual(av.lut_project_records(plan,target)[0]['path'],cube)
            self.assertIn('lut/cube/'+lut['sha256'],av.needed(plan))
    def test_lut_binding_preserves_explicit_hsl_mode_and_legacy_plan(self):
        spec={'grade':{'version':2,'hsl':{'red':{'saturation':-5,'interacting':False}},
                       'lut':{'preset':'alexa-logc33'}}}
        legacy={'grade':{'version':2,'lut':{'preset':'alexa-logc33','native_package_version':1}}}
        av.bind_lut_sources({'tracks':[{'segments':[spec,legacy]}]})
        self.assertIs(spec['grade']['hsl']['red']['interacting'],False)
        self.assertEqual(spec['grade']['hsl']['red']['saturation'],-5)
        self.assertNotIn('hsl',legacy['grade'])
    def test_new_preset_build_uses_complete_lut_package_but_legacy_plan_remains_verifiable(self):
        plan={'tracks':[{'segments':[{'grade':{'version':2,'lut':{'preset':'alexa-logc33'}}}]}]}
        self.assertEqual(len(av.needed(plan)),1)
        av.bind_lut_sources(plan)
        self.assertIn('lut/preset-alexa-logc33',av.needed(plan))
    def test_lut_project_index_is_scoped_to_owned_resources_and_tamper_rejected(self):
        plan={'tracks':[{'segments':[{'grade':{'version':2,'lut':{'preset':'alexa-logc33'}}}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);target=folder/'future-draft'
            records=av.lut_project_records(plan,target)
            self.assertEqual(set(records[0]),{'title','path','originPath','imagePath'})
            self.assertTrue(Path(records[0]['path']).is_relative_to(target/'Resources'))
            index=folder/av.LUT_PROJECT_INDEX;index.parent.mkdir(parents=True)
            index.write_text(json.dumps(records),encoding='utf-8')
            av.verify_lut_project_index(plan,folder,target)
            records[0]['path']=str(folder/'unrelated.cube')
            index.write_text(json.dumps(records),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'differs from the plan'):
                av.verify_lut_project_index(plan,folder,target)
    def test_lut_is_native_material_with_two_owned_paths_and_explicit_enable(self):
        spec={'grade':{'version':2,'lut':{'preset':'alexa-logc33','value':.5}}}
        av.validate_spec(spec,'video');segment={'material_id':'video'};materials={}
        av.apply(segment,materials,spec,'video',Path('D:/draft'))
        node=materials['effects'][0]
        self.assertEqual(node['type'],'lut');self.assertEqual(node['value'],.5)
        self.assertEqual(len(node['path'].split(';')),2)
        self.assertTrue(segment['enable_lut'])
        av.verify(segment,material_index(materials),spec,'video',Path('D:/draft'))
    def test_wheel_group_retains_all_native_components_and_enable_flag(self):
        for mode,group in [('primary','lift'),('log','shadow')]:
            spec={'grade':{'version':2,'wheels':{'mode':mode,group:{'red':.25}}}}
            av.validate_spec(spec,'video');segment={'material_id':'video'};materials={}
            av.apply(segment,materials,spec,'video',Path('D:/draft'))
            node=materials[mode+'_color_wheels'][0]
            self.assertEqual(node[group]['red'],.25)
            self.assertEqual(node[group]['luma'],0)
            self.assertEqual(node['intensity'],1)
            self.assertTrue(segment['enable_color_wheels'])
            av.verify(segment,material_index(materials),spec,'video',Path('D:/draft'))
            node[group]['blue']=.1
            with self.assertRaisesRegex(ValueError,'parameter differs'):
                av.verify(segment,material_index(materials),spec,'video',Path('D:/draft'))
    def test_combined_grade_remains_per_parameter_native_materials(self):
        spec={'grade':{'temperature':.1,'tint':-.03,'hsl':{'red':{'saturation':-20}},
                       'curves':{'red':av._identity_curve()}}}
        av.validate_spec(spec,'video');segment={'material_id':'video'};materials={}
        av.apply(segment,materials,spec,'video',Path('D:/test-draft'))
        self.assertEqual(len(segment['extra_material_refs']),4)
        self.assertEqual(materials['hsl'][0]['saturation'],-20)
        for nodes in materials.values():
            for node in nodes:self.assertEqual(node['path'],node['lumi_hub_path'])
        av.verify(segment,material_index(materials),spec,'video',Path('D:/test-draft'))
        materials['hsl'][0]['saturation']=0
        with self.assertRaisesRegex(ValueError,'parameter differs'):
            av.verify(segment,material_index(materials),spec,'video',Path('D:/test-draft'))
    def test_studio_and_denoise_preserve_separate_native_effects(self):
        spec={'audio_processing':{'studio':{'threshold':-24,'ratio':4},'denoise':{'rate':.35}}}
        segment={'material_id':'voice'};materials={'audios':[{'id':'voice'}]}
        av.validate_spec(spec,'audio');av.apply(segment,materials,spec,'audio',Path('D:/test-draft'))
        self.assertEqual(materials['audios'][0]['check_flag'],3)
        self.assertEqual(len(materials['audio_effects'][0]['audio_adjust_params']),5)
        self.assertTrue(materials['realtime_denoises'][0]['is_denoise'])
        av.verify(segment,material_index(materials),spec,'audio',Path('D:/test-draft'))
        materials['audios'][0]['check_flag']=1
        with self.assertRaisesRegex(ValueError,'not enabled'):
            av.verify(segment,material_index(materials),spec,'audio',Path('D:/test-draft'))
    def test_gui_grade_version_preserves_legacy_and_uses_native_color_key(self):
        legacy=av.nodes_for({'grade':{'hsl':{'red':{'saturation':-8}}}},Path('D:/draft'))[0][1]
        native=av.nodes_for({'grade':{'version':2,'hsl':{'red':{'saturation':-8}}}},Path('D:/draft'))[0][1]
        self.assertEqual(legacy['custom_color'],'')
        self.assertEqual(native['custom_color'],'#FFE64444')
        self.assertEqual(native['resource_id'],'7416258989467374091')
        self.assertEqual(Path(native['lumi_hub_path']),Path(native['path'])/'lumi_hub_path')
    def test_full_studio_chain_keeps_five_parameters_in_two_native_categories(self):
        spec={'audio_processing':{'studio_chain':{'gain':2,'frequency':300,'threshold':-18,'ratio':3,'ceiling':-3}}}
        segment={'material_id':'voice'};materials={'audios':[{'id':'voice'}]}
        av.validate_spec(spec,'audio');av.apply(segment,materials,spec,'audio',Path('D:/draft'))
        nodes=materials['audio_effects']
        self.assertEqual([n['sub_type'] for n in nodes],[0,1])
        self.assertEqual([len(n['audio_adjust_params']) for n in nodes],[2,3])
        self.assertEqual(sum(len(n['audio_adjust_params']) for n in nodes),5)
        self.assertEqual(len({n['constant_material_id'] for n in nodes}),2)
        self.assertTrue(all(n['constant_material_id']==n['id'] for n in nodes))
        av.verify(segment,material_index(materials),spec,'audio',Path('D:/draft'))
    def test_wrong_track_unknown_fields_bool_and_nonunity_audio_are_rejected(self):
        for kind,spec in [('audio',{'grade':{'temperature':.1}}),
                          ('video',{'audio_processing':{'studio':{}}}),
                          ('video',{'grade':{'hsl':{'red':{'saturation':True}}}}),
                          ('video',{'grade':{'unsupported_lut':'file'}}),
                          ('audio',{'audio_processing':{'studio':{'gain':30}}}),
                          ('audio',{'speed':2,'audio_processing':{'denoise':{}}})]:
            with self.subTest(kind=kind,spec=spec),self.assertRaises(ValueError):av.validate_spec(spec,kind)
    def test_studio_dependency_is_prepared_and_verifies_without_downloads(self):
        plan={'tracks':[{'segments':[{'audio_processing':{'studio':{}}}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            runtime={'runtime_profile':WINDOWS_1147_PROFILE}
            records=av.prepare(plan,Path(tmp),runtime);av.verify_files(records,Path(tmp),plan)
            self.assertEqual(records[0]['key'],'audio/local-studio')
            (Path(tmp)/av.RELATIVE['audio/local-studio']/'extra.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'bytes changed'):av.verify_files(records,Path(tmp),plan)
    def test_resource_record_removal_or_wrong_runtime_is_rejected(self):
        plan={'tracks':[{'segments':[{'audio_processing':{'studio':{}}}]}]}
        with self.assertRaisesRegex(ValueError,'records differ'):av.verify_files([],Path('D:/tmp'),plan)
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'11.4.7'):
            av.prepare(plan,Path(tmp),{'runtime_profile':'different-runtime'})
    def test_ordinary_plan_needs_no_new_resource_or_parameter(self):
        plan={'tracks':[{'segments':[{}]}]}
        self.assertEqual(av.prepare(plan,Path('unused'),{}),[])
        av.verify_files([],Path('unused'),plan)
        av.verify({'material_id':'audio'}, {'audio':('audios',{'id':'audio'})}, {},'audio',Path('unused'))


if __name__=='__main__':unittest.main()
