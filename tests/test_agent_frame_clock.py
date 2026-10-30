"""Replay the actual 29.166667s native writer mismatch, without rendering."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_export as native

class FrameClock(unittest.TestCase):
    def probe(self, frames):
        return {'format':{'duration':'29.2','tags':{'major_brand':'isom'}}, 'streams':[
            {'codec_type':'video','codec_name':'h264','width':1080,'height':1920,'r_frame_rate':'30/1','nb_frames':str(frames)},
            {'codec_type':'audio','codec_name':'aac'}]}
    def test_recorded_microsecond_rounding_accepts_actual_native_writer(self):
        result=native.validate_probe(self.probe(876),{'width':1080,'height':1920,'fps':30},29166667,True)
        self.assertEqual(result['accepted_frame_range'],[875,876])
    def test_missing_or_two_extra_frames_still_fail(self):
        for frames in (874,877):
            with self.assertRaisesRegex(ValueError,'frame count'):
                native.validate_probe(self.probe(frames),{'width':1080,'height':1920,'fps':30},29166667,True)
    def test_exact_frame_span_remains_strict(self):
        self.assertEqual(native.frame_count_bounds(33200000,30),(996,996,996,'exact-aligned'))
        self.assertEqual(native.frame_count_bounds(29200000,30),(876,876,876,'exact-aligned'))

if __name__=='__main__': unittest.main()
