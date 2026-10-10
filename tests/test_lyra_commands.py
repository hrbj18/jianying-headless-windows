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

    def test_timeout_command_passes_anything_through(self):
        # 参数表未取到的命令（help 超时）不做白名单校验，按官方原样透传
        call = self.caller(SAMPLE["commands"][2])
        call("/tmp", anything="x")
        self.assertEqual(self.calls[-1]["options"], {"--anything": "x"})

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


if __name__ == "__main__":
    unittest.main()
