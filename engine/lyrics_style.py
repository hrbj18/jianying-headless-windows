#!/usr/bin/env python3
"""从剪映 lyric_animation（LyricStyle）模板提取可用样式，用于等效渲染。

这类模板由剪映客户端的**歌词引擎**渲染（`text_template_default_impl` +
`LyricStyle.json`）。无头原生渲染走 EffectSDK 的 ExportService，它要求模板提供
`content.json` / `anim.prefab` 这类 EffectSDK 素材；而 lyric_animation 的资源包里
本来就没有这些文件（实测下载资源包验证），因此无头链路无法直接渲染该类模板。

本模块把它的样式参数——字体、字号、配色、斜体、行距、每行字数——提取出来，供生成
等效的普通字幕卡使用，从而在无头链路里复现该模板的观感。
"""
from __future__ import annotations

import json
from pathlib import Path

import windows_runtime


def _newest_timeline(folder):
    folder = Path(folder)
    candidates = sorted((folder / "Timelines").glob("*/draft_content.json"))
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)
    return folder / "draft_content.json"


def extract(draft_dir):
    """提取草稿里歌词模板的样式；找不到时返回 None。"""
    folder = Path(draft_dir).resolve(strict=True)
    timeline = windows_runtime._decrypt_metadata_in_memory(_newest_timeline(folder))
    for node in timeline.get("materials", {}).get("text_templates", []) or []:
        if not node.get("is_lyric_effect"):
            continue
        style_path = Path(str(node.get("path") or "")) / "LyricStyle.json"
        if not style_path.is_file():
            continue
        style = json.loads(style_path.read_text(encoding="utf-8"))
        text_style = style.get("text_style") or {}
        fonts = [item.get("path") for item in (node.get("resources") or [])
                 if item.get("panel") == "fonts" and item.get("path")]
        animations = style.get("animations") or {}
        return {
            "source": "lyric_animation",
            "template_name": node.get("name"),
            "resource_id": node.get("resource_id"),
            "layout_title": style.get("title"),
            "font_path": fonts[0] if fonts else None,
            "font_ids": (text_style.get("font_id") or []),
            "font_size": text_style.get("font_size"),
            "colors": list(text_style.get("text_color") or ["#FFFFFF"]),
            "color_random": bool(text_style.get("text_color_random")),
            "italic": bool(text_style.get("global_italic")),
            "bold": bool(text_style.get("global_bold")),
            "alignment": text_style.get("alignment"),
            "line_spacing": text_style.get("line_spacing"),
            "letter_spacing": text_style.get("letter_spacing"),
            "line_max_letter_num": text_style.get("line_max_letter_num"),
            "duration_ratio": animations.get("duration_ratio"),
            "max_duration_s": animations.get("max_dur"),
            "min_duration_s": animations.get("min_dur"),
            "note": "lyric_animation 模板由客户端歌词引擎渲染，"
                    "无头 EffectSDK 链路不支持；此处按其样式生成等效字幕。",
        }
    return None


def color_for(style, index):
    """按模板的取色方式为第 index 句选颜色（默认取色是随机，这里做成确定性交替）。"""
    colors = [color for color in (style.get("colors") or []) if color]
    if not colors:
        return "#FFFFFF"
    if not style.get("color_random") or len(colors) == 1:
        return colors[0]
    return colors[index % len(colors)]
