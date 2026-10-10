"""DraftEditing 官方链路的离线单元测试。

这些测试不调用剪映：一律替换 ``run_lyra``，只验证命令行组装、前置校验
与结果解析。真实宿主验收需要剪映运行，另行记录在 docs/DRAFTEDITING-RUNTIME.md。
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
SPEC = importlib.util.spec_from_file_location("draftediting_runtime", ROOT / "engine/draftediting_runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def scratch(prefix):
    """官方沙箱要求纯 ASCII 路径，而本仓库位于中文目录，因此临时根必须在别处。"""
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "draftediting-tests"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))


class Harness(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.original = MODULE.run_lyra
        self.original_root = MODULE.windows_runtime.DRAFT_ROOT

        def fake(args, cwd, timeout=600, read_write_paths=(), read_only_paths=()):
            self.calls.append({"args": list(args), "cwd": str(cwd), "timeout": timeout,
                               "read_write": [str(p) for p in read_write_paths],
                               "read_only": [str(p) for p in read_only_paths]})
            return {"command": list(args), "result": {"err_code": 0, "result": {}},
                    "stdout": "", "stderr": "", "host_pid": 1}

        MODULE.run_lyra = fake
        self.addCleanup(self.restore)
        folder = scratch("case-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        self.folder = folder
        self.draft_root = folder / "drafts"
        self.draft_root.mkdir()
        MODULE.windows_runtime.DRAFT_ROOT = self.draft_root

    def restore(self):
        MODULE.run_lyra = self.original
        MODULE.windows_runtime.DRAFT_ROOT = self.original_root

    def workspace(self):
        path = self.folder / "ws"
        path.mkdir(exist_ok=True)
        (path / "blueprint.json").write_text(json.dumps({"target_revision": 1}), encoding="utf-8")
        return path

    def draft(self, name="draft-a"):
        path = self.draft_root / name
        path.mkdir(exist_ok=True)
        return path


class DraftRefTests(unittest.TestCase):
    def test_local_ref_shape(self):
        self.assertEqual(MODULE.local_ref("my-draft_1"), "local://my-draft_1")

    def test_local_ref_rejects_paths_and_non_ascii(self):
        for name in ("a/b", "a\\b", "草稿", "", "a b"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                MODULE.local_ref(name)

    def test_draft_ref_rejects_directory_path(self):
        with self.assertRaises(RuntimeError):
            MODULE._require_draft_ref(r"C:\Users\someone\Draft")


class AsciiPathTests(unittest.TestCase):
    def test_rejects_non_ascii(self):
        with self.assertRaises(RuntimeError) as caught:
            MODULE.require_ascii_path(r"C:\Users\Administrator\Documents\剪映", "工作区路径")
        self.assertIn("ASCII", str(caught.exception))

    def test_accepts_ascii(self):
        self.assertEqual(MODULE.require_ascii_path(r"C:\Temp\ws", "工作区路径"), r"C:\Temp\ws")


class CommandAssembly(Harness):
    def test_sync_uses_local_ref_and_draft_root_as_cwd(self):
        workspace, draft_root = self.workspace(), self.draft_root
        MODULE.blueprint_sync(workspace, "local://draft-a", draft_root, current_only=True, timeout=60)
        call = self.calls[-1]
        self.assertEqual(call["args"], ["draft", "blueprint", "sync", "--workspace", str(workspace),
                                        "--ref", "local://draft-a", "--current-only"])
        self.assertEqual(call["cwd"], str(draft_root))
        self.assertIn(str(workspace), call["read_write"])

    def test_apply_passes_official_flags_and_only_given_revision(self):
        workspace, draft = self.workspace(), self.draft("draft-apply")
        selection = workspace / "edit.selection"
        selection.write_text("draft.select(\"multi\").empty();\ndraft.apply();\n", encoding="utf-8")
        MODULE.blueprint_apply(workspace, draft, "local://draft-apply", selection)
        args = self.calls[-1]["args"]
        self.assertEqual(args[:3], ["draft", "blueprint", "apply"])
        self.assertIn("--allow-existing-main-deletion", args)
        self.assertIn("--allow-existing-subtitle-changes", args)
        # blueprint.json 没有 canonical_revision 时不得伪造哈希。
        self.assertNotIn("--base-revision", args)

    def test_apply_forwards_explicit_revision(self):
        workspace, draft = self.workspace(), self.draft("draft-apply")
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();\n", encoding="utf-8")
        MODULE.blueprint_apply(workspace, draft, "local://draft-apply", selection, base_revision="145c3c70bb7f2c66")
        args = self.calls[-1]["args"]
        self.assertEqual(args[args.index("--base-revision") + 1], "145c3c70bb7f2c66")

    def test_apply_rejects_complete_document_selection(self):
        workspace, draft = self.workspace(), self.draft("draft-apply")
        selection = workspace / "edit.selection"
        selection.write_text("<draft></draft>", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            MODULE.blueprint_apply(workspace, draft, "local://draft-apply", selection)

    def test_apply_requires_draft_inside_native_root(self):
        workspace = self.workspace()
        outside = self.folder / "elsewhere"
        outside.mkdir()
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();\n", encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            MODULE.blueprint_apply(workspace, outside, "local://elsewhere", selection)
        self.assertIn("草稿根", str(caught.exception))

    def test_resource_import_uses_local_uri(self):
        workspace = self.workspace()
        source = self.folder / "font.ttf"
        source.write_bytes(b"font")
        MODULE.blueprint_resource_import(workspace, source, "draft-font")
        args = self.calls[-1]["args"]
        self.assertEqual(args[args.index("--import") + 1], "local:///" + source.as_posix().lstrip("/"))
        self.assertEqual(self.calls[-1]["read_only"], [str(source)])


class InitTests(Harness):
    def test_init_rejects_non_empty_workspace(self):
        workspace = self.workspace()
        (workspace / "leftover.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            MODULE.blueprint_init(workspace)
        self.assertIn("空目录", str(caught.exception))

    def test_init_accepts_empty_directory(self):
        workspace = self.folder / "empty-ws"
        workspace.mkdir()
        MODULE.blueprint_init(workspace)
        self.assertEqual(self.calls[-1]["args"][:4], ["draft", "blueprint", "init", "--workspace"])


class EnvelopeTests(unittest.TestCase):
    def test_read_envelope_tolerates_missing_and_partial_json(self):
        folder = scratch("envelope-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        target = folder / "result.json"
        self.assertIsNone(MODULE._read_envelope(target))
        target.write_text("", encoding="utf-8")
        self.assertIsNone(MODULE._read_envelope(target))
        target.write_text('{"partial":', encoding="utf-8")
        self.assertIsNone(MODULE._read_envelope(target))
        target.write_text('{"ok": true}', encoding="utf-8")
        self.assertEqual(MODULE._read_envelope(target), {"ok": True})

    def test_workspace_revision_only_reads_explicit_field(self):
        folder = scratch("revision-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        self.assertIsNone(MODULE.workspace_revision(folder))
        (folder / "blueprint.json").write_text(json.dumps({"target_revision": 3}), encoding="utf-8")
        self.assertIsNone(MODULE.workspace_revision(folder))
        (folder / "blueprint.json").write_text(json.dumps({"canonical_revision": "145c3c70bb7f2c66"}), encoding="utf-8")
        self.assertEqual(MODULE.workspace_revision(folder), "145c3c70bb7f2c66")


if __name__ == "__main__":
    unittest.main()
