#!/usr/bin/env python3
"""通过剪映官方 VMSDK 调用 DraftEditing / Blueprint 命令。

本模块只包装剪映自带的官方链路，不实现资源服务、不读取账号数据、
不提取运行令牌。官方宿主校验要求三项同时成立：

1. 已验证安装路径中的剪映主进程（JianyingPro.exe）正在运行；
2. 剪映官方 VMSDK（agent_runtime_addon.node）；
3. 签名有效且名为 bun-packaged-server.exe 的官方 Bun 副本。

命令契约取自同版本 ``Resources/canvas_agent/runtime/app-server.mjs``：
``draft blueprint init``、``draft blueprint sync``（含 ``--current-only``）、
``draft blueprint apply``、``draft blueprint resource``、``draft project create``、
``media probe``。命令通过官方签名 Bun worker 启动，不伪造父进程。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import windows_runtime


WORKER = Path(__file__).with_name("draftediting_worker.mjs")
SELECTION_FILE = "edit.selection"
BLUEPRINT_FILES = ("blueprint.json", "target_draft.xml", "current_draft.xml",
                   "selection_index.txt", "resource_map.json", "id_map.json")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class EditorNotRunning(RuntimeError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _powershell_json(script, values=None, timeout=30):
    # Codex/PowerShell 7 的模块环境不能直接交给 Windows PowerShell 5.1。
    # 使用最小环境，让 5.1 从 System32 加载 Security/CimCmdlets。
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {key: os.environ[key] for key in
           ("TEMP", "TMP", "LOCALAPPDATA", "USERPROFILE") if key in os.environ}
    env.update({"SystemRoot": system_root, "windir": system_root,
                "PATH": system_root + r"\System32"})
    env.update(values or {})
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )
    require(completed.returncode == 0, completed.stderr.strip() or "PowerShell 调用失败")
    return json.loads(completed.stdout.lstrip("\ufeff").strip())


def _win32_process_list():
    """用 Toolhelp32 枚举进程，不依赖可能被禁用的 WMI/CIM。"""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    require(snapshot not in (0, ctypes.c_void_p(-1).value), "无法枚举进程快照")
    rows = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            rows.append({"pid": int(entry.th32ProcessID), "parent": int(entry.th32ParentProcessID),
                         "name": entry.szExeFile})
            present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return rows


def _win32_image_path(pid):
    """返回进程映像的完整路径；无权限时返回 None，由调用方决定是否降级。"""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def _window_owner_pids():
    """返回拥有可见顶层窗口的进程号集合。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = set()

    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                found.add(int(pid.value))
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return found


def find_official_parent(install):
    """返回受信任的剪映主进程 PID；优先选择真正拥有主窗口的实例。"""
    install = Path(install)
    expected = str(install / "JianyingPro.exe")
    candidates = [row for row in _win32_process_list()
                  if row["name"].lower() == "jianyingpro.exe"]
    if not candidates:
        raise EditorNotRunning("剪映未运行；可在命令中添加 --start-editor 启动已验证的正版剪映")
    matched = [row for row in candidates
               if (path := _win32_image_path(row["pid"]))
               and os.path.normcase(path) == os.path.normcase(expected)]
    require(matched, "已运行的剪映不属于已验证安装路径；请关闭其它版本后再使用 --start-editor")
    override = os.environ.get("JIANYING_HOST_PID")
    if override:
        try:
            pid = int(override)
        except ValueError as error:
            raise RuntimeError("JIANYING_HOST_PID 必须是整数") from error
        require(any(row["pid"] == pid for row in matched),
                "JIANYING_HOST_PID 不是已验证安装路径中的剪映主进程")
        return pid
    windows = _window_owner_pids()
    for row in matched:
        if row["pid"] in windows:
            return row["pid"]
    return matched[0]["pid"]


def ensure_editor_running(timeout=30):
    """仅在显式请求时启动已验签安装；已运行同版本时复用现有宿主。"""
    runtime = windows_runtime.validate_runtime()
    install = Path(runtime["install_dir"])
    try:
        return find_official_parent(install)
    except EditorNotRunning:
        pass
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.Popen([str(install / "JianyingPro.exe")], cwd=str(install),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, startupinfo=startup)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return find_official_parent(install)
        except EditorNotRunning:
            time.sleep(0.25)
    raise RuntimeError("已启动正版剪映，但在等待时间内未发现已验证路径的宿主进程")


