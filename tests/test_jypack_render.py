import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jypack_render", ROOT / "engine/jypack_render.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class JyPackRenderTests(unittest.TestCase):
    def test_resolves_placeholder_inside_nested_text_json(self):
        value = {
            "path": "##_draftpath_placeholder_A_##/ImportedMaterials/Used/a.mp4",
            "content": '{"font":{"path":"##_draftpath_placeholder_A_##/font/a.ttf"}}',
        }
        result = renderer.resolve_paths(value, Path("C:/draft"))
        self.assertEqual(result["path"], "C:/draft/ImportedMaterials/Used/a.mp4")
        self.assertIn("C:/draft/font/a.ttf", result["content"])

    def test_remote_urls_are_not_mistaken_for_local_paths(self):
        value = {"preview": "https://example.com/a.png", "path": "C:/draft/a.mp4"}
        self.assertEqual(renderer.referenced_local_paths(value), {"C:/draft/a.mp4"})

    def test_media_validation_requires_complete_video_duration(self):
        valid = {
            "streams": [
                {"codec_type": "video", "duration": "2.000", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "duration": "2.010"},
            ],
            "format": {"duration": "2.010"},
        }
        video, audio = renderer.validate_media(valid, 2_000_000, True)
        self.assertIsNotNone(video)
        self.assertIsNotNone(audio)
        invalid = {"streams": [{"codec_type": "video", "duration": "1.000",
                                  "avg_frame_rate": "30/1"}], "format": {"duration": "2.000"}}
        with self.assertRaisesRegex(ValueError, "视频时长"):
            renderer.validate_media(invalid, 2_000_000, False)


if __name__ == "__main__":
    unittest.main()
