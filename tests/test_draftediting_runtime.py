"""DraftEditing 官方链路的离线单元测试。

这些测试不调用剪映：一律替换 ``run_lyra``，只验证命令行组装、前置校验
与结果解析。真实宿主验收需要剪映运行，另行记录在 docs/DRAFTEDITING-RUNTIME.md。
"""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


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
            if list(args[:3]) == ["draft", "project", "create"]:
                root = Path(args[args.index("--dir") + 1])
                name = args[args.index("--ref") + 1][len("local://"):]
                created = root / name
                created.mkdir()
                (created / "draft_content.json").write_text("{}", encoding="utf-8")
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
        (path / "draft_content.json").write_text("{}", encoding="utf-8")
        return path


class DraftRefTests(unittest.TestCase):
    def test_local_ref_shape(self):
        self.assertEqual(MODULE.local_ref("my-draft_1"), "local://my-draft_1")

    def test_local_ref_rejects_paths_and_non_ascii(self):
        for name in ("a/b", "a\\b", "草稿", "", "a b", ".", ".."):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                MODULE.local_ref(name)

    def test_draft_ref_rejects_directory_path(self):
        with self.assertRaises(RuntimeError):
            MODULE._require_draft_ref(r"C:\Users\someone\Draft")


class AsciiPathTests(unittest.TestCase):
    def test_rejects_non_ascii(self):
        with mock.patch.object(MODULE, "_short_path", return_value=None), self.assertRaises(RuntimeError) as caught:
            MODULE.require_ascii_path(r"C:\Users\Administrator\Documents\剪映", "工作区路径")
        self.assertIn("ASCII", str(caught.exception))

    def test_accepts_ascii(self):
        self.assertEqual(MODULE.require_ascii_path(r"C:\Temp\ws", "工作区路径"), r"C:\Temp\ws")

    def test_uses_existing_short_alias_for_unicode_account_path(self):
        short = r"C:\Users\USERNA~1\AppData\Local\Temp\job"
        with mock.patch.object(MODULE, "_short_path", return_value=short) as resolve_short:
            self.assertEqual(MODULE.require_ascii_path(r"C:\Users\中文账户\AppData\Local\Temp\job", "工作区"), short)
        resolve_short.assert_called_once()

    def test_default_workspace_uses_local_configuration(self):
        config = SimpleNamespace(load_config=lambda: {"workspace_root": r"C:\Temp\configured"})
        with mock.patch.dict(sys.modules, {"local_config": config}):
            self.assertEqual(MODULE.default_workspace("job"), Path(r"C:\Temp\configured") / "job")

    def test_scratch_root_prefers_ascii_temp_alias(self):
        with tempfile.TemporaryDirectory(prefix="ascii-scratch-") as folder:
            with mock.patch.dict(os.environ, {"TEMP": folder, "TMP": r"C:\Users\中文账户\Temp"}):
                self.assertEqual(MODULE._scratch_root(), Path(folder))

    def test_scratch_root_does_not_fall_back_to_unusable_unicode_path(self):
        with mock.patch.dict(os.environ, {"TEMP": "C:/中文/tmp", "TMP": "C:/中文/tmp", "LOCALAPPDATA": "C:/中文"}), \
                mock.patch.object(MODULE.tempfile, "gettempdir", return_value="C:/中文/tmp"), \
                mock.patch.object(MODULE, "_short_path", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "ASCII 临时目录"):
                MODULE._scratch_root()


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
        self.assertEqual(args[args.index("--dir") + 1], str(draft.parent))
        self.assertEqual(self.calls[-1]["cwd"], str(draft.parent))
        self.assertEqual(self.calls[-1]["read_only"], [str(selection)])
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

    def test_apply_requires_an_existing_draft_content_file(self):
        workspace = self.workspace()
        outside = self.folder / "elsewhere"
        outside.mkdir()
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();\n", encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            MODULE.blueprint_apply(workspace, outside, "local://elsewhere", selection)
        self.assertIn("draft_content.json", str(caught.exception))

    def test_apply_accepts_explicit_external_project(self):
        workspace = self.workspace()
        external = self.folder / "external" / "new-draft"
        external.mkdir(parents=True)
        (external / "draft_content.json").write_text("synthetic", encoding="utf-8")
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();", encoding="utf-8")
        MODULE.blueprint_apply(workspace, external, "local://new-draft", selection)
        call = self.calls[-1]
        self.assertEqual(call["cwd"], str(external.parent))
        self.assertEqual(call["args"][call["args"].index("--dir") + 1], str(external.parent))
        self.assertIn(str(external), call["read_write"])

    def test_apply_rejects_reference_that_names_another_project(self):
        workspace, draft = self.workspace(), self.draft("draft-apply")
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "目录名必须匹配"):
            MODULE.blueprint_apply(workspace, draft, "local://another-project", selection)
        self.assertFalse(self.calls)

    def test_create_uses_explicit_parent_and_validates_result_location(self):
        root = self.folder / "new-external-root"
        result = MODULE.project_create(root, "local://created", timeout=20)
        call = self.calls[-1]
        self.assertEqual(call["args"], ["draft", "project", "create", "--ref", "local://created", "--dir", str(root)])
        self.assertEqual(call["cwd"], str(root))
        self.assertEqual(result["draft_dir"], str(root / "created"))

    def test_create_rejects_existing_directory_or_path_reference(self):
        existing = self.draft("existing")
        with self.assertRaisesRegex(RuntimeError, "拒绝覆盖"):
            MODULE.project_create(existing.parent, "local://existing")
        for ref in ("local://../escape", "cloud://remote", "local://.."):
            with self.subTest(ref=ref), self.assertRaises(RuntimeError):
                MODULE.project_create(self.folder / "other", ref)
        self.assertFalse(self.calls)

    def test_create_stops_if_official_command_did_not_create_expected_project(self):
        with mock.patch.object(MODULE, "run_lyra", return_value={"result": {"err_code": 0}}):
            with self.assertRaisesRegex(RuntimeError, "未在指定父根"):
                MODULE.project_create(self.folder / "missing-result", "local://new")

    def test_resource_import_uses_local_uri(self):
        workspace = self.workspace()
        source = self.folder / "font.ttf"
        source.write_bytes(b"font")
        MODULE.blueprint_resource_import(workspace, source, "draft-font")
        args = self.calls[-1]["args"]
        self.assertEqual(args[args.index("--import") + 1], "local:///" + source.as_posix().lstrip("/"))
        self.assertEqual(self.calls[-1]["read_only"], [str(source)])

    def test_resource_import_can_keep_shared_external_resolution_root(self):
        workspace = self.workspace()
        source = self.folder / "source.mp4"
        source.write_bytes(b"synthetic")
        MODULE.blueprint_resource_import(workspace, source, "video", draft_root=self.draft_root)
        self.assertEqual(self.calls[-1]["cwd"], str(self.draft_root))

    def test_cli_preserves_hash_revision_and_explicit_start_flag(self):
        workspace, draft = self.workspace(), self.draft("cli-draft")
        selection = workspace / "edit.selection"
        selection.write_text("draft.apply();", encoding="utf-8")
        with mock.patch.object(MODULE, "ensure_editor_running", return_value=1) as start, contextlib.redirect_stdout(io.StringIO()):
            MODULE.main(["apply", "--workspace", str(workspace), "--draft-dir", str(draft), "--ref", "local://cli-draft",
                         "--selection-file", str(selection), "--base-revision", "145c3c70bb7f2c66", "--start-editor"])
        start.assert_called_once_with()
        args = self.calls[-1]["args"]
        self.assertEqual(args[args.index("--base-revision") + 1], "145c3c70bb7f2c66")

    def test_cli_generic_run_keeps_flags_and_explicit_permissions(self):
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE.main(["run", "--cwd", str(self.draft_root), "--read-write", str(self.draft_root),
                         "--timeout", "20", "--", "draft", "project", "extract", "--ref", "local://demo"])
        self.assertEqual(self.calls[-1]["args"], ["draft", "project", "extract", "--ref", "local://demo"])
        self.assertEqual(self.calls[-1]["read_write"], [str(self.draft_root)])
        self.assertEqual(self.calls[-1]["timeout"], 20)

    def test_cli_without_start_flag_does_not_launch_editor(self):
        with mock.patch.object(MODULE, "ensure_editor_running") as start, contextlib.redirect_stdout(io.StringIO()):
            MODULE.main(["state", "--workspace", str(self.workspace())])
        start.assert_not_called()


