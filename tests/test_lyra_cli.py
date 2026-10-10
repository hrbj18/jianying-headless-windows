#!/usr/bin/env python3
"""lyra_cli 的单元测试。

只覆盖纯函数与命令参数构造，不调用真实 lyra-cli（真实调用需要剪映宿主、登录态与网络，
放在 tests/test_draftediting_runtime.py 的集成范围之外单独验证）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import lyra_cli  # noqa: E402

XML = """<draft>
  <text id="t12">
    <time start="0" duration="2860"></time>
    <content><sub text="九月不必再逢" color="#FFFFFF" size="5" /></content>
  </text>
  <text id="t13">
    <time start="6440" duration="1520"></time>
    <template ref="text_template_lyrics1" />
    <content><sub text="于是不觉可闻" color="#FFFFFF" size="5" /></content>
  </text>
  <text id="t14">
    <time start="7960" duration="2160"></time>
    <content><sub text="春风" color="#FFFFFF" size="5" /></content>
  </text>
  <subtitle id="t1">
    <time start="0" duration="866"></time>
    <content><sub text="家人们别划走" color="#FFFFFF" size="5" /></content>
  </subtitle>
</draft>
"""

RECOGNIZED = {"affected_segments": [
    {"asr": {"sentences": [
        {"text": "九月不必再逢", "start_us": 80000, "duration_us": 2860000},
        {"text": "于是不觉可闻", "start_us": 6440000, "duration_us": 1520000},
    ]}},
    {"asr": {"sentences": [
        {"text": "九月不必再逢", "start_us": 80000, "duration_us": 2860000},
        {"text": "春风它掠过我空袖口", "start_us": 7960000, "duration_us": 2160000},
    ]}},
]}


class SegmentParseTests(unittest.TestCase):
    def test_parses_id_text_and_template_flag(self):
        rows = lyra_cli.parse_segment_rows(XML)
        self.assertEqual(rows, [("t12", "九月不必再逢", False),
                                ("t13", "于是不觉可闻", True),
                                ("t14", "春风", False),
                                ("t1", "家人们别划走", False)])

    def test_pending_keeps_only_full_lyric_sentences(self):
        mapping = {"t12": "uuid-12", "t13": "uuid-13", "t14": "uuid-14", "t1": "uuid-1"}
        pending = lyra_cli.pending_lyric_segments(
            XML, mapping, ["九月不必再逢", "于是不觉可闻"])
        # t13 已带动效模板、t14 文本只是展开后的词、t1 不是歌词，均应排除
        self.assertEqual(pending, [("t12", "uuid-12", "九月不必再逢")])

    def test_pending_requires_id_mapping(self):
        pending = lyra_cli.pending_lyric_segments(XML, {}, ["九月不必再逢"])
        self.assertEqual(pending, [])


class OfficialCueTests(unittest.TestCase):
    def test_dedupes_and_sorts(self):
        cues = lyra_cli.recognized_cues(RECOGNIZED)
        self.assertEqual([cue["text"] for cue in cues],
                         ["九月不必再逢", "于是不觉可闻", "春风它掠过我空袖口"])
        self.assertEqual(cues[0], {"id": "lyric_01", "text": "九月不必再逢",
                                   "start_ms": 80, "end_ms": 2940})
        self.assertEqual([cue["start_ms"] for cue in cues], sorted(c["start_ms"] for c in cues))

    def test_sentences_helper(self):
        self.assertEqual(lyra_cli.lyrics_recognized_sentences(RECOGNIZED),
                         ["九月不必再逢", "于是不觉可闻", "春风它掠过我空袖口"])

    def test_empty_input(self):
        self.assertEqual(lyra_cli.recognized_cues({}), [])
        self.assertEqual(lyra_cli.lyrics_recognized_sentences(None), [])


class CommandShapeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        original = lyra_cli.run

        def fake_run(args, cwd, timeout=600, read_write=(), read_only=(), allow_dev_app=True):
            self.calls.append({"args": list(args), "cwd": str(cwd)})
            return {"ok": True}

        lyra_cli.run = fake_run
        self.addCleanup(lambda: setattr(lyra_cli, "run", original))

    def args(self):
        return self.calls[-1]["args"]

    def test_recognize_segment_mode(self):
        lyra_cli.lyrics_recognize("/draft-root", "local://demo", language="zh",
                                  mode="segment", seg_id="UUID-1")
        self.assertEqual(self.args(), ["draft", "lyrics", "recognize", "--ref", "local://demo",
                                       "--language", "zh", "--mode", "segment",
                                       "--seg-id", "UUID-1", "--clear-previous", "true"])

    def test_recognize_clear_previous_false(self):
        lyra_cli.lyrics_recognize("/draft-root", "local://demo", clear_previous=False)
        self.assertIn("false", self.args())

    def test_animation_update(self):
        lyra_cli.lyrics_animation_update("/draft-root", "local://demo", "UUID-1",
                                         "vimo://7591420714515844395")
        self.assertEqual(self.args(), ["draft", "lyrics", "animation", "update",
                                       "--ref", "local://demo", "--seg-id", "UUID-1",
                                       "--resource", "vimo://7591420714515844395",
                                       "--language", "zh-CN"])

    def test_animation_add_has_no_seg_id(self):
        lyra_cli.lyrics_animation_add("/draft-root", "local://demo",
                                      "vimo://7591420714515844395", cover_old=True)
        args = self.args()
        self.assertEqual(args[:5], ["draft", "lyrics", "animation", "add", "--ref"])
        self.assertNotIn("--seg-id", args)
        self.assertIn("--cover-old", args)

    def test_login_link_and_complete(self):
        calls = self.calls

        def link_run(args, cwd, *rest, **kwargs):
            calls.append({"args": list(args), "cwd": str(cwd)})
            return {"login_url": "https://example.invalid/auth"}

        lyra_cli.run = link_run
        self.assertEqual(lyra_cli.auth_login_link("/tmp")["login_url"],
                         "https://example.invalid/auth")
        self.assertEqual(self.args(), ["auth", "login", "--link-url", "--no-wait"])
        lyra_cli.auth_login_complete("/tmp", device_code="D", user_code="U",
                                     session_handoff="H")
        args = self.args()
        self.assertEqual(args[:2], ["auth", "login"])
        for flag, value in (("--device-code", "D"), ("--user-code", "U"),
                            ("--session-handoff", "H")):
            self.assertIn(flag, args)
            self.assertEqual(args[args.index(flag) + 1], value)


    def test_subtitle_add_and_audio_add(self):
        lyra_cli.subtitle_add("/draft-root", "local://demo", "字幕内容", track="subtitle",
                              start="1.5s", duration="2s")
        self.assertEqual(self.args(), ["draft", "subtitle", "add", "--ref", "local://demo",
                                       "--content", "字幕内容", "--track", "subtitle",
                                       "--start", "1.5s", "--duration", "2s"])
        lyra_cli.audio_add("/draft-root", "local://demo", "local:///x/a.mp3", start="0s")
        self.assertEqual(self.args()[:5], ["draft", "audio", "add", "--ref", "local://demo"])
        self.assertIn("--resource", self.args())

    def test_algo_tts_flags(self):
        lyra_cli.algo_tts("/draft-root", "local://demo", "你好", speaker="BV700_streaming",
                          write_to_draft=True)
        args = self.args()
        self.assertEqual(args[:4], ["draft", "algo", "tts", "--ref"])
        self.assertIn("--text", args)
        self.assertIn("--write-to-draft", args)
        # 未开启的开关不应出现
        self.assertNotIn("--copy-to-draft", args)
        self.assertNotIn("--replace", args)

    def test_generic_draft_passthrough(self):
        lyra_cli.draft(["video", "speed"], "/draft-root", "local://demo",
                       {"--seg-id": "v1", "--speed": "2.0", "--wait": True, "--x": None})
        self.assertEqual(self.args(), ["draft", "video", "speed", "--ref", "local://demo",
                                       "--seg-id", "v1", "--speed", "2.0", "--wait"])

    def test_lint_and_material_and_media(self):
        lyra_cli.lint_draft("/draft-root", "local://demo", suite="basic")
        self.assertEqual(self.args()[:4], ["lint", "draft", "--ref", "local://demo"])
        self.assertIn("--suite", self.args())
        lyra_cli.material_search("/tmp", "sticker", prompt="flower", limit=5)
        self.assertEqual(self.args()[:4], ["material", "search", "--type", "sticker"])
        self.assertIn("--prompt", self.args())
        lyra_cli.media_asr("/tmp", "/tmp/a.m4a", language="zh")
        self.assertEqual(self.args()[:4], ["media", "asr", "--input", "/tmp/a.m4a"])

    def test_template_render_is_official_render_command(self):
        lyra_cli.template_render("/tmp", "./cfg.json", "local://preview", "./out.mp4")
        self.assertEqual(self.args(), ["draft", "template", "render", "--config", "./cfg.json",
                                       "--ref", "local://preview", "--output", "./out.mp4"])


class ResultEnvelopeTests(unittest.TestCase):
    def test_success_returns_result(self):
        self.assertEqual(lyra_cli._result({"result": {"err_code": 0, "result": {"a": 1}}}),
                         {"a": 1})

    def test_failure_raises_with_message(self):
        with self.assertRaises(Exception) as caught:
            lyra_cli._result({"result": {"err_code": -100304,
                                         "err_msg": "auth credential is missing"}})
        self.assertIn("auth credential is missing", str(caught.exception))

    def test_missing_body_raises(self):
        with self.assertRaises(Exception):
            lyra_cli._result({})


if __name__ == "__main__":
    unittest.main()
