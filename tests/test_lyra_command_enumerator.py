#!/usr/bin/env python3
"""动态 lyra-cli help 枚举器的纯函数与发布门禁测试。"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import enumerate_all_commands as enumerator  # noqa: E402

ROOT_HELP = """Official lyra-cli

USAGE:
  lyra-cli <domain> <action>

OPTIONS:
  -h, --help  Print help
  -v, --version  Version
      --jq TEXT  Select JSON

CLI management:
  auth        Account operations.
  upgrade     Upgrade the CLI.

LYRA DOMAINS:
  draft       Draft operations.

EXAMPLES
  lyra-cli draft --help
"""

DRAFT_HELP = """Draft operations.

USAGE:
  lyra-cli draft <subcommand>

OPTIONS:
  -h, --help  Print help

SUBCOMMANDS:
  history        Undo and redo.
  deform         Deform shortcuts.
  edit           Legacy raw edit.
  text-template  Text template shortcuts.
"""

VIDEO_HELP = """Video shortcuts.

USAGE:
  lyra-cli draft video <subcommand>

OPTIONS:
  -h, --help  Print help

SUBCOMMANDS:
  filter  Filter shortcuts.
"""

FILTER_HELP = """Filter shortcuts.

USAGE:
  lyra-cli draft video filter <subcommand>

OPTIONS:
  -h, --help  Print help

SUBCOMMANDS:
  add     Add a filter.
  remove  Remove a filter.
"""

LEAF_HELP = """Perform one official operation.

USAGE:
  lyra-cli command [options]

OPTIONS:
  -h, --help       Print help
      --ref TEXT   Draft reference
                   Mentioning --not-a-real-option here must not whitelist it.
      --seg-id ID  Segment ID
  -v, --version    Version
      --jq TEXT    Select JSON

EXAMPLES
  lyra-cli command --ref local://demo
"""

NO_BUSINESS_OPTIONS_HELP = """List projects.

USAGE:
  lyra-cli draft project list

OPTIONS:
  -h, --help     Print help
  -v, --version  Version
      --jq TEXT  Select JSON
