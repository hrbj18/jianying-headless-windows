"""Staging must share data bytes without sharing editable JSON identities."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import agent_drafts
import jy14_headless as j
import media_store as media

class StagingMedia(unittest.TestCase):
    def test_explicit_saved_reopen_keeps_native_edits_and_default_stage_refuses(self):
        with tempfile.TemporaryDirectory(prefix='jy-reopen-') as tmp:
            root=Path(tmp);native=root/'draft_content.json'
            native.write_bytes(b'{"native":"edited"}')
            record={'files':{'draft_content.json':{'sha256':'old-build','size':1}}}
            with self.assertRaisesRegex(ValueError,'Existing draft differs'):
                agent_drafts.existing_snapshot(root,record)
            before=native.read_bytes()
            actual=agent_drafts.existing_snapshot(root,record,True)
            self.assertEqual(native.read_bytes(),before)
            self.assertEqual(actual,j.files_manifest(root))
            native.unlink()
            with self.assertRaisesRegex(ValueError,'no native content'):
                agent_drafts.existing_snapshot(root,record,True)
    def test_real_snapshot_preserves_manifest_and_separates_metadata(self):
        with tempfile.TemporaryDirectory(prefix='jy-stage-media-') as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            (source/'clip.mp4').write_bytes(b'original immutable media')
            (source/'meta.json').write_text('{"version":1}',encoding='utf-8')
            manifest=j.files_manifest(source)
            a=root/'first';b=root/'second'
            rows=agent_drafts.copy_build_snapshot(source,a,manifest,pool_root=root/'pool')
            agent_drafts.copy_build_snapshot(source,b,manifest,pool_root=root/'pool')
            self.assertEqual(j.files_manifest(a),manifest)
            self.assertTrue(os.path.samefile(a/'clip.mp4',b/'clip.mp4'))
            self.assertFalse(os.path.samefile(source/'clip.mp4',a/'clip.mp4'))
            self.assertFalse(os.path.samefile(a/'meta.json',b/'meta.json'))
            self.assertTrue(media.file_identity(a/'clip.mp4')['read_only'])
            (a/'meta.json').write_text('{"version":2}',encoding='utf-8')
            self.assertEqual((b/'meta.json').read_text(encoding='utf-8'),'{"version":1}')
            for directory,_,names in os.walk(root,topdown=False):
                for name in names:media._unlink(Path(directory)/name)

if __name__=='__main__':unittest.main()
