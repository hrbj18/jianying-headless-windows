"""Reject permissive-parser traps before data reaches the native LUT loader."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_cube as cube


class CustomCube(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=('0.1 0.2 0.3\n'*cube.SAMPLES).encode('ascii')
        cls.valid=b'LUT_3D_SIZE 33\n'+cls.rows
    def test_optional_default_headers_removed_without_resampling_data(self):
        raw=b'# comment\nTITLE "Owned test"\nDOMAIN_MIN 0 0 0\nLUT_3D_SIZE 33\nDOMAIN_MAX 1 1 1\n'+self.rows
        result=cube.parse(raw)
        self.assertEqual(result.canonical,self.valid)
        self.assertEqual(result.title,'Owned test')
        self.assertNotEqual(result.source_sha256,result.sha256)
        self.assertEqual(cube.parse(result.canonical).canonical,result.canonical)
    def test_missing_and_extra_rows_are_rejected_even_if_ffmpeg_would_ignore_extra(self):
        for data in [self.valid+b'0 0 0\n',self.valid.rsplit(b'\n',2)[0]+b'\n']:
            with self.assertRaises(ValueError):cube.parse(data)
    def test_native_unverified_size_domain_and_shaper_are_rejected(self):
        for header in [b'LUT_3D_SIZE 17\n',b'DOMAIN_MIN .25 .25 .25\nLUT_3D_SIZE 33\n',
                       b'LUT_1D_SIZE 33\nLUT_3D_SIZE 33\n']:
            with self.assertRaises(ValueError):cube.parse(header+self.rows)
    def test_nonfinite_out_of_range_and_non_c_numeric_tokens_are_rejected(self):
        for row in [b'nan 0 0',b'inf 0 0',b'-0.1 0 0',b'1.1 0 0',b'0.0_5 0 0']:
            bad=b'LUT_3D_SIZE 33\n'+row+b'\n'+self.rows.split(b'\n',1)[1]
            with self.subTest(row=row),self.assertRaises(ValueError):cube.parse(bad)

if __name__=='__main__':unittest.main()
