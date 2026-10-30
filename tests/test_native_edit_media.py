"""Saved-edit snapshots share only declared media, preserving writable metadata."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import media_store
import native_edit as edit


class SavedEditMediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jy-edit-media-')
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'saved-draft'
        self.resource = self.source / 'Resources' / 'native-local-file.mp4'
        self.resource.parent.mkdir(parents=True)
        self.resource.write_bytes(b'original source media' * 1024)
        self.metadata = self.source / 'draft_meta_info.json'
        self.metadata.write_bytes(b'original metadata')
        self.timeline = {'id': 'timeline', 'materials': {'videos': [
            {'id': 'clip', 'path': str(self.resource)}]}}
        self.pool = self.root / 'pool'

    def tearDown(self):
        for directory, _, names in os.walk(self.root, topdown=False):
            for name in names:
                path = Path(directory) / name
                if path.exists():
                    media_store._unlink(path)
        self.temporary.cleanup()

    def snapshot(self, name='copy'):
        destination = self.root / name
        with patch.object(edit.j.nd, 'IS_WINDOWS', True), \
                patch.object(media_store, 'default_pool', return_value=self.pool):
            evidence = edit.copy_source_snapshot(self.source, destination,
                                                 edit.j.files_manifest(self.source), self.timeline)
        return destination, evidence

    def test_declared_media_share_pool_metadata_is_independent_and_writable(self):
        destination, evidence = self.snapshot()
        copied = destination / self.resource.relative_to(self.source)
        self.assertEqual(evidence[0]['method'], 'hardlink')
        self.assertNotEqual(media_store.file_identity(copied)['file_id'],
                            media_store.file_identity(self.resource)['file_id'])
        copied_meta = destination / self.metadata.name
        edit.write_owned(copied_meta, b'new metadata')
        self.assertEqual(self.metadata.read_bytes(), b'original metadata')
        self.assertEqual(copied_meta.read_bytes(), b'new metadata')
        self.assertFalse(media_store.file_identity(copied_meta)['read_only'])
        second, second_evidence = self.snapshot('another-copy')
        self.assertEqual(evidence[0]['destination_identity']['file_id'],
                         second_evidence[0]['destination_identity']['file_id'])
        self.assertEqual(edit.j.files_manifest(self.source)[str(self.resource.relative_to(self.source))]['sha256'],
                         edit.j.nd.digest(second / self.resource.relative_to(self.source)))

    def test_undeclared_files_are_copied_independently(self):
        auxiliary = self.source / 'Resources' / 'user-data.json'
        auxiliary.write_bytes(b'editable auxiliary')
        destination, _ = self.snapshot()
        copied = destination / auxiliary.relative_to(self.source)
        self.assertNotEqual(media_store.file_identity(copied)['file_id'],
                            media_store.file_identity(auxiliary)['file_id'])
        copied.write_bytes(b'edited auxiliary')
        self.assertEqual(auxiliary.read_bytes(), b'editable auxiliary')

    def test_generic_metadata_writer_refuses_shared_media(self):
        destination, evidence = self.snapshot()
        copied = destination / self.resource.relative_to(self.source)
        with self.assertRaisesRegex(ValueError, 'cannot modify a shared file'):
            edit.write_owned(copied, b'incidental overwrite')
        self.assertEqual(copied.read_bytes(), self.resource.read_bytes())
        self.assertEqual(edit.j.nd.digest(Path(evidence[0]['pool_object'])), edit.j.nd.digest(self.resource))

    def test_missing_declared_owned_media_fails_before_copying(self):
        self.timeline['materials']['videos'][0]['path'] = str(self.source / 'Resources' / 'missing.mp4')
        with self.assertRaisesRegex(ValueError, 'missing from the verified'):
            self.snapshot()
        self.assertFalse((self.root / 'copy').exists())


if __name__ == '__main__':
    unittest.main()