def ensure_packaged_bun(install):
    """官方 worker 以 PE 内部名识别宿主，因此需要同名且签名有效的官方副本。"""
    install = Path(install)
    source = install / "bun.exe"
    target = install / "bun-packaged-server.exe"
    require(source.is_file(), "剪映安装缺少 bun.exe")
    if not target.is_file() or _sha256(target) != _sha256(source):
        shutil.copy2(source, target)
    require(_sha256(target) == _sha256(source), "bun-packaged-server.exe 与官方 bun.exe 不一致")
    script = r'''
$s = Get-AuthenticodeSignature -LiteralPath $env:JY_BUN
@{ status=$s.Status.ToString(); subject=$s.SignerCertificate.Subject } | ConvertTo-Json -Compress
'''
    signature = _powershell_json(script, {"JY_BUN": str(target)})
    require(signature.get("status") == "Valid" and windows_runtime.PUBLISHER in signature.get("subject", ""),
            "bun-packaged-server.exe 的官方签名验证失败")
    return target


def _resolve(path):
    return require_ascii_path(Path(path).resolve(), "沙箱授权路径")


def _short_path(path):
    """保留真实文件位置，以 Windows 8.3 别名处理含中文的账户目录。"""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    original = Path(path).absolute()
    existing, suffix = original, []
    while not existing.exists():
        if existing.parent == existing:
            return None
        suffix.insert(0, existing.name)
        existing = existing.parent
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_short = kernel32.GetShortPathNameW
    get_short.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    get_short.restype = wintypes.DWORD
    needed = get_short(str(existing), None, 0)
    if not needed:
        return None
    buffer = ctypes.create_unicode_buffer(needed)
    written = get_short(str(existing), buffer, needed)
    if not written or written >= needed:
        return None
    result = str(Path(buffer.value).joinpath(*suffix))
    return result if result.isascii() else None


def require_ascii_path(path, label):
    """官方沙箱策略在非 ASCII 路径上会编码错误并使 lyra-cli 崩溃（0xC0000005）。"""
    text = str(path)
    if not text.isascii():
        text = _short_path(path) or text
    require(text.isascii(), label + " 必须是纯 ASCII 路径，官方沙箱策略无法处理非 ASCII 路径: " + text)
    return text


def default_workspace(name="workspace"):
    """在纯 ASCII 的临时根下给出工作区路径（本仓库本身位于中文目录）。"""
    try:
        from local_config import load_config
        configured = load_config().get("workspace_root")
    except ImportError:
        configured = None
    base = Path(configured) if configured else _scratch_root() / "jianying-draftediting"
    require(name not in (".", "..") and bool(re.fullmatch(r"[A-Za-z0-9._-]+", name)), "工作区名称必须是 ASCII 单层目录名")
    return Path(require_ascii_path(base / name, "工作区路径"))


def _trace_dir():
    """留痕目录：默认在任务工作区下的 draftediting-traces。"""
    base = os.environ.get("JY_DRAFTEDITING_TRACE_DIR")
    directory = Path(base) if base else Path(__file__).resolve().parent.parent / "work/draftediting-traces"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _trace_label(args):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", "_".join(args[1:4])) or "command"


def _write_trace(envelope, args):
    """失败时把官方 worker 的完整 envelope 留痕，便于区分权限、宿主与参数问题。"""
    try:
        path = _trace_dir() / (time.strftime("%Y%m%d-%H%M%S") + "-" + _trace_label(args) + ".json")
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


def _keep_progress(result_path, args):
    """把 worker 的逐步进度复制到留痕目录：同步阻塞时这是唯一的证据。"""
    source = Path(str(result_path) + ".progress")
    if not source.is_file():
        return None
    try:
        path = _trace_dir() / (time.strftime("%Y%m%d-%H%M%S") + "-" + _trace_label(args) + ".progress")
        shutil.copyfile(source, path)
        return path
    except OSError:
        return None


