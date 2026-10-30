"""Experimental resources must not broaden ordinary native color trust."""
from pathlib import Path
from unittest import TestCase, mock
import hashlib
import json
import sys
import tempfile
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import native_cube
import native_lut_candidates as candidates


class CandidateTrustTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / 'owned'
        self.package.mkdir()
        self.cube = self.root / 'source.cube'
        self.cube.write_text('LUT_3D_SIZE 33\n' + '0 0 0\n' * 33**3, encoding='ascii')
        marker = dict(schema='jy14-experimental-lut33/v17', key='candidate',
                      canonical_cube_sha256=native_cube.read(self.cube).sha256)
        self.marker = self.package / candidates.MARKER
        self.marker.write_text(json.dumps(marker), encoding='utf-8')
        self.resource = dict(key='candidate', marker=marker, tree_sha256='a'*64,
                             files={'must_still_be_checked': {}})
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps(dict(resources={'candidate': self.resource})), encoding='utf-8')
        for name, value in [('CATALOG', self.catalog),
                            ('CATALOG_SHA', hashlib.sha256(self.catalog.read_bytes()).hexdigest())]:
            patch = mock.patch.object(candidates, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.node = dict(type='lut', path=self.cube.as_posix()+';'+self.package.as_posix())

    def test_exact_marker_and_cube_select_pinned_entry(self):
        self.assertEqual(candidates.entry(self.package, self.node), self.resource)

    def test_unmarked_existing_original_package_stays_outside_candidate_route(self):
        self.marker.unlink()
        self.catalog.write_bytes(b'this must not be read for an ordinary package')
        self.assertIsNone(candidates.entry(self.package, self.node))

    def test_catalog_tampering_is_rejected(self):
        self.catalog.write_bytes(self.catalog.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'catalog changed'):
            candidates.entry(self.package, self.node)

    def test_unknown_marker_is_rejected(self):
        self.marker.write_text('{"key":"not-captured"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unknown experimental'):
            candidates.entry(self.package, self.node)

    def test_native_migration_cannot_silently_change_sampler(self):
        self.node['path'] = self.cube.as_posix()+';'+(self.root/'official').as_posix()
        with self.assertRaisesRegex(ValueError, 'migrated away'):
            candidates.entry(self.package, self.node)

    def test_different_valid_cube_cannot_reuse_the_captured_atlas(self):
        self.cube.write_text('LUT_3D_SIZE 33\n'+'1 1 1\n'*33**3, encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'does not bind'):
            candidates.entry(self.package, self.node)

    def test_only_exact_full_hash_virtual_directory_can_select_an_entry(self):
        self.assertEqual(candidates.entry(self.root/('a'*64), self.node), self.resource)
        self.assertIsNone(candidates.entry(self.root/('a'*16), self.node))


class ManagedResourceSourceTests(TestCase):
    def setUp(self):
        import native_resources
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        env=mock.patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'appdata')})
        env.start();self.addCleanup(env.stop)
        payload=b'independently owned, pinned native fixture'
        files={'shader-source.txt':dict(size=len(payload),sha256=hashlib.sha256(payload).hexdigest())}
        self.resource=dict(key='filter-fixture',bucket='effects',files=files,
                           tree_sha256=native_resources.manifest_hash(files))
        self.folder=self.root/'build'
        self.relative=Path('Resources/native-av')/('lq-'+self.resource['tree_sha256'][:12])
        self.source=self.folder/self.relative
        self.source.mkdir(parents=True)
        (self.source/'shader-source.txt').write_bytes(payload)
        self.gui=candidates.gui_root(self.resource)
        self.gui.mkdir(parents=True)
        (self.gui/'shader-source.txt').write_bytes(payload)
        patch=mock.patch.object(candidates,'catalog',return_value={'resources':{'fixture':self.resource}})
        patch.start();self.addCleanup(patch.stop)

    def test_exact_managed_path_resolves_to_complete_build_owned_copy(self):
        self.assertEqual(candidates.external_build_source(self.gui,self.folder),(self.source,self.relative))

    def test_arbitrary_external_directory_does_not_gain_resource_trust(self):
        self.assertIsNone(candidates.external_build_source(self.root/'external',self.folder))

    def test_changed_gui_resource_is_rejected(self):
        (self.gui/'shader-source.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Managed standard LUT resource changed'):
            candidates.external_build_source(self.gui,self.folder)

    def test_changed_build_owned_copy_is_rejected(self):
        (self.source/'shader-source.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Build-owned standard LUT resource changed'):
            candidates.external_build_source(self.gui,self.folder)

    def test_unknown_extra_resource_file_is_rejected(self):
        (self.gui/'unreviewed.js').write_bytes(b'unknown code')
        with self.assertRaisesRegex(ValueError,'Managed standard LUT resource changed'):
            candidates.external_build_source(self.gui,self.folder)


class NamedNativeFilterTests(TestCase):
    def setUp(self):
        import native_av_plan
        import windows_vfx
        self.av=native_av_plan
        self.vfx=windows_vfx
        self.entry=candidates.by_key(candidates.variant_key('filter-gentle8-v24'))
        self.spec={'grade':{'version':2,'lut':{
            'file':str(Path(__file__).resolve()),'resource_candidate':'filter-gentle8-v24',
            'value':.55,'native_filter_name':self.entry['display_name']}}}

    def test_named_native_card_keeps_exact_reviewed_material_contract(self):
        self.av.validate_spec(self.spec,'video')
        bucket,node=self.av.nodes_for(self.spec,Path('C:/owned-test-build'))[0]
        node['id']='A'*8+'-'+'B'*4+'-'+'C'*4+'-'+'D'*4+'-'+'E'*12
        self.assertEqual(node['name'],self.entry['display_name'])
        self.assertTrue(self.vfx._shape_matches(bucket,node,self.entry))
        for name in ['other filter',None,True]:
            with self.subTest(name=name):
                self.assertFalse(self.vfx._shape_matches(bucket,{**node,'name':name},self.entry))

    def test_old_builds_do_not_gain_a_name_or_change_expected_shape(self):
        del self.spec['grade']['lut']['native_filter_name']
        self.av.validate_spec(self.spec,'video')
        _,node=self.av.nodes_for(self.spec,Path('C:/owned-test-build'))[0]
        self.assertNotIn('name',node)

    def test_name_is_not_accepted_for_ordinary_or_lut14_resources(self):
        lut=self.spec['grade']['lut']
        for variant in [None,'gentle-8']:
            with self.subTest(variant=variant):
                if variant is None:lut.pop('resource_candidate',None)
                else:lut['resource_candidate']=variant
                with self.assertRaises(ValueError):self.av.validate_spec(self.spec,'video')

    def test_unknown_name_is_rejected_before_material_creation(self):
        self.spec['grade']['lut']['native_filter_name']='arbitrary name'
        with self.assertRaisesRegex(ValueError,'Unreviewed native compatibility filter name'):
            self.av.validate_spec(self.spec,'video')
