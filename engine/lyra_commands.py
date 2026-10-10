#!/usr/bin/env python3
"""由官方 `--help` 清单驱动的命令封装。

``engine/lyra_commands.json`` 由 ``tools/enumerate_all_commands.py`` 逐条调用官方
``<path> --help`` 生成（不靠文档推测），本模块把它变成可调用的 typed 函数：

    import lyra_commands
    lyra_commands.video_speed(draft_root, ref, seg_id="v1", speed=2.0)
    lyra_commands.algo_tts(draft_root, ref, text="你好", speaker="BV700_streaming")

每个 kwargs 会转成 ``--flag value``，并**校验该 flag 确实出现在官方参数表里**，
所以参数名拼错会立刻报错，而不是被静默传给 CLI。
"""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("lyra_commands.json")
_DRAFT_ONLY = "draft"
# 官方全局开关：把它们当作可选业务参数会改变命令行为（例如 --help 会让命令挂住），
# 因此从白名单里剔除，也不允许经 kwargs / options 传入。
_GLOBAL_FLAGS = {"--help", "--version", "--jq"}


def load_manifest(path=None):
    """读取能力清单；缺失时返回空结构（便于在未枚举的机器上导入本模块）。"""
    manifest_path = Path(path or MANIFEST)
    if not manifest_path.is_file():
        return {"generated_from": None, "count": 0, "commands": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def function_name(path):
    """把命令路径转成函数名：``["draft","video","speed"]`` → ``video_speed``。"""
    parts = list(path)
    if parts and parts[0] == _DRAFT_ONLY and len(parts) > 1:
        parts = parts[1:]
    return "_".join(part.replace("-", "_") for part in parts)


def _flag(name):
    """kwarg 名 → 命令行 flag。

    支持尾部下划线写法（``from_`` → ``--from``、``in_`` → ``--in``），因为 Python
    关键字/内建名无法直接作为参数名。
    """
    cleaned = name[:-1] if name.endswith("_") and not name.endswith("__") else name
    return "--" + cleaned.replace("_", "-")


def _check(flag, allowed, dotted):
    if allowed and flag in _GLOBAL_FLAGS:
        raise ValueError(f"{dotted} 不接受全局开关 {flag}")
    if allowed and flag not in allowed:
        raise ValueError(f"{dotted} 不支持 {flag}；可用参数: {', '.join(allowed)}")


def build_caller(spec, runner):
    """为一个命令规格生成调用函数。

    ``runner(path, cwd, timeout, ref, options, workspace)`` 由调用方提供（真正执行命令的
    通道），这样本模块不直接依赖沙箱细节，便于测试。kwargs 与 ``options`` 都会被校验。
    """
    path = list(spec["path"])
    allowed = [flag for flag in (spec.get("options") or []) if flag not in _GLOBAL_FLAGS]
    dotted = " ".join(path)
    summary = spec.get("summary") or ""

    def call(cwd, timeout=600, ref=None, options=None, workspace=None, **kwargs):
        pairs = {}
        for key, value in kwargs.items():
            if value is None or value is False:
                continue
            flag = _flag(key)
            _check(flag, allowed, dotted)
            pairs[flag] = value
        for key, value in (options or {}).items():
            if value is None or value is False:
                continue
            flag = key if str(key).startswith("--") else _flag(str(key))
            _check(flag, allowed, dotted)
            if flag in pairs:
                raise ValueError(f"{dotted} 的 {flag} 被重复指定")
            pairs[flag] = value
        if ref and "--ref" in pairs:
            raise ValueError(f"{dotted} 的 --ref 被重复指定（ref= 与 options 冲突）")
        return runner(path, cwd, timeout=timeout, ref=ref, options=pairs, workspace=workspace)

    call.__name__ = function_name(path)
    call.__doc__ = (f"官方命令 ``lyra-cli {dotted}``。\n\n{summary}\n\n"
                    f"可用参数: {', '.join(allowed) if allowed else '（未取到参数表，按官方原样透传）'}")
    call.command_path = path
    call.allowed_options = allowed
    return call


def install(namespace, runner, manifest=None):
    """把全部命令装成 ``namespace`` 上的函数，返回安装数量与索引。

    同名的手写封装（如 ``algo_tts`` / ``material_search``）会被保留，记入
    ``COMMAND_MANUAL_OVERRIDES``；``COMMAND_INDEX`` **只登记真正安装的**名字，
    保证索引里每个名字都能用清单版签名 ``(cwd, timeout, ref, options, workspace)`` 调用。
    """
    data = manifest if manifest is not None else load_manifest()
    installed, index, overrides = 0, {}, []
    for spec in data.get("commands", []):
        name = function_name(spec["path"])
        if hasattr(namespace, name):
            overrides.append(name)
            continue
        setattr(namespace, name, build_caller(spec, runner))
        index[name] = list(spec["path"])
        installed += 1
    namespace.COMMAND_INDEX = index
    namespace.COMMAND_MANIFEST = data
    namespace.COMMAND_MANUAL_OVERRIDES = sorted(overrides)
    namespace.COMMAND_SKIPPED = sorted(overrides)  # 兼容旧名
    return installed, index