def _read_envelope(result_path):
    """读取官方 worker 的结果文件；尚未写完或不可读时返回 None。"""
    try:
        data = Path(result_path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not data.strip():
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _scratch_root():
    """选择纯 ASCII 且可写的临时根；官方沙箱策略与子进程 TEMP 都要求 ASCII。"""
    candidates = [Path(os.environ["TEMP"]) if os.environ.get("TEMP") else None,
                  Path(os.environ["TMP"]) if os.environ.get("TMP") else None,
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" if os.environ.get("LOCALAPPDATA") else None,
                  Path(tempfile.gettempdir())]
    for base in candidates:
        if base is None:
            continue
        try:
            base = Path(require_ascii_path(base, "临时目录"))
            base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=str(base)):
                pass
            return base
        except (OSError, RuntimeError):
            continue
    raise RuntimeError("没有可写的 ASCII 临时目录；请将 TEMP/TMP 指向 ASCII 路径，或启用现有目录的 8.3 别名")


def parse_cli_payload(payload, args):
    """Successful informational CLI responses use plain text, actions use envelopes."""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        parsed = {"output": payload}
    informational = any(flag in args for flag in ("--help", "--version"))
    plain_help = (informational and isinstance(parsed, dict) and
                  set(parsed) == {"output"} and isinstance(parsed["output"], str) and parsed["output"].strip())
    require(plain_help or (isinstance(parsed, dict) and parsed.get("err_code") == 0),
            "lyra-cli 返回错误: " + json.dumps(parsed, ensure_ascii=False)[:800])
    return parsed


def run_lyra(args, cwd, timeout=600, read_write_paths=(), read_only_paths=(),
             extra_env=None):
    """在官方 VMSDK 沙箱内执行一次 lyra-cli 命令。

    ``extra_env`` 里的键值会注入 worker（及其子进程）的环境，用于传递调用方需要的
    开关，而不必改写宿主进程的环境变量。
    """
    runtime = windows_runtime.validate_runtime()
    install = Path(runtime["install_dir"])
    parent_pid = find_official_parent(install)
    ensure_packaged_bun(install)
    cwd = Path(require_ascii_path(Path(cwd).resolve(strict=True), "命令工作目录"))
    request = {
        "installDir": str(install),
        "args": list(args),
        "cwd": str(cwd),
        "env": {"LYRA_CLI_ROOT_WORKSPACE": str(cwd),
                "CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE": str(cwd)},
        "timeoutMs": int(timeout * 1000),
        "readOnlyPaths": [_resolve(path) for path in read_only_paths],
        "readWritePaths": [_resolve(path) for path in read_write_paths],
    }
    scratch = tempfile.mkdtemp(prefix="draftediting-", dir=str(_scratch_root()))
    result_path = Path(scratch) / "result.json"
    try:
        env = dict(os.environ)
        env.pop("CUSTOM_AGENT_SANDBOX_OWNER", None)
        env.pop("CUSTOM_AGENT_PARENT_PROCESS_ID", None)
        env.pop("AGENT_HOST_PARENT_PROCESS_ID", None)
        env.pop("CUSTOM_AGENT_PROCESS_NAME", None)
        env.update({
            # preload 会依次从这些位置解析 agent_runtime_addon.node 与 vm_sdk；
            # 显式给出安装目录，避免依赖 import.meta.url 之外的相对回退。
            "AGENT_RUNTIME_ADDON_PATH": str(install / "agent_runtime_addon.node"),
            "CUSTOM_AGENT_NATIVE_ADDON_DIR": str(install),
            "TEMP": scratch, "TMP": scratch, "TMPDIR": scratch,
            "JY_DRAFTEDITING_INPUT_B64": base64.b64encode(
                json.dumps(request, ensure_ascii=False).encode("utf-8")).decode("ascii"),
            "JY_DRAFTEDITING_RESULT": str(result_path),
        })
        for key, value in (extra_env or {}).items():
            env[str(key)] = str(value)
        stdout_log = Path(scratch) / "stdout.log"
        stderr_log = Path(scratch) / "stderr.log"
        with stdout_log.open("wb") as out, stderr_log.open("wb") as err:
            process = subprocess.Popen(
                [str(install / "bun.exe"), "--preload",
                 str(install / "Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs"),
                 str(WORKER)],
                stdout=out, stderr=err, env=env,
            )
        # 官方 worker 可能在收尾阶段挂住。以结果文件为准，而不是进程退出。
        deadline = time.monotonic() + timeout + 45
        envelope = None
        while True:
            envelope = _read_envelope(result_path)
            if envelope is not None:
                break
            if process.poll() is not None:
                envelope = _read_envelope(result_path)
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
        if envelope is None:
            progress = _keep_progress(result_path, args)
            stderr_text = stderr_log.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError("DraftEditing 命令未返回结果（超时或 worker 提前退出）"
                               + ("；进度留痕: " + str(progress) if progress else "")
                               + ("；stderr: " + stderr_text[-800:] if stderr_text.strip() else ""))
    finally:
        # 子进程可能仍持有句柄；清理失败不能掩盖真实结果。
        _keep_progress(result_path, args)
        shutil.rmtree(scratch, ignore_errors=True)
    require(not envelope.get("error"), "DraftEditing worker 失败: " + str(envelope.get("error")))
    response = envelope.get("responseMessage") or {}
    require(response.get("ok"), "官方沙箱拒绝该命令: " + json.dumps(response, ensure_ascii=False)[:800])
    result = response["result"]
    if not result.get("ok"):
        trace = _write_trace(envelope, args)
        detail = json.dumps({key: result.get(key) for key in
                             ("exitCode", "timedOut", "durationMs", "stderr", "stdout")},
                            ensure_ascii=False, indent=2)[:1500]
        raise RuntimeError("lyra-cli 调用失败: " + detail + ("\n完整证据: " + str(trace) if trace else ""))
    payload = result.get("stdout", "").strip()
    parsed = parse_cli_payload(payload, args)
    return {"command": list(args), "result": parsed, "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""), "host_pid": parent_pid,
            "duration_ms": result.get("durationMs")}