"""


class ParserTests(unittest.TestCase):
    def test_parses_domains_options_and_summary(self):
        parsed = enumerator.parse_help(ROOT_HELP)
        self.assertEqual(parsed["summary"], "Official lyra-cli")
        self.assertEqual(parsed["options"], ["--help", "--version", "--jq"])
        self.assertEqual(parsed["subcommands"], ["auth", "upgrade", "draft"])

    def test_parses_leaf_business_options_without_help_examples(self):
        parsed = enumerator.parse_help(LEAF_HELP)
        self.assertEqual(parsed["subcommands"], [])
        self.assertEqual(parsed["options"],
                         ["--help", "--ref", "--seg-id", "--version", "--jq"])

    def test_successful_leaf_may_have_no_business_options(self):
        parsed = enumerator.parse_help(NO_BUSINESS_OPTIONS_HELP)
        self.assertEqual(parsed["options"], ["--help", "--version", "--jq"])
        self.assertEqual(parsed["subcommands"], [])

    def test_parses_all_aliases_on_definition_row_only(self):
        help_text = """Aliases.\n\nUSAGE:\n  lyra-cli command\n\nOPTIONS:\n          --path, --input TEXT\n          --curve, --easing, --ease TEXT\n                              Mention --not-an-option only in prose.\n"""
        parsed = enumerator.parse_help(help_text)
        self.assertEqual(parsed["options"],
                         ["--path", "--input", "--curve", "--easing", "--ease"])


class ProbePayloadTests(unittest.TestCase):
    def payload(self, stdout=LEAF_HELP, response_ok=True, result_ok=True, exit_code=0,
                timed_out=False, stderr="", command="C:/Jianying/lyra-cli.exe",
                args=None):
        return {"responseMessage": {"ok": response_ok, "result": {
            "ok": result_ok, "exitCode": exit_code, "timedOut": timed_out,
            "stdout": stdout, "stderr": stderr, "command": command,
            "args": ["draft", "--help"] if args is None else args,
        }}}

    def test_accepts_only_successful_structured_help(self):
        result = enumerator.interpret_probe_payload(self.payload())
        self.assertEqual(result.state, "ok")
        self.assertIn("USAGE:", result.text)

    def test_nonzero_exit_with_stdout_is_not_misclassified_as_help(self):
        result = enumerator.interpret_probe_payload(self.payload(
            stdout="Unknown command draft bogus", result_ok=False, exit_code=2,
            stderr="bad command"))
        self.assertEqual(result.state, "unsupported")
        self.assertIn("exit_code", result.error)

    def test_other_nonzero_exit_remains_a_retryable_error(self):
        result = enumerator.interpret_probe_payload(self.payload(
            stdout="internal failure", result_ok=False, exit_code=1))
        self.assertEqual(result.state, "error")

    def test_zero_exit_without_usage_is_not_help(self):
        result = enumerator.interpret_probe_payload(
            self.payload(stdout="ordinary diagnostic output"))
        self.assertEqual(result.state, "invalid_help")

    def test_timeout_wins_over_partial_stdout(self):
        result = enumerator.interpret_probe_payload(
            self.payload(stdout=LEAF_HELP, timed_out=True))
        self.assertEqual(result.state, "timeout")

    def test_cached_help_must_match_install_and_exact_arguments(self):
        payload = self.payload()
        self.assertTrue(enumerator.probe_payload_matches_invocation(
            payload, Path("C:/Jianying"), ["draft"]))
        self.assertFalse(enumerator.probe_payload_matches_invocation(
            payload, Path("C:/OtherVersion"), ["draft"]))
        self.assertFalse(enumerator.probe_payload_matches_invocation(
            payload, Path("C:/Jianying"), ["media"]))


class DiscoveryTests(unittest.TestCase):
    def test_definitively_unsupported_old_path_is_not_preserved(self):
        previous = {"commands": [{"path": ["draft", "project", "info"],
                                   "options": [], "help_state": "empty"}]}

        def probe(path):
            if tuple(path) == ("draft", "project", "info"):
                return enumerator.ProbeResult("unsupported", error="ExtrasError")
            return enumerator.ProbeResult("ok", NO_BUSINESS_OPTIONS_HELP)

        payload = enumerator.discover_commands(probe, previous=previous, seeds=())
        paths = {tuple(spec["path"]) for spec in payload["commands"]}
        self.assertNotIn(("draft", "project", "info"), paths)
        self.assertTrue(any(failure["state"] == "unsupported"
                            for failure in payload["discovery"]["failures"]))

    def test_recurses_through_every_help_level_instead_of_using_a_tree(self):
        mapping = {
            (): ROOT_HELP,
            ("auth",): "Account operations.\n\nSUBCOMMANDS:\n  status  Show status.\n",
            ("auth", "status"): LEAF_HELP,
            ("upgrade",): LEAF_HELP,
            ("draft",): DRAFT_HELP,
            ("draft", "video"): VIDEO_HELP,
            ("draft", "video", "filter"): FILTER_HELP,
            ("draft", "video", "filter", "add"): LEAF_HELP,
            ("draft", "video", "filter", "remove"): LEAF_HELP,
            ("draft", "history"): LEAF_HELP,
            ("draft", "deform"): LEAF_HELP,
            ("draft", "edit"): LEAF_HELP,
            ("draft", "text-template"): LEAF_HELP,
        }

        def probe(path):
            return enumerator.ProbeResult("ok", mapping[tuple(path)])

        payload = enumerator.discover_commands(
            probe, seeds=(("draft", "video"),), workers=3)
        paths = [tuple(spec["path"]) for spec in payload["commands"]]
        self.assertIn(("auth", "status"), paths)
        self.assertIn(("draft", "video", "filter", "add"), paths)
        self.assertIn(("draft", "video", "filter", "remove"), paths)
        self.assertNotIn(("draft", "video", "filter"), paths,
                         "命令组必须继续递归，不能误当叶命令")
        self.assertEqual(payload["discovery"]["failures"], [])

    def test_previous_leaf_is_reprobed_even_when_parent_help_hides_it(self):
        previous = {"commands": [{"path": ["draft", "project", "rename"],
                                   "options": ["--ref", "--name"],
                                   "summary": "Rename", "help_state": "ok"}]}
        mapping = {
            (): "Root\n\nSUBCOMMANDS:\n  draft  Draft.\n",
            ("draft",): "Draft\n\nSUBCOMMANDS:\n  history  History.\n",
            ("draft", "history"): LEAF_HELP,
            ("draft", "project", "rename"): LEAF_HELP,
        }

        def probe(path):
            return enumerator.ProbeResult("ok", mapping[tuple(path)])

        payload = enumerator.discover_commands(probe, previous=previous, seeds=())
        paths = {tuple(spec["path"]) for spec in payload["commands"]}
        self.assertIn(("draft", "project", "rename"), paths)

    def test_failed_known_probe_preserves_previous_contract_for_evidence(self):
        previous = {"commands": [{"path": ["draft", "project", "list"],
                                   "options": ["--help", "--version", "--jq"],
                                   "summary": "List", "help_state": "ok"}]}

        def probe(path):
            if not path:
                return enumerator.ProbeResult(
                    "ok", "Root\n\nSUBCOMMANDS:\n  draft  Draft.\n")
            if tuple(path) == ("draft",):
                return enumerator.ProbeResult(
                    "ok", "Draft\n\nSUBCOMMANDS:\n  project  Project.\n")
            if tuple(path) == ("draft", "project"):
                return enumerator.ProbeResult(
                    "ok", "Project\n\nSUBCOMMANDS:\n  list  List.\n")
            return enumerator.ProbeResult("timeout", error="fixture timeout")

        payload = enumerator.discover_commands(probe, previous=previous, seeds=())
        self.assertEqual(payload["commands"], previous["commands"])
        errors = enumerator.validate_candidate(
            payload, previous=previous, required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("探测未完成" in error for error in errors),
                        "保留旧值只能用于诊断，默认发布仍须失败")


class PublicationGateTests(unittest.TestCase):
    def candidate(self, commands, failures=()):
        return {"count": len(commands), "commands": commands,
                "discovery": {"probed": len(commands), "groups": [],
                              "failures": list(failures)}}

    def test_old_group_may_be_replaced_by_discovered_leaf_commands(self):
        previous = {"commands": [{"path": ["draft", "video", "filter"],
                                   "options": ["--help"], "help_state": "ok"}]}
        commands = [
            {"path": ["draft", "video", "filter", "add"],
             "options": ["--ref"], "help_state": "ok"},
            {"path": ["draft", "video", "filter", "remove"],
             "options": ["--ref"], "help_state": "ok"},
        ]
        errors = enumerator.validate_candidate(
            self.candidate(commands), previous=previous,
            required_prefixes=(), min_success_ratio=0)
        self.assertEqual(errors, [])

    def test_missing_old_path_without_descendants_blocks_publish(self):
        previous = {"commands": [{"path": ["media", "probe"],
                                   "options": ["--input"], "help_state": "ok"}]}
        commands = [{"path": ["media", "asr"],
                     "options": ["--input"], "help_state": "ok"}]
        errors = enumerator.validate_candidate(
            self.candidate(commands), previous=previous,
            required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("旧命令路径消失" in error for error in errors))

    def test_successful_old_path_may_not_degrade_to_timeout(self):
        previous = {"commands": [{"path": ["media", "probe"],
                                   "options": ["--input"], "help_state": "ok"}]}
        commands = [{"path": ["media", "probe"],
                     "options": [], "help_state": "timeout"}]
        failure = {"path": ["media", "probe"], "state": "timeout", "error": "x"}
        errors = enumerator.validate_candidate(
            self.candidate(commands, [failure]), previous=previous,
            required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("退化" in error for error in errors))
        self.assertTrue(any("探测未完成" in error for error in errors))

    def test_successful_old_path_may_not_lose_business_options(self):
        previous = {"commands": [{"path": ["media", "understand"],
                                   "options": ["--path", "--input", "--help"],
                                   "help_state": "ok"}]}
        commands = [{"path": ["media", "understand"],
                     "options": ["--path", "--help"], "help_state": "ok"}]
        errors = enumerator.validate_candidate(
            self.candidate(commands), previous=previous,
            required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("丢失参数" in error and "--input" in error
                            for error in errors))

    def test_repeated_failure_of_previously_unparsed_path_still_blocks_publish(self):
        previous = {"commands": [{"path": ["draft", "project", "delete"],
                                   "options": [], "help_state": "empty"}]}
        commands = [
            {"path": ["draft", "project", "delete"],
             "options": [], "help_state": "empty"},
            {"path": ["media", "probe"], "options": ["--input"], "help_state": "ok"},
        ]
        failure = {"path": ["draft", "project", "delete"],
                   "state": "timeout", "error": "x"}
        errors = enumerator.validate_candidate(
            self.candidate(commands, [failure]), previous=previous,
            required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("探测未完成" in error for error in errors))

    def test_known_domains_are_independent_of_generated_manifest(self):
        commands = [{"path": ["draft", "video", "add"],
                     "options": ["--ref"], "help_state": "ok"}]
        errors = enumerator.validate_candidate(self.candidate(commands), previous={"commands": []})
        self.assertTrue(any("auth" in error for error in errors))
        self.assertTrue(any("draft history" in error for error in errors))

    def test_duplicate_function_names_block_publish(self):
        commands = [
            {"path": ["draft", "video", "add"], "options": [], "help_state": "ok"},
            {"path": ["video", "add"], "options": [], "help_state": "ok"},
        ]
        errors = enumerator.validate_candidate(
            self.candidate(commands), previous={"commands": []},
            required_prefixes=(), min_success_ratio=0)
        self.assertTrue(any("同一函数名" in error for error in errors))


class MainPublicationTests(unittest.TestCase):
    def test_gate_failure_writes_evidence_but_keeps_engine_manifest_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            engine_path = Path(folder) / "engine.json"
            evidence_path = Path(folder) / "evidence.json"
            previous = {"count": 1, "commands": [
                {"path": ["media", "probe"], "options": ["--input"],
                 "summary": "Probe", "help_state": "ok"}
            ]}
            engine_path.write_text(json.dumps(previous), encoding="utf-8")
            failed = {"count": 0, "commands": [],
                      "discovery": {"probed": 1, "groups": [],
                                    "failures": [{"path": [], "state": "empty",
                                                  "error": "fixture"}]}}
            with patch.object(enumerator, "ENGINE_MANIFEST", engine_path), \
                    patch.object(enumerator, "EVIDENCE_MANIFEST", evidence_path), \
                    patch.object(enumerator, "OfficialHelpProbe", return_value=object()), \
                    patch.object(enumerator, "discover_commands", return_value=failed), \
                    redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                result = enumerator.main([])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(engine_path.read_text(encoding="utf-8")), previous)
            self.assertEqual(json.loads(evidence_path.read_text(encoding="utf-8")), failed)

    def test_reviewed_evidence_requires_force_when_gate_has_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            engine_path = Path(folder) / "engine.json"
            evidence_path = Path(folder) / "evidence.json"
            previous = {"count": 1, "commands": [
                {"path": ["media", "probe"], "options": ["--input"],
                 "summary": "Probe", "help_state": "ok"}
            ]}
            candidate = {"generated_from": "fixture", "count": 1, "commands": [
                {"path": ["media", "probe"], "options": ["--input"],
                 "summary": "Probe", "help_state": "ok"}
            ], "discovery": {"probed": 1, "groups": [], "failures": [
                {"path": ["media", "probe"], "state": "timeout", "error": "fixture"}
            ]}}
            engine_path.write_text(json.dumps(previous), encoding="utf-8")
            evidence_path.write_text(json.dumps(candidate), encoding="utf-8")
            with patch.object(enumerator, "ENGINE_MANIFEST", engine_path), \
                    patch.object(enumerator, "EVIDENCE_MANIFEST", evidence_path), \
                    redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                blocked = enumerator.main(["--publish-evidence"])
                forced = enumerator.main(["--publish-evidence", "--force"])
            self.assertEqual(blocked, 2)
            self.assertEqual(forced, 0)
            self.assertEqual(json.loads(engine_path.read_text(encoding="utf-8")), candidate)


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_produces_valid_lf_json_and_no_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            enumerator.atomic_write_json(path, {"count": 1, "commands": []})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["count"], 1)
            self.assertNotIn(b"\r", path.read_bytes())
            self.assertEqual(list(path.parent.glob("manifest.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
