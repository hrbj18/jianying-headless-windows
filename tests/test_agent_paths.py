"""Storage and homepage index can be on different volumes; ambiguity is explicit."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import local_config

class DraftPaths(unittest.TestCase):
    def test_custom_storage_and_separate_index_are_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);storage=root/'D-store';index=root/'C-index/root_meta_info.json'
            with patch.object(local_config,'load_config',return_value={'draft_root':str(storage),'draft_index_path':str(index)}):
                self.assertEqual(local_config.draft_locations(),(storage,index,'configured'))
    def test_unique_existing_index_parent_is_used_without_assuming_appdata(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);storage=root/'store';(storage/'one').mkdir(parents=True)
            index=root/'root_meta_info.json';index.write_text(json.dumps({'all_draft_store':[{'draft_fold_path':str(storage/'one')}]}))
            with patch.object(local_config,'load_config',return_value={'draft_index_path':str(index)}):
                self.assertEqual(local_config.draft_locations(),(storage.resolve(),index,'editor-index'))
    def test_multiple_live_roots_require_configuration(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);drafts=[root/'a/one',root/'b/two']
            for d in drafts:d.mkdir(parents=True)
            index=root/'root_meta_info.json';index.write_text(json.dumps({'all_draft_store':[{'draft_fold_path':str(d)} for d in drafts]}))
            with patch.object(local_config,'load_config',return_value={'draft_index_path':str(index)}):
                with self.assertRaisesRegex(ValueError,'Multiple draft roots'):local_config.draft_locations()

if __name__=='__main__':unittest.main()
