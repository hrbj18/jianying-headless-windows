"""Compatibility construction must fail before writing for unreviewed inputs."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_transition_compat as compat


class TransitionCompatibilityAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-transition-compat-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.white = self.root / 'white'; self.white.mkdir()
        self.original = self.root / 'original'; self.original.mkdir()
        (self.white / 'config.json').write_bytes(b'{"scene":"fixture"}')
        (self.original / 'config.json').write_bytes(b'{"effect":"fixture"}')
        self.out = self.root / 'out'

    def admit_fixture_sources(self):
        # Only the two source identities are replaced with actual fixture hashes.
        # The real tree scanner and the production write order still run.
        self.enterContext(patch.object(compat, 'WHITE_TREE',
            compat.manifest_hash(compat.tree_manifest(self.white))))
        self.enterContext(patch.dict(compat.ORIGINAL_TREES, {'dissolve':
            compat.manifest_hash(compat.tree_manifest(self.original))}))

    def test_unreviewed_resource_tree_rejected_without_output(self):
        for kind in compat.ORIGINAL_IDS:
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'fingerprint differs'):
                compat.build(kind, self.white, self.original, self.out)
            self.assertFalse(self.out.exists())
        self.assertEqual((self.white / 'config.json').read_bytes(), b'{"scene":"fixture"}')
        self.assertEqual((self.original / 'config.json').read_bytes(), b'{"effect":"fixture"}')

    def test_changed_adapter_rejected_before_copy(self):
        self.admit_fixture_sources()
        for kind in ('dissolve', 'slide-left', 'slide-right'):
            with self.subTest(kind=kind), patch.dict(compat.ORIGINAL_TREES, {
                    kind: compat.manifest_hash(compat.tree_manifest(self.original))}), \
                    patch.dict(compat.ADAPTER_HASHES, {'dissolve': '0' * 64}):
                with self.assertRaisesRegex(ValueError, 'adapter fingerprint changed'):
                    compat.build(kind, self.white, self.original, self.out)
            self.assertFalse(self.out.exists())

    def test_output_nested_in_either_source_rejected(self):
        self.admit_fixture_sources()
        for parent in (self.white, self.original):
            out = parent / 'would-mutate-original'
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'outside both'):
                compat.build('dissolve', self.white, self.original, out)
            self.assertFalse(out.exists())

    def test_existing_or_relative_output_rejected(self):
        for out in (self.white, Path('relative-compat-output')):
            with self.subTest(out=out), self.assertRaisesRegex(ValueError, 'fresh canonical absolute'):
                compat.build('dissolve', self.white, self.original, out)

    def test_manifest_cannot_write_into_source_or_output(self):
        for folder in (self.white, self.original, self.out):
            if not folder.exists():
                folder.mkdir()
            args = ['--kind', 'dissolve', '--white-template', str(self.white),
                    '--original-resource', str(self.original), '--out', str(self.out),
                    '--manifest-out', str(folder / 'manifest.json')]
            with self.subTest(folder=folder), self.assertRaisesRegex(ValueError, 'outside the original'):
                compat.main(args)
            self.assertFalse((folder / 'manifest.json').exists())

    def test_shipped_adapters_match_reviewed_fingerprints(self):
        folder = Path(compat.__file__).with_name('windows_transition_adapters')
        for kind, expected in compat.ADAPTER_HASHES.items():
            with self.subTest(kind=kind):
                self.assertEqual(hashlib.sha256((folder / (kind + '.lua')).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
