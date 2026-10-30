from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_adjustment_track as adjustment
import native_color


class NativeAdjustmentTrackTests(unittest.TestCase):
    def setUp(self):
        self.doc=json.loads((Path(__file__).parent/'fixtures/native_curve_adjustment.json').read_bytes())
        self.segment=self.doc['tracks'][1]['segments'][0]
        self.entry={'key':'color/native-collection-7416258989467374091',
                    'revision':'installed-default-11.4.7.14462','tree_sha256':'a'*64}
        for name,replacement in [('entry_for_node',lambda *args:self.entry),('verify_resource',lambda *args:None)]:
            mocked=patch.object(native_color,name,replacement);mocked.start();self.addCleanup(mocked.stop)

    def test_validation_projection_never_removes_nodes_from_the_render_input(self):
        before=deepcopy(self.doc);report,projection=adjustment.project(self.doc)
        self.assertEqual(self.doc,before)
        self.assertEqual(report['tracks'],1)
        self.assertEqual(len(self.doc['materials']['effects']),3)
        self.assertEqual(projection['materials']['effects'],[])
        self.assertEqual(len(projection['tracks']),1)

    def test_enabling_any_automatic_algorithm_is_rejected(self):
        for field in ('enable_smart_color_adjust','enable_color_match_adjust','enable_color_correct_adjust',
                      'enable_hsl','enable_hsl_curves','enable_adjust','enable_lut'):
            with self.subTest(field=field):
                doc=deepcopy(self.doc);doc['tracks'][1]['segments'][0][field]=True
                with self.assertRaisesRegex(ValueError,'Only complete curves'):adjustment.project(doc)

    def test_shared_material_cannot_be_hidden_from_the_regular_video_validator(self):
        self.doc['tracks'][0]['segments'][0]['extra_material_refs']=[self.segment['extra_material_refs'][0]]
        with self.assertRaisesRegex(ValueError,'must not alias'):adjustment.project(self.doc)

    def test_virtual_build_root_is_resolved_before_exact_resource_verification(self):
        before=deepcopy(self.doc);owned=Path('C:/actual-verified-snapshot')
        with patch.object(native_color,'verify_resource') as verify:
            adjustment.project(self.doc,resolve_resource=lambda path:owned)
        self.assertEqual(verify.call_args.args[0],owned)
        self.assertEqual(self.doc,before)

    def test_inactive_marker_is_preserved_only_for_the_fixed_native_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            node=next(n for n in self.doc['materials']['effects'] if n['type']=='color_match')
            markers=adjustment.inactive_feature_markers(self.doc,Path(temporary))
            self.assertEqual(markers,{node['id']:node['color_match_info']['source_feature_path']})
            node['color_match_info']['source_feature_path']='C:/unreviewed/feature.match'
            with self.assertRaises(ValueError):adjustment.inactive_feature_markers(self.doc,Path(temporary))

    def test_materialized_feature_is_not_silently_exempted_from_dependency_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'color_match';folder.mkdir()
            (folder/'color_match_source_feature_1.match').write_bytes(b'real feature requires its own hash')
            with self.assertRaisesRegex(ValueError,'own verified dependency stager'):
                adjustment.inactive_feature_markers(self.doc,root)


if __name__=='__main__':unittest.main()
