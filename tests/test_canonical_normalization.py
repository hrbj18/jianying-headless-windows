"""canonical XML 规范化工具的单元测试（离线，不调用剪映）。"""
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("normalize_canonical_xml",
                                              ROOT / "tools/normalize_canonical_xml.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SAMPLE = """<draft width="2276" height="1280">
  <main>
    <video id="v2" ref="video1" volume="0">
      <time material_start="0" duration="25133" speed="1" />
    </video>
  </main>
  <multi>
    <subtitle id="t1" font_ref="C:/fonts/a.ttf" text_shadow="0">
      <content><sub text="你好" size="5" /></content>
    </subtitle>
  </multi>
</draft>
"""


class FontRefTests(unittest.TestCase):
    def test_drop_removes_font_ref_everywhere(self):
        updated, handled = MODULE.normalize_font_ref(SAMPLE, "drop")
        self.assertNotIn("font_ref", updated)
        self.assertEqual(len(handled), 1)
        self.assertIn('text_shadow="0"', updated)

    def test_move_keeps_path_on_sub(self):
        updated, handled = MODULE.normalize_font_ref(SAMPLE, "move")
        self.assertEqual(len(handled), 1)
        self.assertNotIn('<subtitle id="t1" font_ref', updated)
        self.assertIn('<sub font_ref="C:/fonts/a.ttf" text="你好"', updated)

    def test_text_and_time_untouched(self):
        updated, _ = MODULE.normalize_font_ref(SAMPLE, "drop")
        self.assertIn('duration="25133"', updated)
        self.assertIn('text="你好"', updated)


class MainRangeTests(unittest.TestCase):
    def test_splits_overflow_and_keeps_total_duration(self):
        report = []
        updated = MODULE.fix_main_range(SAMPLE, {"video1": 17600}, report)
        self.assertIn('id="v2_b2"', updated)
        self.assertIn('duration="17600"', updated)
        self.assertIn('duration="7533"', updated)
        total = sum(piece["duration_ms"] for piece in report[0]["pieces"])
        self.assertEqual(total, 25133)
        for piece in report[0]["pieces"]:
            self.assertLessEqual(piece["material_start_ms"] + piece["duration_ms"], 17600)

    def test_within_range_is_untouched(self):
        report = []
        updated = MODULE.fix_main_range(SAMPLE, {"video1": 30000}, report)
        self.assertEqual(updated, SAMPLE)
        self.assertEqual(report, [])

    def test_unknown_ref_is_untouched(self):
        report = []
        updated = MODULE.fix_main_range(SAMPLE, {}, report)
        self.assertEqual(updated, SAMPLE)


class ResourceDurationTests(unittest.TestCase):
    def test_reads_metadata_duration(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "resource_map.json"
            path.write_text(json.dumps([
                {"asset_id": "video1", "metadata": {"duration_us": 17600000}},
                {"asset_id": "image1", "metadata": {"duration_us": 10800000000}},
                {"asset_id": "audio1"},
            ]), encoding="utf-8")
            durations = MODULE.resource_durations(folder)
        self.assertEqual(durations, {"video1": 17600, "image1": 10800000})


if __name__ == "__main__":
    unittest.main()
