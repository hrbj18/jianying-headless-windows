#!/usr/bin/env python3
"""为剪映官方 DraftEditing 生成并调用受支持的功能请求。

本模块不模拟官方资源服务。音色、歌词动画和模板包都必须使用剪映
MaterialRecall 返回的 blueprint_ref，或当前草稿中已经存在的真实 ref。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

# 兼容 `python engine/official_features.py` 与按文件加载模块两种入口。
ENGINE_DIR = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import windows_runtime


PLAN_SCHEMA = "jianying-official-features/v1"
REQUEST_SCHEMA = "jianying-draft-editing-request/v1"
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
REF_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
DRAFT_REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
AGENT_COMMANDS = {"fetch-feishu-doc", "query-content", "plan-patch", "validate-patch", "apply-patch"}


def require(value, message):
    if not value:
        raise ValueError(message)


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON 存在重复字段: " + key)
            result[key] = value
        return result

    value = json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                       parse_constant=lambda item: (_ for _ in ()).throw(
                           ValueError("JSON 不允许非有限数值: " + item)))
    require(isinstance(value, dict), "JSON 根节点必须是对象")
    return value


def only_keys(value, allowed, label):
    require(isinstance(value, dict), label + " 必须是对象")
    extra = sorted(set(value) - set(allowed))
    require(not extra, label + " 存在不支持的字段: " + ", ".join(extra))


def text(value, label):
    require(isinstance(value, str) and value.strip() == value and value, label + " 必须是非空文本")
    return value


def identifier(value, label):
    value = text(value, label)
    require(ID_PATTERN.fullmatch(value), label + " 必须匹配 [A-Za-z][A-Za-z0-9_-]*")
    return value


def resource_ref(value, label):
    value = text(value, label)
    require(REF_PATTERN.fullmatch(value), label + " 必须是已绑定的 blueprint_ref，不能填写路径、URL 或 resource_id")
    return value


def integer(value, label, minimum=0, maximum=86_400_000):
    require(type(value) is int and minimum <= value <= maximum,
            f"{label} 必须是 {minimum}..{maximum} 的整数毫秒")
    return value


def number(value, label, minimum, maximum):
    require(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum,
            f"{label} 必须在 {minimum}..{maximum} 范围内")
    return value


def color(value, label):
    value = text(value, label)
    require(re.fullmatch(r"#[0-9A-Fa-f]{6}", value), label + " 必须使用 #RRGGBB")
    return value.upper()


def attrs(values):
    return " ".join(f'{key}="{xml_escape(str(value))}"' for key, value in values.items())


def xml_escape(value):
    return (value.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def tts_node(spec, refs):
    allowed = {"id", "text", "tone_ref", "start_ms", "duration_ms", "display", "size", "color"}
    only_keys(spec, allowed, "TTS 项")
    node_id = identifier(spec.get("id"), "TTS id")
    content = text(spec.get("text"), "TTS text")
    tone = resource_ref(spec.get("tone_ref"), "TTS tone_ref")
    display = spec.get("display", False)
    require(type(display) is bool, "TTS display 必须是布尔值")
    refs.append({"ref": tone, "asset_type": "tone", "used_by": node_id})
    children = []
    if display:
        start = integer(spec.get("start_ms", 0), "TTS start_ms")
        duration = integer(spec.get("duration_ms", 1000), "TTS duration_ms", 1)
        size = number(spec.get("size", 10), "TTS size", 1, 100)
        tint = color(spec.get("color", "#FFFFFF"), "TTS color")
        children.extend([
            f'<time start="{start}" duration="{duration}"></time>',
            '<transform justify-self="center" align-self="end" padding-bottom="16%" rotation="0"></transform>',
            f'<content><sub text="{xml_escape(content)}" size="{size}" color="{tint}"></sub></content>',
        ])
    else:
        require("start_ms" not in spec and "duration_ms" not in spec and "size" not in spec and "color" not in spec,
                "仅配音 TTS 不接受展示时间或样式字段；需要画面文字时设置 display=true")
        children.append(f'<content><sub text="{xml_escape(content)}"></sub></content>')
    children.append(f'<speech ref="{tone}"></speech>')
    return f'<text id="{node_id}">' + "".join(children) + "</text>"


def lyric_node(spec, refs):
    allowed = {"id", "text", "start_ms", "end_ms", "animation_ref", "animation_duration_ms", "size", "color"}
    only_keys(spec, allowed, "歌词项")
    node_id = identifier(spec.get("id"), "歌词 id")
    content = text(spec.get("text"), "歌词 text")
    start = integer(spec.get("start_ms"), "歌词 start_ms")
    end = integer(spec.get("end_ms"), "歌词 end_ms", 1)
    require(end > start, "歌词 end_ms 必须大于 start_ms")
    size = number(spec.get("size", 10), "歌词 size", 1, 100)
    tint = color(spec.get("color", "#FFFFFF"), "歌词 color")
    animation_xml = ""
    if "animation_ref" in spec:
        animation = resource_ref(spec.get("animation_ref"), "歌词 animation_ref")
        animation_duration = integer(spec.get("animation_duration_ms", min(1000, end - start)),
                                     "歌词 animation_duration_ms", 1)
        require(animation_duration <= end - start, "歌词动画时长不能超过歌词片段时长")
        refs.append({"ref": animation, "asset_type": "anim_text", "role": "lyric_animation", "used_by": node_id})
        animation_xml = (f'<animation ref="{animation}" animation_type="caption" '
                         f'duration="{animation_duration}"></animation>')
    else:
        require("animation_duration_ms" not in spec, "没有 animation_ref 时不能填写 animation_duration_ms")
    return (
        f'<subtitle id="{node_id}">'
        f'<time start="{start}" duration="{end - start}"></time>'
        '<transform justify-self="center" align-self="end" padding-bottom="16%" rotation="0"></transform>'
        f'<content><sub text="{xml_escape(content)}" size="{size}" color="{tint}"></sub></content>'
        f'{animation_xml}'
        '</subtitle>'
    )


def template_slot(slot, refs, owner):
    allowed = {"source_slot_id", "kind", "ref", "content", "font", "font_size", "text_color", "text_alpha"}
    only_keys(slot, allowed, "模板槽位")
    source_id = text(slot.get("source_slot_id"), "模板 source_slot_id")
    kind = slot.get("kind")
    require(kind in {"media", "text", "sticker"}, "模板 kind 只支持 media、text、sticker")
    values = {"source_slot_id": source_id, "kind": kind}
    if kind in {"media", "sticker"}:
        require(set(slot) == {"source_slot_id", "kind", "ref"}, kind + " 槽位只接受 source_slot_id、kind、ref")
        ref = resource_ref(slot.get("ref"), f"模板 {kind} ref")
        values["ref"] = ref
        refs.append({"ref": ref, "asset_type": "local_media" if kind == "media" else "sticker",
                     "used_by": owner, "source_slot_id": source_id})
    else:
        require("ref" not in slot, "text 槽位不接受 ref")
        values["content"] = text(slot.get("content"), "模板 text content")
        if "font" in slot:
            font = resource_ref(slot["font"], "模板 font")
            values["font"] = font
            refs.append({"ref": font, "asset_type": "font", "used_by": owner, "source_slot_id": source_id})
        if "font_size" in slot:
            values["font_size"] = number(slot["font_size"], "模板 font_size", 1, 100)
        if "text_color" in slot:
            values["text_color"] = color(slot["text_color"], "模板 text_color")
        if "text_alpha" in slot:
            values["text_alpha"] = number(slot["text_alpha"], "模板 text_alpha", 0, 1)
    return f'<slot {attrs(values)}></slot>'


def template_node(spec, refs):
    allowed = {"id", "template_ref", "title", "start_ms", "duration_ms", "slots"}
    only_keys(spec, allowed, "官方模板项")
    node_id = identifier(spec.get("id"), "官方模板 id")
    template = resource_ref(spec.get("template_ref"), "官方模板 template_ref")
    title = text(spec.get("title"), "官方模板 title")
    start = integer(spec.get("start_ms", 0), "官方模板 start_ms")
    duration = integer(spec.get("duration_ms"), "官方模板 duration_ms", 1)
    slots = spec.get("slots")
    require(isinstance(slots, list) and slots, "官方模板 slots 必须是非空数组")
    refs.append({"ref": template, "asset_type": "template", "used_by": node_id})
    seen = set()
    rendered = []
    for slot in slots:
        source_id = slot.get("source_slot_id") if isinstance(slot, dict) else None
        require(source_id not in seen, "同一模板不能重复填写 source_slot_id: " + str(source_id))
        seen.add(source_id)
        rendered.append(template_slot(slot, refs, node_id))
    return (f'<template_package id="{node_id}" ref="{template}" title="{xml_escape(title)}">'
            f'<time start="{start}" duration="{duration}"></time>' + "".join(rendered) + '</template_package>')


def build_request(plan):
    only_keys(plan, {"schema", "tts", "lyrics", "templates"}, "计划")
    require(plan.get("schema") == PLAN_SCHEMA, "不支持的官方能力计划 schema")
    groups = {name: plan.get(name, []) for name in ("tts", "lyrics", "templates")}
    require(all(isinstance(value, list) for value in groups.values()), "tts、lyrics、templates 必须是数组")
    require(any(groups.values()), "计划至少需要一项 TTS、歌词或官方模板")
    refs = []
    nodes = []
    seen_ids = set()
    lyric_ranges = []
    builders = {"tts": tts_node, "lyrics": lyric_node, "templates": template_node}
    for group_name, values in groups.items():
        for spec in values:
            require(isinstance(spec, dict), group_name + " 数组成员必须是对象")
            node_id = spec.get("id")
            require(node_id not in seen_ids, "片段 id 重复: " + str(node_id))
            seen_ids.add(node_id)
            nodes.append(builders[group_name](spec, refs))
            if group_name == "lyrics":
                lyric_ranges.append((spec["start_ms"], spec["end_ms"], node_id))
    ordered = sorted(lyric_ranges)
    for left, right in zip(ordered, ordered[1:]):
        require(left[1] <= right[0], f"歌词时间重叠: {left[2]} 与 {right[2]}")
    fragment = "".join(nodes)
    ET.fromstring("<multi>" + fragment + "</multi>")
    expression = ("draft.select(\"multi\").appendXml(" + json.dumps(fragment, ensure_ascii=False)
                  + "); draft.apply();")
    unique_refs = []
    fingerprints = set()
    for item in refs:
        fingerprint = tuple(sorted(item.items()))
        if fingerprint not in fingerprints:
            fingerprints.add(fingerprint)
            unique_refs.append(item)
    return {
        "schema": REQUEST_SCHEMA,
        "tool": "DraftEditing",
        "arguments": {"selection_expression": expression},
        "features": {name: len(value) for name, value in groups.items()},
        "required_refs": unique_refs,
        "resource_policy": "MaterialRecall blueprint_ref 或当前草稿真实 ref",
        "time_unit": "milliseconds",
    }


def write_new(path, value):
    path = Path(path)
    require(path.is_absolute(), "输出路径必须是绝对路径")
    require(not path.exists(), "输出文件已存在")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(data)


def doctor():
    runtime = windows_runtime.doctor()
    install = Path(runtime["install_dir"])
    cli = install / "jianying-agent-cli.exe"
    lyra = install / "lyra-cli.exe"
    skill = install / "Resources/canvas_agent/skills/studio.lyra.xml_timeline_builder/SKILL.md"
    require(cli.is_file() and lyra.is_file() and skill.is_file(), "当前剪映安装缺少官方 Agent/DraftEditing 组件")
    return {
        "status": "ok",
        "runtime_profile": runtime["runtime_profile"],
        "app_build": runtime["app_build"],
        "official_agent_cli": str(cli),
        "official_lyra_cli": str(lyra),
        "xml_timeline_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
        "runtime_token_available": bool(os.environ.get("JIANYING_AGENT_RUNTIME_TOKEN")),
        "draft_editing_invocation": "仅在剪映官方 Agent Runtime 会话中可用",
    }


def call_agent(command, input_path, output_path):
    require(command in AGENT_COMMANDS, "不支持的 jianying-agent-cli 命令")
    runtime = doctor()
    require(os.environ.get("JIANYING_AGENT_RUNTIME_TOKEN"),
            "缺少 JIANYING_AGENT_RUNTIME_TOKEN；请在剪映官方 Agent Runtime 会话中调用，不能从账号文件提取令牌")
    source = Path(input_path).resolve(strict=True)
    target = Path(output_path)
    require(source.is_file() and target.is_absolute() and not target.exists(), "输入必须是文件，输出必须是不存在的绝对路径")
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [runtime["official_agent_cli"], "draft", command, "--input", str(source), "--output", str(target)]
    completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    require(completed.returncode == 0, "官方 Agent 调用失败: " + (completed.stderr.strip() or completed.stdout.strip()))
    require(target.is_file(), "官方 Agent 未生成输出文件")
    return strict_json(target)


def absolute_directory(path, label):
    path = Path(path)
    require(path.is_absolute() and path.is_dir(), label + " 必须是已存在的绝对目录")
    require(not path.is_symlink(), label + " 不能是符号链接")
    return path.resolve()


def draft_ref(value):
    value = text(value, "draft_ref")
    require(DRAFT_REF_PATTERN.fullmatch(value), "draft_ref 格式不合法")
    return value


def lyra_environment(root):
    env = dict(os.environ)
    require(env.get("JIANYING_AGENT_RUNTIME_TOKEN"),
            "缺少 JIANYING_AGENT_RUNTIME_TOKEN；apply/render 必须由剪映官方 Agent Runtime 启动")
    env["CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE"] = str(root)
    env["LYRA_CLI_ROOT_WORKSPACE"] = str(root)
    return env


def call_lyra(arguments, root, timeout):
    runtime = doctor()
    completed = subprocess.run(
        [runtime["official_lyra_cli"], *arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=lyra_environment(root))
    require(completed.returncode == 0,
            "官方 lyra-cli 调用失败: " + (completed.stderr.strip() or completed.stdout.strip()))
    return completed


def apply_plan(plan_path, workspace_path, draft_directory, current_draft_ref, audit_path):
    plan_path = Path(plan_path).resolve(strict=True)
    require(plan_path.is_file(), "plan 必须是文件")
    workspace = absolute_directory(workspace_path, "workspace")
    draft_dir = absolute_directory(draft_directory, "draft_dir")
    current_ref = draft_ref(current_draft_ref)
    audit = Path(audit_path)
    require(audit.is_absolute() and not audit.exists(), "audit 必须是不存在的绝对路径")
    audit.mkdir(parents=True)

    request = build_request(strict_json(plan_path))
    request["source_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    write_new(audit / "request.json", request)
    selection = audit / "selection.expr"
    selection.write_text(request["arguments"]["selection_expression"] + "\n", encoding="utf-8")
    args = ["draft", "blueprint", "apply", "--workspace", str(workspace), "--dir", str(draft_dir),
            "--ref", current_ref, "--selection-file", str(selection),
            "--allow-existing-main-deletion", "--allow-existing-subtitle-changes"]
    completed = call_lyra(args, draft_dir, 600)
    (audit / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (audit / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    result = {"status": "applied", "draft_ref": current_ref, "audit": str(audit),
              "request": str(audit / "request.json"), "selection": str(selection)}
    write_new(audit / "result.json", result)
    return result


def render_draft(draft_directory, current_draft_ref, output_path, timeout):
    draft_dir = absolute_directory(draft_directory, "draft_dir")
    current_ref = draft_ref(current_draft_ref)
    output = Path(output_path)
    report = output.with_suffix(output.suffix + ".result.json")
    require(output.is_absolute() and output.suffix.lower() == ".mp4" and not output.exists()
            and not report.exists(),
            "out 必须是不存在的绝对 MP4 路径")
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = call_lyra(["draft", "export", "--ref", current_ref, "--output", str(output),
                           "--timeout", f"{timeout}s"], draft_dir, timeout + 60)
    require(output.is_file() and output.stat().st_size > 0, "官方渲染没有生成非空 MP4")
    result = {"status": "rendered", "draft_ref": current_ref, "output": str(output),
              "size": output.stat().st_size,
              "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}
    write_new(report, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="检查官方 Agent/DraftEditing 组件")
    build = sub.add_parser("build", help="生成 DraftEditing Selection Expression 请求")
    build.add_argument("--plan", required=True)
    build.add_argument("--out", required=True)
    call = sub.add_parser("call-agent", help="调用官方 jianying-agent-cli")
    call.add_argument("--command", dest="agent_command", choices=sorted(AGENT_COMMANDS), required=True)
    call.add_argument("--input", required=True)
    call.add_argument("--out", required=True)
    apply = sub.add_parser("apply", help="在官方 Agent Runtime 中应用 TTS、歌词与模板计划")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--workspace", required=True)
    apply.add_argument("--draft-dir", required=True)
    apply.add_argument("--draft-ref", required=True)
    apply.add_argument("--audit", required=True)
    render = sub.add_parser("render", help="用官方 lyra-cli 渲染已应用功能的草稿")
    render.add_argument("--draft-dir", required=True)
    render.add_argument("--draft-ref", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        result = doctor()
    elif args.command == "build":
        plan_path = Path(args.plan).resolve(strict=True)
        result = build_request(strict_json(plan_path))
        result["source_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        write_new(Path(args.out), result)
    elif args.command == "call-agent":
        result = call_agent(args.agent_command, args.input, args.out)
    elif args.command == "apply":
        result = apply_plan(args.plan, args.workspace, args.draft_dir, args.draft_ref, args.audit)
    else:
        require(5 <= args.timeout <= 43_200, "timeout 必须在 5..43200 秒")
        result = render_draft(args.draft_dir, args.draft_ref, Path(args.out), args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("官方能力调用失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
