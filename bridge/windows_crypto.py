#!/usr/bin/env python3
"""Windows 剪映草稿加解密桥接。

仅调用用户本机 ``videoeditor.dll`` 的公开导出符号，不分发官方二进制。
默认由父进程以隔离子进程方式调用，避免 ABI 不匹配导致主进程崩溃。
"""
from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import sys

DECRYPT_SYMBOL = (
    "?decrypt@EncryptUtils@lvve@@QEAA?AV?$basic_string@DU?$char_traits@D@std@@"
    "V?$allocator@D@2@@std@@AEBV34@0AEA_N@Z"
)
ENCRYPT_SYMBOL = (
    "?encrypt@EncryptUtils@lvve@@QEAA?AV?$basic_string@DU?$char_traits@D@std@@"
    "V?$allocator@D@2@@std@@AEBV34@@Z"
)
ENABLE_SYMBOL = "?enable@EncryptUtils@lvve@@QEAAX_N@Z"
WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class CryptoError(RuntimeError):
    pass


class _StringData(ctypes.Union):
    _fields_ = [("small", ctypes.c_char * 16), ("pointer", ctypes.c_void_p)]


class MsvcString(ctypes.Structure):
    _fields_ = [("data", _StringData), ("size", ctypes.c_uint64), ("capacity", ctypes.c_uint64)]


class MsvcStringArg:
    def __init__(self, payload: bytes):
        self.buffer = None
        self.value = MsvcString()
        self.value.size = len(payload)
        if len(payload) < 16:
            self.value.capacity = 15
            ctypes.memset(ctypes.addressof(self.value.data), 0, 16)
            if payload:
                ctypes.memmove(ctypes.addressof(self.value.data), payload, len(payload))
        else:
            self.buffer = ctypes.create_string_buffer(payload)
            self.value.capacity = len(payload)
            self.value.data.pointer = ctypes.cast(self.buffer, ctypes.c_void_p).value


def _bytes(value: MsvcString) -> bytes:
    size = int(value.size)
    if size > 512 * 1024 * 1024:
        raise CryptoError("剪映 DLL 返回了异常长度")
    address = ctypes.addressof(value.data) if value.capacity < 16 else value.data.pointer
    if size and not address:
        raise CryptoError("剪映 DLL 返回了空指针")
    return ctypes.string_at(address, size)


class WindowsDraftCrypto:
    def __init__(self, install_dir: Path):
        if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise CryptoError("需要 64 位 Windows Python")
        self.install_dir = Path(install_dir).resolve(strict=True)
        dll_path = self.install_dir / "videoeditor.dll"
        if not dll_path.is_file():
            raise CryptoError("安装目录中缺少 videoeditor.dll")
        self.cookie = os.add_dll_directory(str(self.install_dir)) if hasattr(os, "add_dll_directory") else None
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.install_dir) + os.pathsep + old_path
        try:
            self.dll = ctypes.WinDLL(str(dll_path), winmode=0x100 | 0x400 | 0x800, use_last_error=True)
        finally:
            os.environ["PATH"] = old_path
        self.decrypt_fn = self._bind(DECRYPT_SYMBOL, WINFUNCTYPE(
            ctypes.POINTER(MsvcString), ctypes.c_void_p, ctypes.POINTER(MsvcString),
            ctypes.POINTER(MsvcString), ctypes.POINTER(MsvcString), ctypes.POINTER(ctypes.c_bool)))
        self.encrypt_fn = self._bind(ENCRYPT_SYMBOL, WINFUNCTYPE(
            ctypes.POINTER(MsvcString), ctypes.c_void_p, ctypes.POINTER(MsvcString), ctypes.POINTER(MsvcString)))
        self.enable_fn = self._bind(ENABLE_SYMBOL, WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool))

    def _bind(self, symbol, prototype):
        try:
            address = ctypes.cast(self.dll[symbol], ctypes.c_void_p).value
        except AttributeError as error:
            raise CryptoError("当前 videoeditor.dll 缺少所需导出符号") from error
        return prototype(address)

    def decrypt(self, payload: bytes) -> bytes:
        source, parameters = MsvcStringArg(payload), MsvcStringArg(b"{}")
        output, ok = MsvcString(), ctypes.c_bool(False)
        self.decrypt_fn(None, ctypes.byref(output), ctypes.byref(source.value),
                        ctypes.byref(parameters.value), ctypes.byref(ok))
        result = _bytes(output)
        if not ok.value or not result:
            raise CryptoError("草稿解密失败")
        return result

    def encrypt(self, payload: bytes) -> bytes:
        self.enable_fn(None, True)
        source, output = MsvcStringArg(payload), MsvcString()
        self.encrypt_fn(None, ctypes.byref(output), ctypes.byref(source.value))
        result = _bytes(output)
        if not result or self.decrypt(result) != payload:
            raise CryptoError("草稿加密回环校验失败")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("decrypt", "encrypt"))
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    source = args.input.read_bytes()
    crypto = WindowsDraftCrypto(args.install_dir)
    result = crypto.decrypt(source) if args.mode == "decrypt" else crypto.encrypt(source)
    args.output.write_bytes(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, CryptoError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
