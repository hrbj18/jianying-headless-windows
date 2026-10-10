#!/usr/bin/env python3
"""tools/functional_test.py 的纯函数测试（不启动真实官方 CLI）。

真实调用由 ``python tools/functional_test.py --layer execute`` 完成；这里只守护
参数规格解析、取值生成与失败归类这些"决定测试是否可信"的逻辑。
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import functional_test as ft  # noqa: E402

HELP = """Compress a video file.

USAGE:
  lyra-cli <domain> <[subdomain] ...> <action> [--flags] [--options]

OPTIONS:
  -h,     --help              Print this help message and exit
          --input TEXT REQUIRED
                              Input video file path.
          --path, --input-file TEXT
                              Alias row.
          --codec TEXT:{h264,hevc} [h264]
                              Output codec.
          --no-auto-orient    Disable rotation metadata normalization.
  -v,     --version           Show version information and exit.
"""


class FakeContext:
    """最小上下文替身：只提供取值需要的字段。"""

    def __init__(self):
        self.ref = "local://unit"
        self.seg_id = "SEG-1"
        self.out_dir = Path("C:/unit/out")
        self.workspace = Path("C:/unit/ws")
        self.media_files = {"video": Path("C:/unit/v.mp4"), "audio": Path("C:/unit/a.m4a"),
                            "image": Path("C:/unit/i.png")}

    def seg_id_for(self, path):
        return self.seg_id

    def fresh_workspace(self, clear=False):
        return self.workspace

    def pick_media(self, path, flag):
        hint = " ".join(path) + " " + flag
        if "image" in hint:
            return self.media_files["image"]
        if "audio" in hint:
            return self.media_files["audio"]
        return self.media_files["video"]

    def output_path(self, flag, path):
        return self.out_dir / ("-".join(path) + ".mp4")

    def generic_value(self, flag):
        return "func-test"

    def media_path(self, flag):
        return self.media_files["video"]


class OptionSpecTests(unittest.TestCase):
    def test_parses_required_alias_choices_and_switches(self):
        specs = {spec.flag: spec for spec in ft.parse_option_specs(HELP)}
        self.assertTrue(specs["--input"].required)
        self.assertEqual(specs["--input"].type_token, "TEXT")
        self.assertEqual(specs["--path"].aliases, ["--path", "--input-file"])
        self.assertEqual(specs["--codec"].choices, ["h264", "hevc"])
        self.assertFalse(specs["--no-auto-orient"].takes_value)
        # 别名行与首行是同一个参数，不会重复登记。
        self.assertEqual(list(specs), ["--help", "--input", "--path", "--codec",
                                       "--no-auto-orient", "--version"])

    def test_prose_starting_with_capital_is_not_a_type(self):
        text = ("OPTIONS:\n"
                "          --wait     Wait for the task to finish.\n")
        spec = ft.parse_option_specs(text)[0]
        self.assertEqual(spec.type_token, "")
        self.assertFalse(spec.takes_value)


class BuildInvocationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeContext()
        self.specs = ft.parse_option_specs(HELP)

    def test_required_value_uses_typed_default_and_skips_switches(self):
        args, used = ft.build_invocation(["media", "compress"], self.specs, self.ctx)
        self.assertEqual(args[:2], ["media", "compress"])
        self.assertIn("--input", args)
        self.assertIn(str(self.ctx.media_files["video"]), args)
        self.assertNotIn("--help", args)
        self.assertNotIn("--no-auto-orient", args)
        # 可选参数不主动传：避免 --codec 之类改变官方默认行为。
        self.assertNotIn("--codec", args)

    def test_format_follows_output_suffix_not_first_choice(self):
        # 官方会拒绝 --format 与 --output 后缀不一致，因此必须跟随后缀（png）而不是 choices[0]。
        text = ("OPTIONS:\n"
                "          --format TEXT:{jpg,png} REQUIRED\n"
                "          --output TEXT REQUIRED\n")
        args, _ = ft.build_invocation(["media", "transcode-image"],
                                      ft.parse_option_specs(text), self.ctx)
        self.assertEqual(args[args.index("--format") + 1], "png")

    def test_plain_choice_still_uses_first_candidate(self):
        text = "OPTIONS:\n          --codec TEXT:{h264,hevc} REQUIRED\n"
        args, _ = ft.build_invocation(["media", "compress"],
                                      ft.parse_option_specs(text), self.ctx)
        self.assertEqual(args[args.index("--codec") + 1], "h264")

    def test_seg_id_wins_over_mutually_exclusive_locators(self):
        text = ("OPTIONS:\n"
                "          --seg-id <SEG_ID[,SEG_ID...]>\n"
                "          --target-track <INDEX[,INDEX...]>\n"
                "          --seg-index <INDEX[,INDEX...]>\n")
        args, _ = ft.build_invocation(["draft", "video", "speed"],
                                      ft.parse_option_specs(text), self.ctx)
        self.assertIn("--seg-id", args)
        self.assertNotIn("--target-track", args)
        self.assertNotIn("--seg-index", args)

    def test_enable_disable_pair_becomes_enable_switch(self):
        text = ("OPTIONS:\n"
                "          --enable   Enable it.\n"
                "          --disable  Disable it.\n"
                "          --seg-id <SEG_ID>\n")
        args, _ = ft.build_invocation(["draft", "video", "mix-mode"],
                                      ft.parse_option_specs(text), self.ctx)
        self.assertIn("--enable", args)
        self.assertNotIn("--disable", args)

    def test_optional_segment_paths_do_not_get_seg_id(self):
        text = "OPTIONS:\n          --seg-id TEXT\n"
        args, _ = ft.build_invocation(["draft", "extract", "summary"],
                                      ft.parse_option_specs(text), self.ctx)
        self.assertNotIn("--seg-id", args)

    def test_resource_uses_local_uri_but_input_keeps_plain_path(self):
        text = ("OPTIONS:\n"
                "          --resource TEXT\n"
                "          --input TEXT\n")
        args, _ = ft.build_invocation(["draft", "video", "add"],
                                      ft.parse_option_specs(text), self.ctx)
        resource = args[args.index("--resource") + 1]
        self.assertTrue(resource.startswith("local:///"))
        self.assertFalse(args[args.index("--input") + 1].startswith("local:///"))


class OutcomeTests(unittest.TestCase):
    def outcome(self, exit_code, message="", err_code=None, category=""):
        return ft.Outcome("x", exit_code=exit_code, err_code=err_code,
                          err_category=category, message=message)

    def test_official_boundaries_are_named_not_blamed_on_the_wrapper(self):
        self.assertEqual(ft.classify(self.outcome(
            2, "command is not implemented yet (work in progress)")), "not_implemented")
        self.assertEqual(ft.classify(self.outcome(
            2, "only available when lyra-cli is embedded as a client library")),
            "requires_embedded_library")
        self.assertEqual(ft.classify(self.outcome(
            2, "VAD (AED) model not found")), "model_missing")

    def test_login_and_prerequisite_are_separated(self):
        self.assertEqual(ft.classify(self.outcome(
            1, "auth credential is missing: not logged in")), "needs_login")
        self.assertEqual(ft.classify(self.outcome(
            2, "draft algo command requires a segment target")), "needs_prerequisite")
        self.assertEqual(ft.classify(self.outcome(
            2, "cli parse error: RequiredError: --seg-id is required")), "usage")
        self.assertEqual(ft.classify(self.outcome(1, "draft not found: local://x")),
                         "business_error")


class ReportTests(unittest.TestCase):
    def test_markdown_lists_every_command_row(self):
        report = {"command_count": 1,
                  "execute": {"summary": {"ok": 1},
                              "rows": [{"path": ["draft", "project", "list"],
                                        "state": "ok", "exit_code": 0,
                                        "args": ["project", "list"], "message": "success"}]}}
        text = ft.render_markdown(report)
        self.assertIn("draft project list", text)
        self.assertIn("✅ 成功", text)


if __name__ == "__main__":
    unittest.main()