class HostAndDoctorTests(unittest.TestCase):
    def test_verified_existing_host_is_reused_without_launching(self):
        with mock.patch.object(MODULE.windows_runtime, "validate_runtime", return_value={"install_dir": r"C:\Jianying"}), \
                mock.patch.object(MODULE, "find_official_parent", return_value=123), \
                mock.patch.object(MODULE.subprocess, "Popen") as launch:
            self.assertEqual(MODULE.ensure_editor_running(), 123)
        launch.assert_not_called()

    def test_explicit_start_launches_verified_install_then_waits_for_host(self):
        install = Path(r"C:\Jianying")
        with mock.patch.object(MODULE.windows_runtime, "validate_runtime", return_value={"install_dir": str(install)}), \
                mock.patch.object(MODULE, "find_official_parent", side_effect=[MODULE.EditorNotRunning("missing"), 456]), \
                mock.patch.object(MODULE.subprocess, "Popen") as launch:
            self.assertEqual(MODULE.ensure_editor_running(), 456)
        self.assertEqual(launch.call_args.args[0], [str(install / "JianyingPro.exe")])

    def test_running_unverified_version_does_not_trigger_second_launch(self):
        with mock.patch.object(MODULE.windows_runtime, "validate_runtime", return_value={"install_dir": r"C:\Jianying"}), \
                mock.patch.object(MODULE, "find_official_parent", side_effect=RuntimeError("other version")), \
                mock.patch.object(MODULE.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "other version"):
                MODULE.ensure_editor_running()
        launch.assert_not_called()

    def test_host_override_cannot_select_another_installation(self):
        with mock.patch.dict(os.environ, {"JIANYING_HOST_PID": "10"}), \
                mock.patch.object(MODULE, "_win32_process_list", return_value=[{"name": "JianyingPro.exe", "pid": 10}]), \
                mock.patch.object(MODULE, "_win32_image_path", return_value=r"C:\OtherVersion\JianyingPro.exe"):
            with self.assertRaisesRegex(RuntimeError, "不属于已验证安装路径"):
                MODULE.find_official_parent(Path(r"C:\VerifiedVersion"))

    def test_doctor_is_read_only_when_editor_and_bun_copy_are_missing(self):
        folder = scratch("doctor-")
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        runtime = {"install_dir": str(folder), "runtime_profile": "test", "app_build": "11.4.7.14462"}
        with mock.patch.object(MODULE.windows_runtime, "doctor", return_value=runtime), \
                mock.patch.object(MODULE, "find_official_parent", side_effect=MODULE.EditorNotRunning("missing")), \
                mock.patch.object(MODULE, "ensure_packaged_bun") as copy_bun, \
                mock.patch.object(MODULE.subprocess, "Popen") as launch:
            result = MODULE.doctor()
        copy_bun.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(result["status"], "warning")
        self.assertFalse(result["editor_running"])
        self.assertFalse((folder / "bun-packaged-server.exe").exists())


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
    def test_informational_plain_output_is_not_mistaken_for_failed_action(self):
        self.assertEqual(MODULE.parse_cli_payload('USAGE: lyra-cli draft ...', ['draft', '--help']),
                         {'output': 'USAGE: lyra-cli draft ...'})
        self.assertEqual(MODULE.parse_cli_payload('11.4.7', ['--version']), {'output': '11.4.7'})

    def test_actions_and_errors_still_require_a_success_envelope(self):
        for payload, args in [('ordinary output', ['draft', 'config']),
                              ('{"err_code": -1}', ['--help']), ('', ['--help']),
                              ('[]', ['--help'])]:
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                MODULE.parse_cli_payload(payload, args)
        self.assertEqual(MODULE.parse_cli_payload('{"err_code":0,"result":{}}', ['draft', 'config'])['err_code'], 0)

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
