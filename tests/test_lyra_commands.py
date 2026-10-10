#!/usr/bin/env python3
"""lyra_commands（清单驱动封装）的单元测试。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import lyra_commands  # noqa: E402

SAMPLE = {
    "generated_from": "test",
    "count": 3,
    "commands": [
        {"path": ["draft", "video", "speed"], "summary": "变速",
         "options": ["--ref", "--seg-id", "--speed", "--wait"], "help_state": "ok"},
        {"path": ["draft", "text", "add"], "summary": "加文本",
         "options": ["--ref", "--content"], "help_state": "ok"},
        {"path": ["media", "probe"], "summary": "探测", "options": [], "help_state": "timeout"},
    ],
}


class NamingTests(unittest.TestCase):
    def test_draft_prefix_stripped(self):
        self.assertEqual(lyra_commands.function_name(["draft", "video", "speed"]), "video_speed")

    def test_non_draft_keeps_first_part(self):
        self.assertEqual(lyra_commands.function_name(["media", "probe"]), "media_probe")
        self.assertEqual(lyra_commands.function_name(["material", "search"]), "material_search")

    def test_dashes_become_underscores(self):
        self.assertEqual(lyra_commands.function_name(["draft", "algo", "sound-separation"]),
                         "algo_sound_separation")

    def test_missing_manifest_is_empty(self):
        data = lyra_commands.load_manifest(Path("/nonexistent/manifest.json"))
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["commands"], [])


class CallerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def runner(path, cwd, timeout=600, ref=None, options=None, workspace=None):
            self.calls.append({"path": path, "ref": ref, "options": dict(options or {})})
            return {"ok": True}

        self.runner = runner

    def caller(self, spec):
        return lyra_commands.build_caller(spec, self.runner)

    def test_builds_flags_from_kwargs(self):
        call = self.caller(SAMPLE["commands"][0])
        call("/draft-root", ref="local://demo", seg_id="v1", speed=2.0, wait=True)
        # build_caller 保留原值，字符串化发生在 lyra_cli._options（真正拼命令行时）
        self.assertEqual(self.calls[-1]["options"],
                         {"--seg-id": "v1", "--speed": 2.0, "--wait": True})

    def test_rejects_unknown_flag(self):
        call = self.caller(SAMPLE["commands"][0])
        with self.assertRaises(ValueError) as caught:
            call("/draft-root", rotation=90)
        self.assertIn("--rotation", str(caught.exception))

    def test_none_and_false_are_skipped(self):
        call = self.caller(SAMPLE["commands"][0])
        call("/draft-root", seg_id="v1", speed=None, wait=False)
        self.assertEqual(self.calls[-1]["options"], {"--seg-id": "v1"})

    def test_timeout_command_passes_unknown_business_flags_through(self):
        # 参数表未取到的命令（help 超时）不校验未知业务参数，按官方原样透传
        call = self.caller(SAMPLE["commands"][2])
        call("/tmp", anything="x")
        self.assertEqual(self.calls[-1]["options"], {"--anything": "x"})
        self.assertFalse(call.strict_options)

    def test_global_flags_are_always_rejected_even_when_help_timed_out(self):
        call = self.caller(SAMPLE["commands"][2])
        attempts = [
            lambda: call("/tmp", help=True),
            lambda: call("/tmp", options={"--version": True}),
            lambda: call("/tmp", options={"jq": ".result"}),
        ]
        for attempt in attempts:
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                attempt()

    def test_parsed_command_with_no_business_options_rejects_every_flag(self):
        spec = {"path": ["draft", "project", "list"], "summary": "列出工程",
                "options": ["--help", "--version", "--jq"], "help_state": "ok"}
        call = self.caller(spec)
        self.assertEqual(call.allowed_options, [])
        self.assertTrue(call.strict_options)
        self.assertIn("无业务参数", call.__doc__)
        self.assertNotIn("原样透传", call.__doc__)
        attempts = [
            lambda: call("/tmp", rotaton=90),
            lambda: call("/tmp", ref="local://unexpected"),
            lambda: call("/tmp", help=True),
            lambda: call("/tmp", options={"--help": True}),
        ]
        for attempt in attempts:
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                attempt()
        self.assertEqual(self.calls, [], "校验失败时不得进入 runner")

    def test_options_dictionary_uses_the_same_whitelist(self):
        call = self.caller(SAMPLE["commands"][0])
        call("/tmp", options={"seg_id": "v1", "--speed": 2})
        self.assertEqual(self.calls[-1]["options"], {"--seg-id": "v1", "--speed": 2})
        with self.assertRaises(ValueError):
            call("/tmp", options={"--rotation": 90})

    def test_metadata_and_docstring(self):
        call = self.caller(SAMPLE["commands"][0])
        self.assertEqual(call.__name__, "video_speed")
        self.assertEqual(call.command_path, ["draft", "video", "speed"])
        self.assertIn("draft video speed", call.__doc__)


class InstallTests(unittest.TestCase):
    class Namespace:
        def __init__(self):
            self.existing_marker = True

        def text_add(self):
            """手写版本，应被保留。"""

    def test_install_creates_functions(self):
        namespace = self.Namespace()
        runner = lambda *a, **k: {}
        count, index = lyra_commands.install(namespace, runner, manifest=SAMPLE)
        self.assertEqual(count, 2)  # text_add 已存在 → 跳过
        self.assertEqual(index["video_speed"], ["draft", "video", "speed"])
        self.assertTrue(callable(namespace.video_speed))
        self.assertTrue(callable(namespace.media_probe))
        self.assertEqual(namespace.COMMAND_SKIPPED, ["text_add"])

    def test_shipped_manifest_covers_all_commands(self):
        data = lyra_commands.load_manifest()
        self.assertGreater(data["count"], 100, "清单应覆盖 100+ 条官方命令")
        names = [lyra_commands.function_name(spec["path"]) for spec in data["commands"]]
        self.assertEqual(len(names), len(set(names)), "函数名不应重复")
        top_domains = {spec["path"][0] for spec in data["commands"]}
        self.assertTrue({"auth", "draft", "material", "media", "lint"} <= top_domains)
        specs = {tuple(spec["path"]): spec for spec in data["commands"]}
        discovery = data.get("discovery") or {}
        for failure in discovery.get("failures", []):
            with self.subTest(path=failure.get("path")):
                path = tuple(failure.get("path") or ())
                self.assertIn(path, specs, "暂态失败路径必须保留并明确标记非 ok")
                self.assertNotEqual(specs[path].get("help_state"), "ok")
        for item in discovery.get("unsupported", []):
            with self.subTest(unsupported=item.get("path")):
                self.assertNotIn(tuple(item.get("path") or ()), specs,
                                 "官方明确不支持的路径不得暴露 wrapper")
        self.assertIn(("draft", "algo", "object-matting-track"), specs)
        unsupported_paths = {tuple(item.get("path") or ())
                             for item in discovery.get("unsupported", [])}
        self.assertIn(("draft", "algo", "mask-tracking-mattingTrack"),
                      unsupported_paths)


if __name__ == "__main__":
    unittest.main()