def blueprint_init(workspace, timeout=180):
    workspace = Path(require_ascii_path(Path(workspace).resolve(), "工作区路径"))
    if workspace.exists():
        require(workspace.is_dir(), "工作区路径必须是目录: " + str(workspace))
        require(not any(workspace.iterdir()),
                "官方 blueprint init 只接受空目录或不存在的路径；请换一个新工作区或先清空: " + str(workspace))
    else:
        workspace.mkdir(parents=True, exist_ok=True)
    return run_lyra(["draft", "blueprint", "init", "--workspace", str(workspace)],
                    workspace.parent, timeout, [workspace, workspace.parent])


def local_ref(name):
    """草稿引用形如 local://<name>；官方只接受引用而不是目录路径。"""
    require(isinstance(name, str) and name not in (".", "..") and re.fullmatch(r"[A-Za-z0-9._-]+", name),
            "草稿名称只能包含 ASCII 字母、数字、点、下划线或连字符: " + str(name))
    return "local://" + name


def _require_draft_ref(ref):
    require(isinstance(ref, str) and re.fullmatch(r"(?:local|cloud)://[!-~]+", ref),
            "草稿引用必须是 local://<name> 或 cloud://<name>: " + str(ref))
    return ref


def _local_ref_name(ref):
    _require_draft_ref(ref)
    require(ref.startswith("local://"), "本地工程操作要求 local://<目录名> 引用")
    name = ref[len("local://"):]
    require(local_ref(name) == ref, "本地草稿引用必须与目录名一一对应")
    return name


def project_create(draft_root, ref, timeout=180):
    """在明确指定的父根中创建全新工程，不覆盖已有目录。"""
    name = _local_ref_name(ref)
    root = Path(require_ascii_path(Path(draft_root).resolve(), "草稿父根目录"))
    root.mkdir(parents=True, exist_ok=True)
    require(root.is_dir(), "草稿父根必须是目录")
    target = root / name
    require(not target.exists(), "草稿目录已存在，拒绝覆盖: " + str(target))
    result = run_lyra(["draft", "project", "create", "--ref", ref, "--dir", str(root)],
                      root, timeout, [root])
    require(target.is_dir() and (target / "draft_content.json").is_file(),
            "官方 create 未在指定父根生成预期草稿，停止后续编辑: " + str(target))
    return dict(result, draft_dir=str(target), draft_root=str(root))


