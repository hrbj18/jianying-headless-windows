"""Real small-file sharing, isolation and recovery; never touch user media."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import media_store as media


class MediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='jy-media-tests-')
        self.root = Path(self.scratch.name).resolve()
        self.owned = self.root / 'work'
        self.owned.mkdir()
        self.pool = self.root / 'pool'
        self.source = self.root / 'original.mp4'
        self.data = b'original video bytes\x00' * 1024
        self.source.write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def tearDown(self):
        # Deleting a read-only link must not chmod the other names of its inode.
        for directory, _, names in os.walk(self.root, topdown=False):
            for name in names:
                path = Path(directory) / name
                if path.exists():
                    media._unlink(path)
        self.scratch.cleanup()

    def materialize(self, name='clip.mp4', **kwargs):
        return media.materialize_immutable(self.source, self.owned / name, self.sha,
                                           self.pool, **kwargs)

    def test_real_hardlinks_share_pool_but_never_share_original(self):
        before = media.file_identity(self.source)
        first = self.materialize()
        second = self.materialize('other.mp4')
        self.assertEqual(first['method'], 'hardlink')
        self.assertEqual(first['pool_identity']['file_id'], second['destination_identity']['file_id'])
        self.assertNotEqual(before['file_id'], first['pool_identity']['file_id'])
        self.assertEqual(media.file_identity(self.source), before)
        self.assertTrue(first['destination_identity']['read_only'])
        self.assertFalse(second['pool_object_created'])
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_existing_conflicting_target_is_not_overwritten(self):
        path = self.owned / 'clip.mp4'
        path.write_bytes(b'other bytes')
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.materialize()
        self.assertEqual(path.read_bytes(), b'other bytes')
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_expected_hash_is_checked_before_creating_pool(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            media.materialize_immutable(self.source, self.owned / 'clip.mp4', '0' * 64, self.pool)
        self.assertFalse(self.pool.exists())

    def test_corrupt_existing_pool_is_rejected(self):
        evidence = self.materialize()
        pooled = Path(evidence['pool_object'])
        os.chmod(pooled, stat.S_IRUSR | stat.S_IWUSR)
        pooled.write_bytes(b'corrupt')
        os.chmod(pooled, stat.S_IRUSR)
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.materialize('new.mp4')
        self.assertFalse((self.owned / 'new.mp4').exists())
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_link_failure_is_recorded_as_independent_verified_copy(self):
        with patch.object(media.os, 'link', side_effect=OSError(errno.EPERM, 'no links')):
            evidence = self.materialize()
        self.assertEqual(evidence['method'], 'verified-copy-fallback')
        self.assertEqual(evidence['fallback']['errno'], errno.EPERM)
        self.assertNotEqual(evidence['destination_identity']['file_id'], evidence['pool_identity']['file_id'])
        self.assertEqual((self.owned / 'clip.mp4').read_bytes(), self.data)

    def test_private_write_isolation_preserves_original_and_store_guards(self):
        evidence = self.materialize()
        pooled = Path(evidence['pool_object'])
        other = self.materialize('other.mp4')
        isolated = media.ensure_private_copy(self.owned / 'clip.mp4', self.sha,
                                             allowed_roots=[self.owned])
        self.assertNotEqual(isolated['after']['file_id'], other['destination_identity']['file_id'])
        self.assertFalse(isolated['after']['read_only'])
        (self.owned / 'clip.mp4').write_bytes(b'edited independently')
        self.assertEqual(pooled.read_bytes(), self.data)
        self.assertTrue(media.file_identity(pooled)['read_only'])
        self.assertEqual((self.owned / 'other.mp4').read_bytes(), self.data)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_unlinking_owned_read_only_link_preserves_pool(self):
        evidence = self.materialize()
        result = media.unlink_owned_file(self.owned / 'clip.mp4', [self.owned])
        self.assertEqual(result['released_allocation_bytes'], 0)
        self.assertFalse((self.owned / 'clip.mp4').exists())
        self.assertEqual(Path(evidence['pool_object']).read_bytes(), self.data)
        self.assertTrue(media.file_identity(evidence['pool_object'])['read_only'])
        with self.assertRaisesRegex(ValueError, 'outside'):
            media.unlink_owned_file(self.source, [self.owned])

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only rename semantics')
    def test_readonly_atomic_replace_preserves_old_hardlink_guard(self):
        target = self.owned / 'target.mp4'
        alias = self.owned / 'old-alias.mp4'
        replacement = self.owned / 'replacement.mp4'
        target.write_bytes(b'old immutable media')
        os.chmod(target, stat.S_IRUSR)
        os.link(target, alias)
        old_identity = media.file_identity(alias)
        pooled = self.owned / 'new-pool-object.mp4'
        pooled.write_bytes(b'new immutable media')
        os.chmod(pooled, stat.S_IRUSR)
        os.link(pooled, replacement)
        new_identity = media.file_identity(replacement)
        media._atomic_replace(replacement, target)
        self.assertFalse(replacement.exists())
        self.assertEqual(target.read_bytes(), b'new immutable media')
        self.assertEqual(media.file_identity(target)['file_id'], new_identity['file_id'])
        self.assertEqual(alias.read_bytes(), b'old immutable media')
        self.assertEqual(media.file_identity(alias)['file_id'], old_identity['file_id'])
        self.assertTrue(media.file_identity(alias)['read_only'])
        self.assertTrue(media.file_identity(target)['read_only'])

    def test_full_hash_scan_distinguishes_same_size_media(self):
        (self.owned / 'one.mp4').write_bytes(self.data)
        (self.owned / 'two.mp4').write_bytes(self.data)
        (self.owned / 'three.mp4').write_bytes(b'Z' * len(self.data))
        (self.owned / 'not-media.bin').write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1)
        self.assertEqual(scan['summary']['paths'], 3)
        self.assertEqual(scan['summary']['unique_content_hashes'], 2)
        self.assertEqual(scan['summary']['unique_file_ids'], 3)
        self.assertFalse(scan['mutation_performed'])

    def test_dedupe_preserves_paths_bytes_and_uses_one_real_file_id(self):
        for name in ['one.mp4', 'two.mp4']:
            (self.owned / name).write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1)
        log = self.root / 'dedupe.jsonl'
        result = media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        self.assertEqual(result['after']['paths'], 2)
        self.assertEqual(result['after']['unique_file_ids'], 1)
        self.assertGreater(result['verified_net_allocation_reduction_bytes'], 0)
        for name in ['one.mp4', 'two.mp4']:
            self.assertEqual((self.owned / name).read_bytes(), self.data)
        self.assertEqual(self.source.read_bytes(), self.data)
        resumed = media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        self.assertTrue(all(row['method'] == 'already-shared' for row in resumed['files']))
        self.assertEqual(resumed['verified_net_allocation_reduction_bytes'], 0)

    def test_changed_same_size_content_aborts_without_overwriting(self):
        path = self.owned / 'one.mp4'
        path.write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1)
        replacement = b'Z' * len(self.data)
        path.write_bytes(replacement)
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            media.dedupe_manifest(scan, [self.owned], self.root / 'log.jsonl', pool_root=self.pool)
        self.assertEqual(path.read_bytes(), replacement)

    def test_manifest_cannot_expand_the_explicit_scope(self):
        scan = media.scan_media([self.owned], min_bytes=1)
        scan['files'] = [{'path': str(self.source), 'sha256': self.sha, **media.file_identity(self.source)}]
        with self.assertRaisesRegex(ValueError, 'outside'):
            media.dedupe_manifest(scan, [self.owned], self.root / 'log.jsonl', pool_root=self.pool)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_protected_source_is_omitted_and_not_mutated_by_a_forged_manifest(self):
        path = self.owned / 'protected.mp4'
        path.write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1, protected_roots=[path])
        self.assertEqual(scan['files'], [])
        scan['files'] = [{'path': str(path), 'sha256': self.sha, **media.file_identity(path)}]
        with self.assertRaisesRegex(ValueError, 'Protected'):
            media.dedupe_manifest(scan, [self.owned], self.root / 'log.jsonl', pool_root=self.pool)

    def test_symlink_or_reparse_sources_are_not_followed(self):
        alias = self.owned / 'alias.mp4'
        try:
            alias.symlink_to(self.source)
        except OSError as error:
            self.skipTest('Symlink creation unavailable: ' + str(error))
        try:
            with self.assertRaisesRegex(ValueError, 'Symlink/reparse'):
                media.materialize_immutable(alias, self.owned / 'copy.mp4', self.sha, self.pool)
            scan = media.scan_media([self.owned], min_bytes=1)
            self.assertEqual(scan['files'], [])
        finally:
            alias.unlink()

    def test_interruption_after_atomic_replace_can_resume_from_the_real_identity(self):
        path = self.owned / 'clip.mp4'
        path.write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1)
        log = self.root / 'log.jsonl'
        original_replace = media._atomic_replace

        def interrupted(temporary, destination):
            original_replace(temporary, destination)
            raise RuntimeError('interruption after replacement')

        with patch.object(media, '_atomic_replace', side_effect=interrupted), self.assertRaises(RuntimeError):
            media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        self.assertEqual(path.read_bytes(), self.data)
        result = media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        self.assertEqual(result['files'][0]['method'], 'already-shared')
        self.assertEqual(result['after']['unique_file_ids'], 1)
        self.assertTrue(json.loads(log.read_text(encoding='utf-8').splitlines()[-1])['result']['full_hash_verification'])

    def test_torn_journal_tail_and_owned_orphan_link_are_recovered(self):
        path = self.owned / 'clip.mp4'
        path.write_bytes(self.data)
        scan = media.scan_media([self.owned], min_bytes=1)
        log = self.root / 'log.jsonl'
        result = media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        prepare = next(json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()
                       if json.loads(line)['event'] == 'prepare')
        temporary = Path(prepare['temporary'])
        os.link(result['files'][0]['pool_object'], temporary)
        with log.open('ab') as stream:
            stream.write(b'{"event":"torn')
        resumed = media.dedupe_manifest(scan, [self.owned], log, pool_root=self.pool)
        self.assertEqual(resumed['recovered_temporary_links'], [str(temporary)])
        self.assertFalse(temporary.exists())
        self.assertEqual(path.read_bytes(), self.data)

    def test_dead_pool_creator_partial_copy_is_recovered_without_changing_original(self):
        media._pool(self.owned / 'clip.mp4', self.pool)
        target = self.pool / 'sha256' / self.sha[:2] / self.sha
        target.parent.mkdir(parents=True)
        temporary = target.with_suffix('.tmp-' + 'a' * 32)
        temporary.write_bytes(b'partial copy')
        lock = target.with_suffix('.lock')
        lock.write_text(json.dumps({'pid': 2147483647, 'temporary': str(temporary)}), encoding='utf-8')
        self.materialize()
        self.assertFalse(temporary.exists())
        self.assertFalse(lock.exists())
        self.assertEqual(target.read_bytes(), self.data)
        self.assertEqual(self.source.read_bytes(), self.data)


if __name__ == '__main__':
    unittest.main()
