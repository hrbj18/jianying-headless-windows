import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("official_features", ROOT / "engine/official_features.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OfficialFeatures(unittest.TestCase):
    def test_plain_generated_lyrics_do_not_require_animation_ref(self):
        request = MODULE.build_request({
            "schema": MODULE.PLAN_SCHEMA, "tts": [], "templates": [],
            "lyrics": [{"id": "lyric1", "text": "自动歌词", "start_ms": 0, "end_ms": 1000}],
        })
        self.assertEqual(request["features"]["lyrics"], 1)
        self.assertNotIn("<animation", request["arguments"]["selection_expression"])

    def test_builds_tts_lyrics_and_template_request(self):
        plan = {
            "schema": MODULE.PLAN_SCHEMA,
            "tts": [{"id": "voice_1", "text": "甲<&\"乙", "tone_ref": "tone1", "display": False}],
            "lyrics": [{"id": "lyric_1", "text": "第一句", "start_ms": 0, "end_ms": 1800,
                        "animation_ref": "anim_text1"}],
            "templates": [{"id": "tpl_1", "template_ref": "template1", "title": "片头<&",
                           "start_ms": 0, "duration_ms": 6533, "slots": [
                               {"source_slot_id": "media-slot", "kind": "media", "ref": "video1"},
                               {"source_slot_id": "text-slot", "kind": "text", "content": "标题<&"},
                           ]}],
        }
        result = MODULE.build_request(plan)
        self.assertEqual(result["features"], {"tts": 1, "lyrics": 1, "templates": 1})
        expression = result["arguments"]["selection_expression"]
        self.assertIn("<speech ref=", expression)
        self.assertIn("animation_type=", expression)
        self.assertIn("<template_package", expression)
        self.assertTrue(expression.endswith("draft.apply();"))
        self.assertNotIn("甲<&", expression)
        self.assertEqual({item["asset_type"] for item in result["required_refs"]},
                         {"tone", "anim_text", "template", "local_media"})

    def test_rejects_overlapping_lyrics(self):
        plan = {"schema": MODULE.PLAN_SCHEMA, "lyrics": [
            {"id": "a", "text": "甲", "start_ms": 0, "end_ms": 1000, "animation_ref": "anim1"},
            {"id": "b", "text": "乙", "start_ms": 900, "end_ms": 2000, "animation_ref": "anim1"},
        ]}
        with self.assertRaisesRegex(ValueError, "歌词时间重叠"):
            MODULE.build_request(plan)

    def test_rejects_unbound_resource_shapes(self):
        for ref in ("https://example.test/tone", "7426691632168324367", "C:/tone"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "blueprint_ref"):
                MODULE.build_request({"schema": MODULE.PLAN_SCHEMA, "tts": [
                    {"id": "voice", "text": "测试", "tone_ref": ref, "display": False}
                ]})

    def test_rejects_duplicate_template_slot(self):
        plan = {"schema": MODULE.PLAN_SCHEMA, "templates": [{
            "id": "tpl", "template_ref": "template1", "title": "片头", "duration_ms": 1000,
            "slots": [
                {"source_slot_id": "same", "kind": "text", "content": "甲"},
                {"source_slot_id": "same", "kind": "text", "content": "乙"},
            ],
        }]}
        with self.assertRaisesRegex(ValueError, "重复填写"):
            MODULE.build_request(plan)

    def test_strict_json_rejects_duplicate_key(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "重复字段"):
                MODULE.strict_json(path)

    def test_agent_wrapper_uses_documented_cli_arguments(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "input.json"
            target = Path(directory) / "output.json"
            source.write_text('{"request":true}', encoding="utf-8")

            def run(args, **_kwargs):
                self.assertEqual(args[1:3], ["draft", "fetch-feishu-doc"])
                self.assertEqual(args[3:5], ["--input", str(source)])
                self.assertEqual(args[5:7], ["--output", str(target)])
                target.write_text('{"status":"ok"}', encoding="utf-8")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(MODULE, "doctor", return_value={"official_agent_cli": "agent.exe"}), \
                    mock.patch.object(MODULE.subprocess, "run", side_effect=run), \
                    mock.patch.dict(os.environ, {"JIANYING_AGENT_RUNTIME_TOKEN": "test-token"}):
                self.assertEqual(MODULE.call_agent("fetch-feishu-doc", source, target), {"status": "ok"})

    def test_apply_uses_official_blueprint_selection_command(self):
        plan = {"schema": MODULE.PLAN_SCHEMA, "tts": [
            {"id": "voice", "text": "测试", "tone_ref": "tone1", "display": False}
        ]}
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            workspace = root / "blueprint"
            draft_dir = root / "draft"
            workspace.mkdir()
            draft_dir.mkdir()
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            audit = root / "audit"
            completed = mock.Mock(stdout='{"status":"completed"}\n', stderr="")
            with mock.patch.object(MODULE, "call_lyra", return_value=completed) as invoke:
                result = MODULE.apply_plan(plan_path, workspace, draft_dir, "draft:current", audit)
            arguments, command_root, timeout = invoke.call_args.args
            self.assertEqual(arguments[:3], ["draft", "blueprint", "apply"])
            self.assertIn("--selection-file", arguments)
            self.assertEqual(command_root, draft_dir.resolve())
            self.assertEqual(timeout, 600)
            self.assertEqual(result["status"], "applied")
            self.assertTrue((audit / "selection.expr").read_text(encoding="utf-8").strip()
                            .endswith("draft.apply();"))


if __name__ == "__main__":
    unittest.main()