def blueprint_sync(workspace, ref, draft_root, current_only=False, timeout=600):
    """把草稿同步为 canonical XML。

    ``ref`` 形如 ``local://<名称>``，名称相对 ``draft_root``（该目录同时作为
    官方子进程的 cwd 与读写白名单），目录必须使用纯 ASCII 路径。
    """
    workspace = Path(require_ascii_path(Path(workspace).resolve(strict=True), "工作区路径"))
    draft_root = Path(require_ascii_path(Path(draft_root).resolve(strict=True), "草稿根目录"))
    args = ["draft", "blueprint", "sync", "--workspace", str(workspace),
            "--ref", _require_draft_ref(ref)]
    if current_only:
        args.append("--current-only")
    return run_lyra(args, draft_root, timeout, [workspace, draft_root])


def workspace_revision(workspace):
    """读取工作区记录的 canonical 版本。

    官方 apply 的 ``--base-revision`` 是 canonical XML 的哈希（例如
    ``145c3c70bb7f2c66``），只有当 blueprint.json 明确给出 ``canonical_revision``
    时才使用；否则返回 None，让 lyra-cli 依据自身工作区状态判定，绝不猜造哈希。
    """
    path = Path(workspace) / "blueprint.json"
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = state.get("canonical_revision")
    return value if isinstance(value, str) and value else None


def require_draft_root(draft_dir, ref=None):
    """校验显式指定的工程副本；官方外部工程可位于默认草稿根以外。"""
    resolved = Path(draft_dir).resolve(strict=True)
    require(resolved.is_dir() and (resolved / "draft_content.json").is_file(),
            "草稿目录必须包含已有 draft_content.json；请先 create 或使用任务自有副本: " + str(resolved))
    if ref is not None:
        name = _local_ref_name(ref)
        require(os.path.normcase(resolved.name) == os.path.normcase(name),
                "--draft-dir 目录名必须匹配 local:// 草稿引用，避免改到其它工程")
    return resolved


def blueprint_apply(workspace, draft_dir, ref, selection_file,
                    base_revision=None, timeout=900):
    """应用一份 Selection Expression；草稿目录必须是任务自有的副本。"""
    workspace = Path(require_ascii_path(Path(workspace).resolve(strict=True), "工作区路径"))
    draft_dir = Path(require_ascii_path(require_draft_root(draft_dir, ref), "草稿目录"))
    selection_file = Path(require_ascii_path(Path(selection_file).resolve(strict=True), "Selection 文件"))
    require(selection_file.is_file() and selection_file.stat().st_size > 0, "Selection 文件为空")
    expression = selection_file.read_text(encoding="utf-8")
    require(not expression.lstrip().startswith("<draft"), "Selection 不能是完整 <draft> 文档")
    if base_revision is None:
        base_revision = workspace_revision(workspace)
    args = ["draft", "blueprint", "apply", "--workspace", str(workspace),
            "--dir", str(draft_dir.parent), "--ref", _require_draft_ref(ref),
            "--selection-file", str(selection_file),
            "--allow-existing-main-deletion", "--allow-existing-subtitle-changes"]
    if base_revision is not None:
        args += ["--base-revision", str(base_revision)]
    return run_lyra(args, draft_dir.parent, timeout, [workspace, draft_dir], [selection_file])


def blueprint_resource_search(workspace, search, timeout=300):
    """调用官方资源检索，并把命中的资源写进工作区 resource_map。

    ``search`` 是官方要求的数组，每项形如 ``{"type": "subtitle_template", "keyword": "歌词"}``；
    返回的 ``assets[].asset_id`` 可直接作为 Selection 里的 ``ref`` 使用。检索需要账号权益与
    网络，本函数不代做授权，只转发官方命令。
    """
    workspace = Path(require_ascii_path(Path(workspace).resolve(strict=True), "工作区路径"))
    require(isinstance(search, list) and search, "检索条件必须是非空数组")
    payload = {"mode": "knowledge_then_vimo", "search": search}
    args = ["draft", "blueprint", "resource", "--workspace", str(workspace),
            "--search", json.dumps(payload, ensure_ascii=False)]
    return run_lyra(args, workspace, timeout, [workspace])


