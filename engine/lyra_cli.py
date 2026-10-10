#!/usr/bin/env python3
"""官方 lyra-cli 的薄封装。

``lyra-cli`` 是剪映官方提供给 Agent 的命令行接口，命令域为
``auth`` / ``draft`` / ``material`` / ``media`` / ``lint``（完整清单与实测状态见
``docs/LYRA-CLI-MATRIX.md``）。本模块只做三件事：

1. 构造官方命令参数；
2. 通过 :func:`draftediting_runtime.run_lyra` 在官方 VMSDK 沙箱内执行；
3. 把返回的 envelope 规整成普通字典，并在 ``err_code != 0`` 时抛出可读错误。

编排（何时识别、如何套用动效、何时渲染）留在调用方，便于单元测试。

关于 ``LYRA_CLI_ALLOW_DEV_JIANYING_APP``：本机剪映的 Authenticode 签名不被官方认可
（``signature_not_official``），官方在 ``auth login --require-jianying-app`` 的错误恢复
提示里给出了这个**开发用开关**，用于复用本机已有的剪映登录态。仅在本机开发环境使用。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import draftediting_runtime
import lyra_commands

DEV_APP_ENV = "LYRA_CLI_ALLOW_DEV_JIANYING_APP"
# 默认沿用官方提示的开发开关；置 0 可整体关闭（库级可配置，避免隐式的进程级副作用）。
ALLOW_DEV_APP = os.environ.get(DEV_APP_ENV, "1") not in ("0", "false", "False")
require = draftediting_runtime.require


def run(args, cwd, timeout=600, read_write=(), read_only=(), allow_dev_app=None):
    """执行一条官方命令，返回规整后的 ``result``。

    dev 开关通过 ``extra_env`` 注入子进程，**不再改写宿主进程的 os.environ**。
    """
    if allow_dev_app is None:
        allow_dev_app = ALLOW_DEV_APP
    extra_env = {DEV_APP_ENV: "1"} if allow_dev_app else None
    return _result(draftediting_runtime.run_lyra(list(args), Path(cwd).resolve(strict=True),
                                                 timeout, list(read_write), list(read_only),
                                                 extra_env=extra_env))


def _result(envelope):
    """解包官方 envelope。

    ``err_code`` 必须是 0（与 ``draftediting_runtime`` 上游判定一致）；缺失或非 0 一律
    报错，避免把"命令失败"当成成功。``result`` 字段原样返回，保留 ``[]`` / ``None``
    这类合法空值（旧实现用 ``or {}`` 会把空列表改成空字典，破坏类型契约）。
    """
    body = envelope.get("result") if isinstance(envelope, dict) else None
    require(isinstance(body, dict), "官方命令没有返回结果")
    require(body.get("err_code") == 0,
            f"官方命令失败（err_code={body.get('err_code')}）: {body.get('err_msg')}")
    if "result" not in body:
        return {}
    return body["result"]


# --------------------------------------------------------------------------- auth


def auth_status(cwd, timeout=120):
    """查询当前登录状态。"""
    return run(["auth", "status"], cwd, timeout, [cwd])


def auth_me(cwd, timeout=120):
    """查询当前账号资料。"""
    return run(["auth", "me"], cwd, timeout, [cwd])


def auth_login_link(cwd, timeout=180):
    """发起分步登录，返回授权链接与后续完成参数。

    官方要求：把 ``login_url`` 交给用户打开（或渲染 ``qr_image_markdown``），
    用户授权后再用 ``device_code`` / ``user_code`` / ``session_handoff`` 完成登录。
    """
    body = run(["auth", "login", "--link-url", "--no-wait"], cwd, timeout, [cwd])
    require(body.get("login_url"), "官方未返回授权链接")
    return body


def auth_login_qrcode(cwd, timeout=180):
    """发起扫码登录，返回二维码文件与后续完成参数。"""
    body = run(["auth", "login", "--qr-code", "--no-wait"], cwd, timeout, [cwd])
    require(body.get("qr_token") or body.get("qr_image_file"), "官方未返回二维码信息")
    return body


def auth_login_complete(cwd, device_code, user_code, session_handoff=None,
                        qr_token=None, qr_device_id=None, timeout=300):
    """在用户完成授权后收尾登录（参数取自 :func:`auth_login_link` 的返回）。"""
    args = ["auth", "login"]
    if qr_token:
        args += ["--qr-token", qr_token]
    if qr_device_id:
        args += ["--qr-device-id", qr_device_id]
    args += ["--device-code", device_code, "--user-code", user_code]
    if session_handoff:
        args += ["--session-handoff", session_handoff]
    return run(args, cwd, timeout, [cwd])


# --------------------------------------------------------------------------- lyrics


def lyrics_recognize(draft_root, ref, language="zh", mode=None, seg_id=None,
                     clear_previous=True, subtitle_source=None, workspace=None,
                     timeout=1800):
    """歌词识别（官方 ASR），把结果写入草稿。

    ``mode='segment'`` + ``seg_id`` 只识别单个片段；整稿识别（默认）会**对每个音视频
    来源各识别一遍**，同一段歌词可能被重复写入多份，套用动效前需注意。
    """
    args = ["draft", "lyrics", "recognize", "--ref", ref, "--language", language]
    if mode:
        args += ["--mode", mode]
    if seg_id:
        args += ["--seg-id", seg_id]
    args += ["--clear-previous", "true" if clear_previous else "false"]
    if subtitle_source is not None:
        args += ["--subtitle-source", str(subtitle_source)]
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(args, draft_root, timeout, paths)


def lyrics_recognized_sentences(result):
    """从识别结果里取出句级歌词文本（按出现顺序、去重）。"""
    lines = []
    for segment in (result or {}).get("affected_segments", []):
        for sentence in ((segment.get("asr") or {}).get("sentences") or []):
            text = (sentence.get("text") or "").strip()
            if text and text not in lines:
                lines.append(text)
    return lines


def _microseconds(value, default=0):
    """把官方返回的微秒值安全转成 int（可能是 int / 浮点 / 数字字符串）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def recognized_cues(result):
    """把官方识别结果规整成句级 cues（微秒 → 毫秒）。

    整稿识别会**对每个音视频来源各识别一遍**，同一句歌词可能重复出现多次；这里按文本
    去重并保留首次出现的时间，再按开始时间排序（实测本工程 100 条原始句 → 10 句）。
    """
    cues, seen = [], set()
    for segment in (result or {}).get("affected_segments", []):
        for sentence in ((segment.get("asr") or {}).get("sentences") or []):
            text = (sentence.get("text") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            start = _microseconds(sentence.get("start_us")) // 1000
            duration = max(_microseconds(sentence.get("duration_us")) // 1000, 1)
            cues.append({"id": f"lyric_{len(cues) + 1:02d}", "text": text,
                         "start_ms": start, "end_ms": start + duration})
    return sorted(cues, key=lambda cue: cue["start_ms"])


def lyrics_animation_add(draft_root, ref, resource, language="zh-CN", cover_old=False,
                         workspace=None, timeout=900):
    """把歌词动效资源应用到草稿里的歌词。

    ``resource`` 形如 ``vimo://7591420714515844395``（官方歌词动效资源 id）。
    实测：草稿里存在多组识别结果时会报
    ``multiple lyrics recognize tasks found``，此时应改用
    :func:`lyrics_animation_update` 逐段应用。
    """
    args = ["draft", "lyrics", "animation", "add", "--ref", ref, "--resource", resource]
    if language:
        args += ["--language", language]
    if cover_old:
        args += ["--cover-old"]
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(args, draft_root, timeout, paths)


def lyrics_animation_update(draft_root, ref, seg_id, resource, language="zh-CN",
                            workspace=None, timeout=600):
    """对单个歌词段套用/替换动效资源。

    实测两点：目标必须是**普通文本段**（``segment_text``），已经套过动效的
    ``segment_text_template`` 会被拒绝；套用后该段会被**重建并展开为逐词多段**，
    因此原 ``seg_id`` 失效，批量处理必须每轮重新同步取 id。
    """
    args = ["draft", "lyrics", "animation", "update", "--ref", ref,
            "--seg-id", seg_id, "--resource", resource]
    if language:
        args += ["--language", language]
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(args, draft_root, timeout, paths)


def lyrics_animation_remove(draft_root, ref, seg_id, workspace=None, timeout=600):
    """移除某个歌词段上的动效资源。"""
    args = ["draft", "lyrics", "animation", "remove", "--ref", ref, "--seg-id", seg_id]
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(args, draft_root, timeout, paths)


# ------------------------------------------------------- 段落解析（纯函数，便于测试）

import xml.etree.ElementTree as _ET  # noqa: E402  （放在此处以保持文件上部导入简洁）

_SEGMENT_TAGS = ("text", "subtitle")


def _attribute(element, name):
    """取属性值；支持 ``name`` 与 ``name-x`` 两种写法（官方 XML 混用）。"""
    if name in element.attrib:
        return element.attrib[name]
    dashed = name.replace("_", "-")
    if dashed in element.attrib:
        return element.attrib[dashed]
    return None


def parse_segment_rows(xml_text, tags=_SEGMENT_TAGS):
    """解析 ``(xml_id, 文本, 是否已带动效模板)``。

    用真正的 XML 解析而不是逐行正则：canonical XML 里段属性可能换行、``</text>`` 可能与
    内容同行、``<template_package>`` 这类段外节点也以 ``<template`` 开头，逐行匹配会漏判
    或误判（进而漏套动效或把模板节点算成已套用）。``has_template`` 只认**段内**的
    ``template`` 子元素。

    ``tags`` 用于限定段类型：``<subtitle>`` 与 ``<text>`` 的 id 外形相同（都用 ``tN``），
    只能靠标签名区分，而官方 ``lyrics animation update`` 只接受普通文本段。
    """
    try:
        root = _ET.fromstring(f"<_root>{xml_text}</_root>")
    except _ET.ParseError:
        return []
    rows = []
    for element in root.iter():
        if element.tag not in tags:
            continue
        xml_id = element.get("id")
        if not xml_id:
            continue
        body = ""
        for sub in element.iter("sub"):
            text = sub.get("text")
            if text:
                body = text
                break
        has_template = any(child.tag == "template" for child in element.iter()
                           if child is not element)
        rows.append((xml_id, body, has_template))
    return rows


def pending_lyric_segments(xml_text, id_map, lyrics):
    """挑出**尚未套用动效**、且文本正好是一句识别歌词的 ``<text>`` 段。

    两个约束：按整句匹配（套用动效会把整句展开成逐词多段，那些词段文本不等于任何整句，
    因此不会被再次处理）；只认 ``<text>``，因为官方 ``lyrics animation update`` 只接受
    普通文本段（``segment_text``），``<subtitle>`` 送进去必然失败。
    """
    wanted = {line.strip() for line in (lyrics or []) if line and line.strip()}
    pending = []
    for xml_id, body, has_template in parse_segment_rows(xml_text, tags=("text",)):
        if has_template:
            continue
        if body.strip() not in wanted:
            continue
        seg_id = (id_map or {}).get(xml_id)
        if seg_id:
            pending.append((xml_id, seg_id, body.strip()))
    return pending


def load_workspace_views(workspace):
    """读取工作区的 canonical XML 与公开 id 映射。"""
    workspace = Path(workspace)
    xml_text = (workspace / "current_draft.xml").read_text(encoding="utf-8", errors="replace")
    mapping = {}
    id_map_path = workspace / "id_map.json"
    if id_map_path.is_file():
        for item in json.loads(id_map_path.read_text(encoding="utf-8")):
            mapping[item.get("xml_id")] = item.get("seg_id")
    return xml_text, mapping


# ----------------------------------------------------------------- 通用转发

def _options(pairs):
    """把 ``{"--flag": value}`` 展开成命令行参数；值为 None 时跳过。"""
    args = []
    for flag, value in (pairs or {}).items():
        if value is None or value is False:
            continue
        args.append(flag)
        if value is not True:
            args.append(str(value))
    return args


def draft(action, draft_root, ref=None, options=None, workspace=None, timeout=600):
    """转发任意 ``draft`` 命令。

    ``action`` 形如 ``["video", "add"]``、``["template", "render"]``；``options`` 是
    ``{"--flag": value}`` 形式的附加参数（``True`` 表示只加开关，``None`` 跳过）。
    这条通道覆盖全部 draft 子命令，避免为每个命令硬编码参数；已确认参数的高频命令
    另见下面的 typed 封装。
    """
    args = ["draft"] + list(action)
    if ref:
        args += ["--ref", ref]
    args += _options(options)
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(args, draft_root, timeout, paths)


# ------------------------------------------------- 高频域 typed 封装（参数经 --help 核对）

def subtitle_add(draft_root, ref, content, track=None, start=None, duration=None,
                 wrap_width=None, workspace=None, timeout=300):
    """添加一条字幕（官方 ``draft subtitle add``）。"""
    return draft(["subtitle", "add"], draft_root, ref,
                 {"--content": content, "--track": track, "--start": start,
                  "--duration": duration, "--wrap-width": wrap_width},
                 workspace=workspace, timeout=timeout)


def audio_add(draft_root, ref, resource, kind=None, track=None, start=None, duration=None,
              source_from=None, workspace=None, timeout=300):
    """添加一条音频（官方 ``draft audio add``）。"""
    return draft(["audio", "add"], draft_root, ref,
                 {"--resource": resource, "--kind": kind, "--track": track,
                  "--start": start, "--duration": duration, "--source-from": source_from},
                 workspace=workspace, timeout=timeout)


def algo_tts(draft_root, ref, text, speaker=None, speed=None, write_to_draft=False,
             copy_to_draft=False, output_dir=None, audio_format=None, start_time=None,
             duration=None, replace=False, resource_id=None, workspace=None, timeout=900):
    """官方 TTS（``draft algo tts``）。

    ``write_to_draft`` / ``copy_to_draft`` 决定生成结果是否落地到草稿；
    只取音频文件时两者都不传，并用 ``output_dir`` 指定目录。
    """
    return draft(["algo", "tts"], draft_root, ref,
                 {"--text": text, "--speaker": speaker, "--speed": speed,
                  "--write-to-draft": True if write_to_draft else None,
                  "--copy-to-draft": True if copy_to_draft else None,
                  "--output-dir": output_dir, "--audio-format": audio_format,
                  "--start-time": start_time, "--duration": duration,
                  "--replace": True if replace else None, "--resource-id": resource_id},
                 workspace=workspace, timeout=timeout)


def algo_sound_separation(draft_root, ref, seg_id=None, mode=None, keep=None, sounds=None,
                          apply_result=False, output_dir=None, audio_format=None,
                          workspace=None, timeout=1800):
    """人声分离（``draft algo sound-separation``）。"""
    return draft(["algo", "sound-separation"], draft_root, ref,
                 {"--seg-id": seg_id, "--mode": mode, "--keep": keep, "--sounds": sounds,
                  "--apply": True if apply_result else None, "--output-dir": output_dir,
                  "--format": audio_format},
                 workspace=workspace, timeout=timeout)


def algo_upscale_resolution(draft_root, ref, seg_id=None, mode=None, from_path=None,
                            input_path=None, output_path=None, wait=False,
                            skip_re_run=False, workspace=None, timeout=3600):
    """超分（``draft algo upscale-resolution``）。"""
    return draft(["algo", "upscale-resolution"], draft_root, ref,
                 {"--seg-id": seg_id, "--mode": mode, "--from": from_path,
                  "--input-path": input_path, "--output-path": output_path,
                  "--wait": True if wait else None,
                  "--skip-re-run": True if skip_re_run else None},
                 workspace=workspace, timeout=timeout)


def template_render(cwd, config, ref, output, dir_path=None, timeout=1800):
    """官方渲染命令（``draft template render``）。

    注意它要求 ``--ref`` 指向**尚不存在**的新工作区，即"从配置生成草稿再渲染"，
    不能用于渲染任意已有草稿——后者由本项目自编译的原生辅助程序完成。
    """
    return run(["draft", "template", "render", "--config", config, "--ref", ref,
                "--output", output] + (["--dir", dir_path] if dir_path else []),
               cwd, timeout, [cwd])


def material_search(cwd, kind, prompt=None, limit=None, need_recommend=None, timeout=300):
    """官方素材检索（``material search``）。"""
    return run(["material", "search", "--type", kind] + _options(
        {"--prompt": prompt, "--limit": limit, "--need-recommend": need_recommend}),
        cwd, timeout, [cwd])


def material_download(cwd, resource_id, output_dir, timeout=900):
    """官方素材下载（``material download``）。"""
    return run(["material", "download", "--resource-id", resource_id,
                "--output-dir", output_dir], cwd, timeout, [cwd, output_dir])


def media_asr(cwd, input_path, language=None, output=None, clear_talking_head=False,
              timeout=1800):
    """本地音频转写（``media asr``），不写草稿。"""
    return run(["media", "asr", "--input", input_path] + _options(
        {"--language": language, "--output": output,
         "--clear-talking-head": True if clear_talking_head else None}),
        cwd, timeout, [cwd])


def lint_draft(draft_root, ref, input_path=None, suite=None, output=None, fail_on=None,
               workspace=None, timeout=600):
    """官方草稿验收（``lint draft``，属于顶层 lint 域）。"""
    paths = [Path(draft_root)] + ([Path(workspace)] if workspace else [])
    return run(["lint", "draft", "--ref", ref] + _options(
        {"--input": input_path, "--suite": suite, "--output": output, "--fail-on": fail_on}),
        draft_root, timeout, paths)


def lint_command(cwd, input_path=None, suite=None, output=None, fail_on=None, timeout=300):
    """官方命令契约验收（``lint command``）。"""
    return run(["lint", "command"] + _options(
        {"--input": input_path, "--suite": suite, "--output": output, "--fail-on": fail_on}),
        cwd, timeout, [cwd])


# ------------------------------------------------- 全部命令的 typed 封装（清单驱动）
# engine/lyra_commands.json 由 tools/enumerate_all_commands.py 逐条调用官方
# ``<path> --help`` 生成；install() 会把清单里的每条命令装成同名函数，例如
# video_speed / video_crop / algo_tts / media_asr / material_search。
# 上面手写的核心封装优先，清单版本不会覆盖它们：被顶掉的名字记入
# COMMAND_MANUAL_OVERRIDES，COMMAND_INDEX 只登记真正安装的清单版函数。
# tests/test_lyra_command_index.py 断言这层对应关系不漂移。


def _manifest_runner(path, cwd, timeout=600, ref=None, options=None, workspace=None):
    """清单生成函数的执行通道：参数已由 lyra_commands 校验过 flag 名。"""
    args = list(path)
    if ref:
        args += ["--ref", ref]
    args += _options(options)
    paths = [Path(cwd)] + ([Path(workspace)] if workspace else [])
    return run(args, cwd, timeout, paths)


COMMAND_COUNT, COMMAND_INDEX = lyra_commands.install(sys.modules[__name__],
                                                      _manifest_runner)
