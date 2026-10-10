import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jypack_inspect", ROOT / "engine/jypack_inspect.py")
jypack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jypack)


def package_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    payload = stream.getvalue()
    for source, target in ((b"PK\x03\x04", b"JY\x03\x04"),
                           (b"PK\x01\x02", b"JY\x01\x02"),
                           (b"PK\x05\x06", b"JY\x05\x06")):
        payload = payload.replace(source, target)
    return payload


class JyPackInspectTests(unittest.TestCase):
    def timeline(self):
        return {
            "duration": 2_000_000,
            "tracks": [{"type": "audio"}],
            "config": {"lyrics_taskinfo": [{
                "id": "job", "language": "zh-CN", "type": 115,
                "content": json.dumps({"utterances": [{"text": "歌词", "words": [{"text": "歌"}]}]}),
            }]},
            "materials": {
                "audios": [{
                    "id": "tts", "type": "text_to_audio", "name": "测试文本",
                    "tone_type": "测试音色", "tone_speaker": "speaker", "resource_id": "123",
                    "path": "##_draftpath_placeholder_A_##/textReading/a.wav",
                }],
                "texts": [{"id": "lyric", "type": "lyrics",
                            "content": json.dumps({"text": "歌词"}, ensure_ascii=False)}],
                "text_templates": [{"type": "text_template_lyrics", "resource_id": "456"}],
            },
        }

    def test_detects_tts_lyrics_and_intentionally_absent_template_package(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            source = Path(folder) / "sample.jypack"
            source.write_bytes(package_bytes({
                "draft_content.json": b"encrypted-placeholder",
                "textReading/a.wav": b"ID3\x04\x00\x00\x00\x00\x00\x00",
            }))
            report = jypack.inspect_jypack(source, decryptor=lambda _: (self.timeline(), True))
        self.assertTrue(report["container"]["crc_valid"])
        self.assertTrue(report["tts"]["all_audio_present"])
        self.assertEqual(report["tts"]["items"][0]["detected_format"], "mp3")
        self.assertEqual(report["lyrics"]["material_count"], 1)
        self.assertEqual(report["lyrics"]["recognition_tasks"][0]["word_count"], 1)
        self.assertFalse(report["official_template_package"]["detected"])
        self.assertFalse(report["render_readiness"]["jypack_is_draft_ref"])
        self.assertEqual(report["path_integrity"]["missing_reference_count"], 0)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            source = Path(folder) / "unsafe.jypack"
            source.write_bytes(package_bytes({"draft_content.json": b"x", "../escape": b"x"}))
            with self.assertRaisesRegex(ValueError, "不安全路径"):
                jypack.inspect_jypack(source, decryptor=lambda _: (self.timeline(), True))

    def test_decodes_jy_zip_signatures(self):
        payload = package_bytes({"draft_content.json": b"{}"})
        decoded, counts = jypack.decode_container(payload)
        self.assertTrue(decoded.startswith(b"PK\x03\x04"))
        self.assertEqual(counts["4A590304"], 1)


if __name__ == "__main__":
    unittest.main()