def blueprint_resource_import(workspace, path, title, timeout=180, draft_root=None):
    """把本地文件导入 Blueprint 资源库，使其可作为 XML 的 ref 使用。"""
    workspace = Path(require_ascii_path(Path(workspace).resolve(strict=True), "工作区路径"))
    path = Path(require_ascii_path(Path(path).resolve(strict=True), "本地素材路径"))
    require(path.is_file(), "导入资源必须是文件: " + str(path))
    require(isinstance(title, str) and title.strip(), "资源标题不能为空")
    # 官方只接受 local:///<绝对路径> 形式的导入 URI。
    uri = "local:///" + path.as_posix().lstrip("/")
    args = ["draft", "blueprint", "resource", "--workspace", str(workspace),
            "--import", uri, "--title", title]
    cwd = Path(require_ascii_path(Path(draft_root).resolve(strict=True), "草稿父根目录")) if draft_root else workspace
    return run_lyra(args, cwd, timeout, [workspace], [path])


def write_selection(workspace, expression):
    """把 Selection Expression 写入工作区，返回可供 --selection-file 使用的路径。"""
    require(isinstance(expression, str) and expression.strip(), "Selection Expression 不能为空")
    workspace = Path(require_ascii_path(Path(workspace).resolve(strict=True), "工作区路径"))
    target = workspace / SELECTION_FILE
    target.write_text(expression if expression.endswith("\n") else expression + "\n", encoding="utf-8")
    return target


def workspace_state(workspace):
    """读取 blueprint 工作区状态；缺失文件按空值处理，不猜测。"""
    workspace = Path(workspace)
    state = {"workspace": str(workspace), "files": {}}
    for name in BLUEPRINT_FILES:
        path = workspace / name
        state["files"][name] = {"exists": path.is_file(),
                                "size": path.stat().st_size if path.is_file() else 0}
    blueprint_path = workspace / "blueprint.json"
    if blueprint_path.is_file():
        state["blueprint"] = json.loads(blueprint_path.read_text(encoding="utf-8"))
    return state


