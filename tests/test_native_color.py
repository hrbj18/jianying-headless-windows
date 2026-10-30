"""A valid HSL node must use the resource which actually changes pixels."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_color as color


def fixture():
    node=dict(id='hsl',type='hsl',hsl_color_type=1,hue=0,saturation=-30,lightness=0,
              version='1',path='merge',lumi_hub_path='merge')
    return dict(materials=dict(hsl=[node]),tracks=[dict(type='video',segments=[
        dict(material_id='video',enable_hsl=True,extra_material_refs=['hsl'])])])


class Color(unittest.TestCase):
    def test_saved_white_balance_omitted_zero_is_valid_but_explicit_invalid_values_fail(self):
        for kind in ('temperature','tone'):
            node={'id':'white','type':kind,'path':'merge','lumi_hub_path':'merge/lumi_hub_path'}
            timeline={'materials':{'effects':[node]},'tracks':[{'type':'video','segments':[
                {'material_id':'video','extra_material_refs':['white']}]}]}
            self.assertEqual(self.validate(timeline)['materials'],1)
            for value in (None,True,1.01,float('nan')):
                invalid=deepcopy(timeline);invalid['materials']['effects'][0]['value']=value
                with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):self.validate(invalid)
    def test_normal_native_white_balance_v3_empty_color_match_does_not_enable_auto_adjustment(self):
        node={'id':'white','type':'temperature','version':'v3','value':.08,'color_match_info':{},
              'path':'merge','lumi_hub_path':'merge/lumi_hub_path'}
        timeline={'materials':{'effects':[node]},'tracks':[{'type':'video','segments':[
            {'material_id':'video','extra_material_refs':['white']}]}]}
        self.assertEqual(self.validate(timeline)['materials'],1)
        node['color_match_info']={'enabled':True}
        with self.assertRaises(ValueError):self.validate(timeline)
    def test_native_saved_cube_placeholder_resolves_only_on_a_copy(self):
        from jy14_headless import DRAFT_PATH_TOKEN
        root=Path('D:/owned-draft')
        node={'id':'lut','type':'lut','path':DRAFT_PATH_TOKEN+'Resources/a.cube;'+DRAFT_PATH_TOKEN+'Resources/grade',
              'lumi_hub_path':DRAFT_PATH_TOKEN+'Resources/grade/lumi_hub_path'}
        source={'materials':{'effects':[node]}};original=deepcopy(source)
        resolved=color.resolve_timeline_paths(source,root)['materials']['effects'][0]
        self.assertEqual(source,original)
        self.assertEqual(Path(resolved['path'].split(';')[0]),root/'Resources/a.cube')
        self.assertEqual(Path(resolved['lumi_hub_path']),root/'Resources/grade/lumi_hub_path')
        source['materials']['effects'][0]['path']='##_draftpath_placeholder_unknown_##/a.cube;C:/grade'
        with self.assertRaises(ValueError):color.resolve_timeline_paths(source,root)
    def test_native_selected_lut_rebases_independent_cube_and_shader_dependencies(self):
        root=Path('C:/verified-collection')
        node={'type':'lut','path':'C:/native-lut/Alexa LogC to Rec709.cube;D:/native-merge',
              'lumi_hub_path':str(root/'lumi_hub_path')}
        self.assertEqual(color.resource_root(node),root)
        self.assertEqual(dict(color.lut_sources(node)),{'cube':Path('C:/native-lut'),'feature':Path('D:/native-merge')})
        color.rebase_node(node,Path('C:/job/Resources/collection'))
        self.assertEqual([Path(p) for p in node['path'].split(';')],
            [Path('C:/job/Resources/collection-lut-cube/Alexa LogC to Rec709.cube'),
             Path('C:/job/Resources/collection-lut-feature')])
        self.assertEqual(Path(node['lumi_hub_path']),Path('C:/job/Resources/collection/lumi_hub_path'))
        self.assertNotIn('\\',node['path'])
    def test_native_lut_json_parse_failure_cannot_pass_as_completed_encoding(self):
        with self.assertRaisesRegex(ValueError,'LUT merged-parameter JSON'):
            color.validate_render_log('JY_WINDOWS_NATIVE_EXPORT_DONE\naddLutEnableStatus:5675 parse json error')
    def validate(self,timeline):
        with patch.object(color,'verify_resource'):
            return color.validate(timeline)
    def test_actual_merged_hsl_resource_is_selected(self):
        t=fixture();before=deepcopy(t)
        self.assertEqual(self.validate(t)['packages'],['color/merge']);self.assertEqual(t,before)
    def test_shared_package_is_hashed_once_per_validation_without_skipping_node_checks(self):
        t=fixture();other=deepcopy(t['materials']['hsl'][0]);other['id']='hsl2'
        t['materials']['hsl'].append(other);t['tracks'][0]['segments'][0]['extra_material_refs'].append('hsl2')
        with patch.object(color,'verify_resource') as verify:
            self.assertEqual(color.validate(t)['materials'],2)
            self.assertEqual(verify.call_count,1)
        other['saturation']=101
        with patch.object(color,'verify_resource'),self.assertRaises(ValueError):color.validate(t)

    def test_wheels_require_correct_component_range_and_explicit_enable(self):
        node=dict(id='wheel',type='primary_color_wheels',path='merge',lumi_hub_path='merge/lumi_hub_path',
                  panel='',lift={'red':.25},gamma={},gain={},offset={},intensity=1)
        t=dict(materials={'primary_color_wheels':[node]},tracks=[dict(type='video',segments=[
            dict(material_id='video',enable_color_wheels=True,extra_material_refs=['wheel'])])])
        self.assertEqual(self.validate(t)['materials'],1)
        compact=deepcopy(t);compact['materials']['primary_color_wheels'][0]['panel']='adjust_collection'
        compact['materials']['primary_color_wheels'][0].pop('intensity')
        compact['tracks'][0]['segments'][0].pop('enable_color_wheels')
        self.assertEqual(self.validate(compact)['materials'],1)
        for value in [True,1.01,float('nan')]:
            invalid=deepcopy(t);invalid['materials']['primary_color_wheels'][0]['lift']['red']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.validate(invalid)
        t['tracks'][0]['segments'][0]['enable_color_wheels']=False
        with self.assertRaisesRegex(ValueError,'disabled'):self.validate(t)

    def test_lut_rebases_both_paths_and_preserves_verified_cube_identity(self):
        root=Path('D:/grade');node=dict(type='lut',path=str(root/color.LUT_CUBE)+';'+str(root/color.LUT_CONFIG.parent),
                                      lumi_hub_path=str(root/'lumi_hub_path'))
        self.assertEqual(color.resource_root(node),root)
        mapping=color.rebased_paths(node,Path('C:/snapshot'))
        self.assertEqual(color.resource_root(node),root)
        color.rebase_node(node,Path('C:/snapshot'))
        self.assertEqual(color.resource_root(node),Path('C:/snapshot'))
        self.assertIn((Path('C:/snapshot')/color.LUT_CUBE).as_posix(),node['path'])
        node['path']=node['path'].replace('Alexa LogC to Rec709.cube','unknown.cube')
        with self.assertRaisesRegex(ValueError,'cube identity'):color.resource_root(node)

    def test_native_scene_load_failure_cannot_be_successful_export(self):
        with self.assertRaisesRegex(ValueError,'despite completed encoding'):
            color.validate_render_log('JY_WINDOWS_NATIVE_EXPORT_DONE\nCannot load filter scene with bad.cube')
        color.validate_render_log('JY_WINDOWS_NATIVE_EXPORT_DONE\nNormal feature scene loaded')
    def test_native_gui_default_omission_and_nested_lumi_path(self):
        t=fixture();n=t['materials']['hsl'][0];n.pop('hue');n.pop('lightness')
        n['lumi_hub_path']='merge/lumi_hub_path';t['tracks'][0]['segments'][0].pop('enable_hsl')
        self.assertEqual(self.validate(t)['packages'],['color/native-collection-7416258989467374091'])
        color.rebase_node(n,'snapshot')
        self.assertEqual(Path(n['lumi_hub_path']),Path('snapshot/lumi_hub_path'))
        self.assertEqual(Path(n['path']),Path('snapshot'))
    def test_standalone_hsl_packages_cannot_pass_as_working_adjustment(self):
        for path in ['',None,'other']:
            t=fixture();t['materials']['hsl'][0]['lumi_hub_path']=path
            with self.subTest(path=path),self.assertRaises(ValueError):self.validate(t)
    def test_native_integer_channels_and_values_are_validated(self):
        for field,value in [('hue',.5),('saturation',True),('saturation',101),
                            ('hsl_color_type',0),('hsl_color_type',True),('version','0')]:
            t=fixture();t['materials']['hsl'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.validate(t)
    def test_disabled_or_orphan_color_is_rejected(self):
        for disabled in [False,True]:
            t=fixture()
            if disabled:t['tracks'][0]['segments'][0]['enable_hsl']=False
            else:t['tracks'][0]['segments'][0]['extra_material_refs']=[]
            with self.subTest(disabled=disabled),self.assertRaises(ValueError):self.validate(t)


class BuiltinColorRevision(unittest.TestCase):
    def test_exact_builtin_copy_is_accepted_but_changed_or_extra_files_are_rejected(self):
        import tempfile,json
        import native_resources as resources
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);package=root/'ascii-snapshot';package.mkdir()
            (package/'shader.frag').write_text('captured installed shader',encoding='ascii')
            files=resources.tree_manifest(package)
            primary={'key':'color/native-collection-7416258989467374091',
                     'files':{'shader.frag':{'size':1,'sha256':'a'*64}},'tree_sha256':'b'*64,
                     'native_builtin_revisions':[{'revision':'pinned-built-in',
                         'files':files,'tree_sha256':resources.manifest_hash(files)}]}
            catalog=root/'catalog.json'
            catalog.write_text(json.dumps({'resources':{primary['key']:primary}}),encoding='utf-8')
            node={'type':'hsl','path':str(package),'lumi_hub_path':str(package/'lumi_hub_path')}
            with patch.object(color,'CATALOG',catalog):
                selected=color.entry_for_node('hsl',node)
                self.assertEqual(selected['revision'],'pinned-built-in')
                color.verify_resource(package,selected)
                (package/'extra.lua').write_text('unreviewed code',encoding='ascii')
                with self.assertRaisesRegex(ValueError,'Color package bytes differ'):
                    color.verify_resource(package,color.entry_for_node('hsl',node))
                (package/'extra.lua').unlink()
                (package/'shader.frag').write_text('changed shader',encoding='ascii')
                with self.assertRaisesRegex(ValueError,'Color package bytes differ'):
                    color.verify_resource(package,color.entry_for_node('hsl',node))


if __name__=='__main__':unittest.main()
