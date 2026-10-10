#!/usr/bin/env python3
"""按官方 XMLDRAFT 协议规范化 Blueprint 工作区的 canonical XML。

官方 `draft blueprint apply` 会先做 XML 协议校验与目标审计，两类问题必须在
apply 之前修掉，否则 lyra-cli 直接返回失败：

1. **属性所有者**：`font_ref` 属于 ``text|sub|slot|style|text_style``，不允许挂在
   ``<subtitle>`` 宿主上；而且它的值必须是资源库引用，物理路径会被
   ``does not exist in the resource library`` 拒绝（``blueprint resource --import``
   不支持字体）。因此默认 `--mode drop` 移除字体引用，文字回退到默认字体；
   `--mode move` 只把宿主上的 font_ref 迁到 ``<sub>``。
2. **主轨素材范围**：主轨片段的 ``material_start + duration * speed`` 不得超过素材
   时长，否则目标审计报 ``main.source_range.exceeds_resource``。`--fix-main-range`
   按官方修复指令把片段拆成多段，保持总时长不变。

本脚本只改工作区的 XML，不触碰草稿；写入由 apply 完成。

用法：
    python tools/normalize_canonical_xml.py --workspace C:\\Temp\\jy-ws \\
        --mode drop --fix-main-range [--dry-run]
"""
import argparse
import json
from pathlib import Path
import re

FILES = ("target_draft.xml", "current_draft.xml")
SUBTITLE = re.compile(r"<subtitle\b(?P<attrs>[^>]*)>(?P<body>.*?)</subtitle>", re.S)
FONT_REF = re.compile(r'\s+font_ref="[^"]*"')
MAIN = re.compile(r"<main\b(?P<attrs>[^>]*)>(?P<body>.*?)</main>", re.S)
VIDEO = re.compile(r"(?P<open>[ \t]*<video\b(?P<attrs>[^>]*)>)(?P<body>.*?)(?P<close></video>)", re.S)
TIME = re.compile(r"<time\b[^>]*/>")
ATTR = re.compile(r'%s="([^"]*)"')


def time_attr(tag, name, default=None):
    found = re.search(ATTR.pattern % name, tag)
    return found.group(1) if found else default


def normalize_font_ref(text, mode):
    """按所有者模型处理 font_ref；返回新文本与被处理的路径列表。"""
    handled = []

    def fix(match):
        found = FONT_REF.search(match.group("attrs"))
        attrs = FONT_REF.sub("", match.group("attrs"))
        body = match.group("body")
        if found:
            handled.append(found.group(0).strip())
            if mode == "move":
                path = found.group(0).split('"')[1]
                body = body.replace('<sub ', f'<sub font_ref="{path}" ')
        return f"<subtitle{attrs}>{body}</subtitle>"

    updated = SUBTITLE.sub(fix, text)
    if mode == "drop":
        updated = FONT_REF.sub("", updated)
    return updated, handled


def split_overflow(body, attrs, opener, closer, limit_ms, report):
    """把超出素材范围的主轨片段拆成多段，返回新的片段 XML 或 None。"""
    timing = TIME.search(body)
    if timing is None:
        return None
    tag = timing.group(0)
    speed = float(time_attr(tag, "speed", "1") or 1)
    start = int(time_attr(tag, "material_start", "0") or 0)
    duration = int(time_attr(tag, "duration", "0") or 0)
    if duration <= 0 or start + duration * speed <= limit_ms + 0.5:
        return None
    base_id = time_attr(attrs, "id", "main")
    cursor, remaining, pieces, suffix = start, duration, [], 0
    while remaining > 0:
        available = int((limit_ms - cursor) / speed)
        take = min(remaining, available)
        if take <= 0:
            break
        suffix += 1
        segment_id = base_id if suffix == 1 else f"{base_id}_b{suffix}"
        new_attrs = re.sub(ATTR.pattern % "id", f'id="{segment_id}"', attrs)
        new_time = f'<time material_start="{cursor}" duration="{take}" speed="{speed:g}" />'
        pieces.append((opener.replace(attrs, new_attrs), body.replace(tag, new_time),
                       closer, segment_id))
        remaining -= take
        cursor = max(0, limit_ms - int(remaining * speed))
    if remaining > 0:
        report.append({"segment": base_id, "error": "无法在素材范围内容纳该片段"})
        return None
    report.append({"segment": base_id, "ref": time_attr(attrs, "ref"),
                   "original_duration_ms": duration, "limit_ms": limit_ms,
                   "pieces": [{"id": piece[3],
                               "material_start_ms": int(time_attr(piece[1], "material_start")),
                               "duration_ms": int(time_attr(piece[1], "duration"))} for piece in pieces]})
    return "\n".join(piece[0] + piece[1] + piece[2] for piece in pieces)


def fix_main_range(text, durations, report):
    """拆分所有超出素材范围的主轨 video 片段。"""
    def fix_main(main_match):
        def fix_video(video_match):
            attrs = video_match.group("attrs")
            limit = durations.get(time_attr(attrs, "ref"))
            if not limit:
                return video_match.group(0)
            fixed = split_overflow(video_match.group("body"), attrs, video_match.group("open"),
                                   video_match.group("close"), limit, report)
            return fixed if fixed else video_match.group(0)

        return ("<main" + main_match.group("attrs") + ">"
                + VIDEO.sub(fix_video, main_match.group("body")) + "</main>")

    return MAIN.sub(fix_main, text)


def resource_durations(workspace):
    """从 resource_map.json 取 ref -> 素材时长(ms)。"""
    path = Path(workspace) / "resource_map.json"
    if not path.is_file():
        return {}
    result = {}
    for entry in json.loads(path.read_text(encoding="utf-8")):
        duration = (entry.get("metadata") or {}).get("duration_us") or entry.get("duration_us")
        if isinstance(duration, (int, float)) and duration > 0:
            result[entry.get("asset_id")] = int(duration / 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Blueprint 工作区（纯 ASCII 路径）")
    parser.add_argument("--mode", choices=("drop", "move"), default="drop")
    parser.add_argument("--fix-main-range", action="store_true",
                        help="拆分超出素材范围的主轨片段（官方目标审计要求）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve(strict=True)
    durations = resource_durations(workspace)
    report = {}
    for name in FILES:
        path = workspace / name
        if not path.is_file():
            report[name] = {"missing": True}
            continue
        text = path.read_text(encoding="utf-8")
        updated, handled = normalize_font_ref(text, args.mode)
        splits = []
        if args.fix_main_range:
            updated = fix_main_range(updated, durations, splits)
        report[name] = {"font_ref_handled": len(handled), "main_splits": splits,
                        "changed": updated != text}
        if not args.dry_run and updated != text:
            path.write_text(updated, encoding="utf-8")
    print(json.dumps({"workspace": str(workspace), "mode": args.mode,
                      "dry_run": args.dry_run, "files": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