def doctor():
    """只读检查；不启动剪映、不创建 Bun 副本、不调用官方编辑命令。"""
    runtime = windows_runtime.doctor()
    install = Path(runtime["install_dir"])
    warnings = []
    try:
        parent = find_official_parent(install)
    except RuntimeError as error:
        parent = None
        warnings.append(str(error))
    packaged = install / "bun-packaged-server.exe"
    source = install / "bun.exe"
    same_bun = packaged.is_file() and source.is_file() and _sha256(packaged) == _sha256(source)
    if not same_bun:
        warnings.append("首次执行动作时需要创建与官方 bun.exe 同字节的 bun-packaged-server.exe 副本")
    preload = install / "Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs"
    worker_target = install / "Resources/canvas_agent/runtime/hub-agent-tool-worker.mjs"
    assets_ready = all(path.is_file() for path in (source, preload, worker_target, install / "lyra-cli.exe", install / "agent_runtime_addon.node"))
    if not assets_ready:
        warnings.append("当前剪映安装缺少官方 Lyra/Bun/VMSDK worker 文件")
    return {
        "status": "ok" if not warnings else "warning",
        "runtime_profile": runtime["runtime_profile"],
        "app_build": runtime["app_build"],
        "official_parent_pid": parent,
        "editor_running": parent is not None,
        "packaged_bun": {"path": str(packaged), "exists": packaged.is_file(),
                         "sha256": _sha256(packaged) if packaged.is_file() else None,
                         "same_as_official_bun": same_bun},
        "official_worker_files_present": assets_ready,
        "warnings": warnings,
        "worker": str(WORKER),
        "network_called": False,
        "account_data_read": False,
    }


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        from local_config import configure_environment
    except ImportError:
        pass
    else:
        configure_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-editor", action="store_true", help="动作开始前启动已验证正版剪映；已有匹配宿主时复用")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="只读检查官方运行时、宿主与 Bun 副本，不自动修复")
    default_ws = str(default_workspace("apply"))
    init = sub.add_parser("init", help="初始化 blueprint 工作区")
    init.add_argument("--workspace", default=default_ws)
    init.add_argument("--timeout", type=int, default=180)
    create = sub.add_parser("create", aliases=["project-create"], help="在指定父根创建全新外部草稿，不覆盖已有目录")
    create.add_argument("--draft-root", required=True, help="新工程的父目录（--ref 名称会作为其子目录）")
    create.add_argument("--ref", required=True, help="唯一新引用，例如 local://my-new-draft")
    create.add_argument("--timeout", type=int, default=180)
    resource_import = sub.add_parser("resource-import", help="导入本地媒体到 blueprint 资源表，不检索在线素材")
    resource_import.add_argument("--workspace", default=default_ws)
    resource_import.add_argument("--path", required=True, help="本地视频、音频或图片文件")
    resource_import.add_argument("--title", required=True)
    resource_import.add_argument("--draft-root", help="可选，保持与 create/sync/apply 一致的引用解析父根")
    resource_import.add_argument("--timeout", type=int, default=180)
    sync = sub.add_parser("sync", help="把草稿同步为 canonical XML")
    sync.add_argument("--workspace", default=default_ws)
    sync.add_argument("--ref", required=True, help="草稿引用，例如 local://my-draft")
    sync.add_argument("--draft-root", required=True, help="草稿引用解析的根目录（纯 ASCII）")
    sync.add_argument("--current-only", action="store_true", help="仅刷新 current XML；下一轮编辑前用完整 sync 更新 target 基线")
    sync.add_argument("--timeout", type=int, default=600)
    apply_cmd = sub.add_parser("apply", help="应用 Selection Expression")
    apply_cmd.add_argument("--workspace", default=default_ws)
    apply_cmd.add_argument("--draft-dir", required=True, help="任务自有的已有工程或副本目录，目录名须匹配 local:// 引用")
    apply_cmd.add_argument("--ref", required=True, help="草稿引用，例如 local://my-draft")
    apply_cmd.add_argument("--selection-file", required=True)
    apply_cmd.add_argument("--base-revision", help="可选 canonical XML 修订哈希字符串，不是数字版本号")
    apply_cmd.add_argument("--timeout", type=int, default=900)
    state = sub.add_parser("state", help="读取工作区状态")
    state.add_argument("--workspace", default=default_ws)
    run = sub.add_parser("run", help="运行通用官方 Lyra 命令；用 -- 分隔，读写授权目录须显式提供")
    run.add_argument("--cwd", required=True, help="ASCII 引用解析根目录")
    run.add_argument("--read-write", action="append", default=[], help="授权一个任务自有读写目录，可重复")
    run.add_argument("--read-only", action="append", default=[], help="授权一个只读素材路径，可重复")
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("lyra_args", nargs=argparse.REMAINDER, help="-- 后的官方命令，例如 draft project create --ref local://demo --dir C:\\Temp\\drafts")
    for action_parser in (init, create, resource_import, sync, apply_cmd, run):
        action_parser.add_argument("--start-editor", action="store_true", default=argparse.SUPPRESS,
                                   help="若剪映未运行，先启动已验签安装；已有宿主时复用")
    args = parser.parse_args(argv)
    if args.command not in ("state", "doctor") and args.start_editor:
        ensure_editor_running()
    if args.command == "doctor":
        result = doctor()
    elif args.command == "init":
        result = blueprint_init(args.workspace, args.timeout)
    elif args.command == "sync":
        result = blueprint_sync(args.workspace, args.ref, args.draft_root,
                                args.current_only, args.timeout)
    elif args.command == "apply":
        result = blueprint_apply(args.workspace, args.draft_dir, args.ref,
                                 args.selection_file, args.base_revision, args.timeout)
    elif args.command in ("create", "project-create"):
        result = project_create(args.draft_root, args.ref, args.timeout)
    elif args.command == "resource-import":
        result = blueprint_resource_import(args.workspace, args.path, args.title, args.timeout, args.draft_root)
    elif args.command == "run":
        command_args = args.lyra_args[1:] if args.lyra_args[:1] == ["--"] else args.lyra_args
        require(command_args, "run 需要 -- 后的官方 Lyra 命令")
        result = run_lyra(command_args, args.cwd, args.timeout, args.read_write, args.read_only)
    else:
        result = workspace_state(args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print("DraftEditing 调用失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
