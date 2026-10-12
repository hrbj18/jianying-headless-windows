#!/usr/bin/env python3
"""tools/mine_cli_strings.py 与 tools/jypack_report.py 的纯函数测试。

真实二进制与真实模板包不在仓库里，因此这里只守护解析/渲染逻辑本身。
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import jypack_report  # noqa: E402
import mine_cli_strings  # noqa: E402


class MineCliStringsTests(unittest.TestCase):
    def test_scan_counts_hits_and_keeps_context(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "fake-lyra-cli.exe"
            exe.write_bytes(
                b"... draft algo video-tracking --tracker-type 2 --left-up-x ...\x00"
                b"... expects template:// or local:/// resource ...\x00"
                b"... template:// again ...")
            report = mine_cli_strings.scan(exe, ["tracker-type", "template://", "absent"])
        self.assertEqual(report["tracker-type"]["count"], 1)
        self.assertIn("tracker-type", report["tracker-type"]["samples"][0])
        self.assertEqual(report["template://"]["count"], 2)
        self.assertEqual(report["absent"], {"count": 0, "samples": []})

    def test_samples_are_ascii_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "fake.exe"
            exe.write_bytes("中文 --wait false 结尾".encode("utf-8"))
            report = mine_cli_strings.scan(exe, ["--wait false"])
        sample = report["--wait false"]["samples"][0]
        self.assertIn("--wait false", sample)
        sample.encode("ascii")  # 必须能安全打印到任意控制台

    def test_default_groups_cover_known_constraints(self):
        flat = {pattern for patterns in mine_cli_strings.DEFAULT_GROUPS.values()
                for pattern in patterns}
        for pattern in ("task_id", "segment_filter", "template://", "vimo://",
                        "not implemented yet", "tracker-type"):
            self.assertIn(pattern, flat)


class JypackReportTests(unittest.TestCase):
    def inspect_payload(self):
        return {
            "source": {"path": "C:/x/测试.jypack", "size": 71751134, "sha256": "abc"},
            "container": {"entry_count": 88, "unpacked_size": 91009468,
                          "crc_valid": True, "timeline_encrypted": True},
            "timeline": {"duration_seconds": 31.567, "track_count": 6,
                         "material_counts": {"texts": 43, "stickers": 5}},
            "tts": {"detected": True, "count": 5, "all_audio_present": True,
                    "speakers": ["ICL_zh_female_xinmanbo"],
                    "items": [{"text": "家人们别划走", "detected_format": "mp3",
                               "sample_rate": 24000, "channels": 1}]},
            "lyrics": {"detected": True, "material_count": 32, "template_count": 6,
                       "template_resource_ids": ["7591420714515844395"],
                       "recognition_tasks": [{"id": "t1"}]},
            "path_integrity": {"placeholder_reference_count": 10,
                               "missing_reference_count": 0},
        }

    def render_payload(self):
        return {"status": "rendered", "renderer": "Jianying native ExportService",
                "timeline_id": "E1C00739", "width": 2276, "height": 1280,
                "video_codec": "h264", "audio_codec": "aac", "video_duration": 31.6,
                "audio_duration": 31.601995, "output_size": 5205673,
                "output_sha256": "def", "runtime_token_used": False,
                "imported_draft": "C:/drafts/headless-verify-1",
                "imported_draft_written": False}

    def test_report_covers_all_sections(self):
        text = jypack_report.build_report(self.inspect_payload(), self.render_payload(),
                                          Path("."), {})
        for heading in ("容器与完整性", "模板要素", "包内配音", "歌词", "成片渲染", "结论"):
            self.assertIn(heading, text)
        self.assertIn("31.567", text)
        self.assertIn("2276×1280", text)
        self.assertIn("家人们别划走", text)
        self.assertIn("headless-verify-1", text)

    def test_report_without_render_still_renders(self):
        text = jypack_report.build_report(self.inspect_payload(), None, Path("."), {})
        self.assertIn("容器与完整性", text)
        self.assertNotIn("成片渲染", text)

    def test_audio_stats_section(self):
        audio = {"peak": 30979, "rms": 6413, "seconds": 31.6,
                 "segments": [(0, 3476), (5, 4820)]}
        text = jypack_report.build_report(self.inspect_payload(), self.render_payload(),
                                          Path("."), audio)
        self.assertIn("声轨实测", text)
        self.assertIn("30979", text)

    def test_shot_list_is_registered(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "check-8s.png").write_bytes(b"png")
            text = jypack_report.build_report(self.inspect_payload(), None,
                                              Path(folder), {})
        self.assertIn("画面抽帧", text)
        self.assertIn("check-8s.png", text)


if __name__ == "__main__":
    unittest.main()
