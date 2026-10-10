#!/usr/bin/env python3
"""COMMAND_INDEX 与官方能力清单的一致性断言。

回归目标（代码审查第 6 条待确认项）：`lyra_commands.install()` 装出的索引、清单文件
`engine/lyra_commands.json` 与 `engine/lyra_cli.py` 里的手写封装必须三方对齐——

- 清单里每条命令要么装成可调用函数，要么作为手写覆盖登记，不能静默丢失；
- 索引里每个名字都必须真能用清单签名调用，且参数白名单与清单逐条一致；
- 全局开关（``--help`` / ``--version`` / ``--jq``）不得进入任何命令的白名单。

这些断言只读已装好的结果，不执行任何真实官方命令。
"""
import ast
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import lyra_cli  # noqa: E402
import lyra_commands  # noqa: E402

MANIFEST = lyra_commands.load_manifest()
# 函数名 → 清单规格；install() 与测试都以它为唯一真源
SPEC_BY_NAME = {lyra_commands.function_name(spec["path"]): spec for spec in MANIFEST["commands"]}
# 官方全局开关：会改变命令行为（--help 会让命令挂住），必须从白名单剔除
GLOBAL_FLAGS = {"--help", "--version", "--jq"}


def handwritten_names():
    """``lyra_cli.py`` 里手写的顶层函数名（清单版不会覆盖它们）。"""
    tree = ast.parse((ROOT / "engine" / "lyra_cli.py").read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


class IndexConsistencyTests(unittest.TestCase):
    def test_global_flag_set_is_the_one_we_test(self):
        # 断言实现里的常量与本文档化的集合一致，避免它被悄悄扩大或缩小
        self.assertEqual(set(lyra_commands._GLOBAL_FLAGS), GLOBAL_FLAGS)

    def test_index_and_overrides_cover_every_manifest_command(self):
        covered = set(lyra_cli.COMMAND_INDEX) | set(lyra_cli.COMMAND_MANUAL_OVERRIDES)
        self.assertEqual(sorted(covered), sorted(SPEC_BY_NAME),
                         "清单命令必须全部落地：装成函数或登记为手写覆盖")
        self.assertEqual(MANIFEST["count"], len(MANIFEST["commands"]))
        self.assertEqual(len(SPEC_BY_NAME), len(MANIFEST["commands"]), "清单函数名重复")

    def test_counts_add_up(self):
        self.assertEqual(lyra_cli.COMMAND_COUNT, len(lyra_cli.COMMAND_INDEX))
        self.assertEqual(lyra_cli.COMMAND_COUNT,
                         len(MANIFEST["commands"]) - len(lyra_cli.COMMAND_MANUAL_OVERRIDES))

    def test_manual_overrides_are_handwritten_and_never_indexed(self):
        overrides = set(lyra_cli.COMMAND_MANUAL_OVERRIDES)
        handwritten = handwritten_names()
        self.assertTrue(overrides <= handwritten,
                        "被顶掉的必须是 lyra_cli 手写封装，而不是拼错的名字")
        self.assertEqual(overrides, set(SPEC_BY_NAME) & handwritten,
                         "清单里被手写顶掉的命令必须全部登记，不能静默跳过")
        self.assertEqual(overrides & set(lyra_cli.COMMAND_INDEX), set(),
                         "索引只登记真正安装的名字")
        for name in sorted(overrides):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(lyra_cli, name)))

    def test_index_entries_match_manifest_path(self):
        for name, path in lyra_cli.COMMAND_INDEX.items():
            with self.subTest(name=name):
                spec = SPEC_BY_NAME[name]
                self.assertEqual(spec["path"], path)
                function = getattr(lyra_cli, name)
                self.assertTrue(callable(function))
                self.assertEqual(function.command_path, path)

    def test_allowed_options_match_manifest_minus_global_flags(self):
        for name in lyra_cli.COMMAND_INDEX:
            spec = SPEC_BY_NAME[name]
            expected = [flag for flag in spec["options"] if flag not in GLOBAL_FLAGS]
            with self.subTest(name=name):
                function = getattr(lyra_cli, name)
                allowed = function.allowed_options
                self.assertEqual(allowed, expected)
                self.assertEqual(function.strict_options, spec.get("help_state", "ok") == "ok")
                self.assertEqual(set(allowed) & GLOBAL_FLAGS, set(),
                                 "全局开关不得进入命令白名单")

    def test_shipped_manifest_has_no_unparsed_commands(self):
        # 最终动态清单已稳定为全量 ok；超时透传语义由 test_lyra_commands 的合成用例覆盖。
        unparsed = {name for name, spec in SPEC_BY_NAME.items()
                    if spec.get("help_state") != "ok"}
        self.assertEqual(unparsed, set())
        for name in lyra_cli.COMMAND_INDEX:
            with self.subTest(name=name):
                self.assertTrue(getattr(lyra_cli, name).strict_options)

    def test_index_functions_accept_the_manifest_signature(self):
        for name in lyra_cli.COMMAND_INDEX:
            with self.subTest(name=name):
                parameters = set(inspect.signature(getattr(lyra_cli, name)).parameters)
                self.assertTrue({"cwd", "timeout", "ref", "options", "workspace"} <= parameters,
                                "索引里的函数必须支持清单版签名")


if __name__ == "__main__":
    unittest.main()
