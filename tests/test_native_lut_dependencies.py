"""LUT resource snapshots retain bytes, including long shader paths."""
from pathlib import Path
import hashlib,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_lut_dependencies as lut


class LutDependencies(unittest.TestCase):
    def test_bounded_snapshot_copies_verified_bytes_without_overwriting_or_modifying_source(self):
        with tempfile.TemporaryDirectory(prefix='jy-lut-copy-') as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            data=b'original shader bytes';(source/'shader.txt').write_bytes(data)
            files={'shader.txt':dict(size=len(data),sha256=hashlib.sha256(data).hexdigest())}
            target=lut.destination(root/('a'*64),'feature')/('b'*45)/('c'*45)
            self.assertLessEqual(len(target.parents[1].name),32)
            lut.copy_dependency(source,target,files)
            self.assertEqual((target/'shader.txt').read_bytes(),data)
            self.assertEqual((source/'shader.txt').read_bytes(),data)
            (target/'shader.txt').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'snapshot bytes differ'):
                lut.copy_dependency(source,target,files)
            self.assertEqual((target/'shader.txt').read_bytes(),b'tampered')

if __name__=='__main__':unittest.main()
