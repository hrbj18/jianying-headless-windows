"""Windows 剪映 11.5 本地运行时适配。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from types import SimpleNamespace
import msvcrt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRIDGE = PROJECT_ROOT / "bridge"
DRAFT_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "JianyingPro/User Data/Projects/com.lveditor.draft"
TIMELINE_FILE = "draft_content.json"
PROFILE_PREFIX = "jy14-headless-windows-"
WINDOWS_PROFILES = {
    "11.5.0.14471": "37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb",
}
PUBLISHER = "深圳市脸萌科技有限公司"


class ApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    content: bytes
    sha256: str
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    parent_mtime_ns: int


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _install_candidates():
    explicit = os.environ.get("JIANYING_INSTALL_DIR")
    if explicit:
        yield Path(explicit)
        return
    apps = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "JianyingPro/Apps"
    if not apps.is_dir():
        return
    folders = [p for p in apps.iterdir() if p.is_dir() and (p / "videoeditor.dll").is_file()]
    yield from sorted(folders, key=lambda p: tuple(int(x) for x in p.name.split(".") if x.isdigit()), reverse=True)


def discover_installation():
    for folder in _install_candidates():
        folder = folder.resolve()
        dll, executable = folder / "videoeditor.dll", folder / "JianyingPro.exe"
        if dll.is_file() and executable.is_file() and folder.name in WINDOWS_PROFILES:
            actual = digest(dll)
            if actual == WINDOWS_PROFILES[folder.name]:
                return folder, folder.name, actual
    raise ValueError("未找到已审核的 Windows 剪映 11.5.0.14471；可用 JIANYING_INSTALL_DIR 指定版本目录")


def doctor():
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise ValueError("Windows 运行时需要 64 位 Windows 和 64 位 Python")
    install, build, fingerprint = discover_installation()
    if not DRAFT_ROOT.is_dir() or not (DRAFT_ROOT / "root_meta_info.json").is_file():
        raise ValueError("剪映默认本地草稿目录尚未初始化")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError(tool + " 未安装或不在 PATH 中")
    return {"status": "ok", "platform": "windows", "architecture": "x64",
            "app_version": "11.5.0", "app_build": build,
            "install_dir": str(install), "draft_root": str(DRAFT_ROOT),
            "libvideoeditor_sha256": fingerprint,
            "runtime_profile": PROFILE_PREFIX + build,
            "runtime_hashes_verified": True, "network_called": False,
            "full_signature_check": "required before live creation"}


def validate_runtime():
    before = doctor()
    install = Path(before["install_dir"])
    env = {"PATH": os.environ.get("SystemRoot", r"C:\Windows") + r"\System32",
           "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
           "JY_EXE": str(install / "JianyingPro.exe")}
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
               "$s=Get-AuthenticodeSignature -LiteralPath $env:JY_EXE; "
               "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
               "Write-Output ($s.Status.ToString()+'|'+$s.SignerCertificate.Subject)"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=30, env=env)
    if result.returncode or not result.stdout.startswith("Valid|") or PUBLISHER not in result.stdout:
        raise ValueError("Windows 剪映 Authenticode 签名或发布者验证失败")
    if doctor() != before:
        raise ValueError("验证签名期间 Windows 剪映运行时发生变化")
    return dict(before, full_signature_check="passed", publisher=PUBLISHER)


def _powershell(script, values=None, timeout=60):
    env = dict(os.environ)
    env.update(values or {})
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, env=env)
    if result.returncode:
        raise ApplyError("PowerShell 安全描述符操作失败: " + (result.stderr or "").strip()[:400])
    return result.stdout.strip()


def read_xattrs(path):
    """Windows 上以 DACL 作为受保护属性的等价物（不读取需要提升权限的 SACL）。"""
    sddl = _powershell('[Console]::OutputEncoding=[Text.Encoding]::UTF8; '
                       '[System.IO.File]::GetAccessControl($env:JY_PATH).'
                       'GetSecurityDescriptorSddlForm("Access")',
                       {"JY_PATH": str(Path(path).resolve())})
    if not sddl or not sddl.startswith("D:"):
        raise ApplyError("无法读取文件的 DACL")
    return {"windows.dacl": sddl.encode("utf-8")}


def copy_xattrs(source_attrs, destination, audit, source=None):
    """把源文件的安全描述符复制到新文件，并在提交前逐字节校验。

    DACL 必须整对象复制：只按 SDDL 字符串重建会丢失“是否受保护/是否继承”的
    状态位，Windows 会把显式 ACL 重新标记为继承而来。因此这里既校验源文件在
    快照之后没有变化，又要求调用方提供源路径。
    """
    (Path(audit) / "index-attributes-before.json").write_text(
        json.dumps({key: value.hex() for key, value in source_attrs.items()},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not source_attrs.get("windows.dacl") or source is None or not Path(source).is_file():
        raise ApplyError("缺少源文件或其 DACL，拒绝提交索引替换")
    if read_xattrs(source) != source_attrs:
        raise ApplyError("源文件安全属性在快照之后发生变化，拒绝提交索引替换")
    _powershell('$acl = [System.IO.File]::GetAccessControl($env:JY_SRC); '
                '[System.IO.File]::SetAccessControl($env:JY_PATH, $acl)',
                {"JY_SRC": str(Path(source).resolve()), "JY_PATH": str(Path(destination).resolve())})
    copied = read_xattrs(destination)
    (Path(audit) / "index-attributes-staged.json").write_text(
        json.dumps({key: value.hex() for key, value in copied.items()},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = sorted(key for key in set(source_attrs) | set(copied)
                     if source_attrs.get(key) != copied.get(key))
    if changed:
        raise ApplyError("提交前无法保留文件 DACL: " + ", ".join(changed)
                         + "。未剥离任何安全属性；当前环境需要人工确认权限保留策略。")
    return copied, []


def fresh_directory(path):
    path = Path(path).resolve()
    if path == DRAFT_ROOT or DRAFT_ROOT in path.parents:
        raise ValueError("构建和审计目录不能位于实时草稿目录中")
    path.mkdir(parents=True, exist_ok=False)
    return path


def packed(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _parse_strict_json(payload, label):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ApplyError(label + " 包含重复键")
            result[key] = value
        return result
    def reject(_):
        raise ApplyError(label + " 包含非有限数值")
    try:
        value = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=reject)
        json.dumps(value, allow_nan=False)
    except ApplyError:
        raise
    except (UnicodeError, ValueError, TypeError) as error:
        raise ApplyError(label + " 不是严格 UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ApplyError(label + " 顶层必须是对象")
    return value


def _snapshot_file(path, label, max_bytes=256 * 1024 * 1024):
    path = Path(path).resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise ApplyError(label + " 必须是普通文件")
    before, parent = path.stat(), path.parent.stat()
    if max_bytes is not None and before.st_size > max_bytes:
        raise ApplyError(label + " 超过安全大小限制")
    content = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ApplyError(label + " 在读取期间发生变化")
    return FileSnapshot(path, content, hashlib.sha256(content).hexdigest(), stat.S_IMODE(after.st_mode),
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns, parent.st_mtime_ns)


def _revalidate_snapshot(snapshot, phase):
    current = _snapshot_file(snapshot.path, phase)
    if (current.sha256, current.size, current.mtime_ns, current.ctime_ns) != (
            snapshot.sha256, snapshot.size, snapshot.mtime_ns, snapshot.ctime_ns):
        raise ApplyError(phase + " 在事务快照后发生变化")


def _crypto(mode, payload):
    runtime = doctor()
    with tempfile.TemporaryDirectory(prefix="jianying-crypto-") as folder:
        source, output = Path(folder) / "input.bin", Path(folder) / "output.bin"
        source.write_bytes(payload)
        command = [sys.executable, str(BRIDGE / "windows_crypto.py"), mode,
                   "--install-dir", runtime["install_dir"], str(source), str(output)]
        result = subprocess.run(command, capture_output=True, timeout=120)
        if result.returncode or not output.is_file():
            raise ApplyError("Windows 草稿" + ("解密" if mode == "decrypt" else "加密") + "失败")
        return output.read_bytes()


def _decrypt_metadata_in_memory(path):
    return _parse_strict_json(_crypto("decrypt", Path(path).read_bytes()), "解密后的草稿元数据")


def _encrypt_metadata_from_memory(payload, path):
    path = Path(path)
    if path.exists():
        raise ApplyError("拒绝覆盖已有加密输出")
    path.write_bytes(_crypto("encrypt", payload))


def _ensure_editor_closed(confirm_editor_closed):
    if confirm_editor_closed is not True:
        raise ApplyError("需要明确确认剪映已关闭")
    result = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq JianyingPro.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ApplyError("无法确认剪映是否已关闭")
    if "JianyingPro.exe" in result.stdout:
        raise ApplyError("剪映主进程仍在运行")
    return {"confirmed_by_user": True, "main_process_closed": True}


def _acquire_directory_transaction_lock(directory, label):
    lock_path = Path(directory) / ".jianying-headless.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    except OSError as error:
        os.close(descriptor)
        raise ApplyError("另一个事务正在占用" + label) from error
    return descriptor, str(lock_path)


def _release_directory_transaction_lock(descriptor):
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(descriptor)


def helper():
    return SimpleNamespace(_decrypt_metadata_in_memory=_decrypt_metadata_in_memory,
        _encrypt_metadata_from_memory=_encrypt_metadata_from_memory,
        _ensure_editor_closed=_ensure_editor_closed, _snapshot_file=_snapshot_file,
        _parse_strict_json=_parse_strict_json, _revalidate_snapshot=_revalidate_snapshot,
        _acquire_directory_transaction_lock=_acquire_directory_transaction_lock,
        _release_directory_transaction_lock=_release_directory_transaction_lock,
        _read_attributes=read_xattrs, _copy_attributes=copy_xattrs,
        _validate_runtime_environment=validate_runtime)
