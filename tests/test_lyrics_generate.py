import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lyrics_generate", ROOT / "engine/lyrics_generate.py")
lyrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lyrics)


class LyricsGenerateTests(unittest.TestCase):
    def test_source_time_maps_back_to_timeline_with_speed(self):
        mapping = [{"source_start": 10.0, "source_end": 14.0,
                    "target_start": 2.0, "target_end": 4.0, "speed": 2.0}]
        self.assertEqual(lyrics.map_time(12.0, mapping), 3.0)
        self.assertIsNone(lyrics.map_time(9.0, mapping))

    def test_writes_json_srt_and_plain_official_plan(self):
        result = {"schema": lyrics.SCHEMA, "cues": [{
            "id": "lyric_0001", "text": "自动歌词", "start_ms": 1200, "end_ms": 2500,
            "words": [{"text": "自动歌词", "start_ms": 1200, "end_ms": 2500,
                       "confidence": 0.9}],
        }]}
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            output = Path(parent) / "result"
            files = lyrics.write_outputs(output, result)
            plan = json.loads(Path(files["official_plan"]).read_text(encoding="utf-8"))
            srt = Path(files["srt"]).read_text(encoding="utf-8")
        self.assertEqual(plan["lyrics"][0]["text"], "自动歌词")
        self.assertNotIn("animation_ref", plan["lyrics"][0])
        self.assertIn("00:00:01,200 --> 00:00:02,500", srt)


if __name__ == "__main__":
    unittest.main()
