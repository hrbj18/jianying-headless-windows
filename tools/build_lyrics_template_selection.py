#!/usr/bin/env python3
"""把本地歌词按 Blueprint 工作区里的官方歌词模板卡生成 Selection Expression。

对齐由映射文件显式给出（卡 id → 歌词句索引）。刻意不做自动时间推断：官方规范
禁止猜测歌词时间，而实测本地识别时间轴与原草稿歌词时间存在偏移，按重叠自动匹配
会把相邻句串进同一张卡。程序只校验交叠比例与槽位可行性，失败即报错，不降级猜测。

切分沿用模板原有槽位字符比例，因此不改变模板的视觉分词设计。

输出：工作区内的 ``edit.selection``（含结尾的 ``draft.apply()``）与对账报告
``lyrics-template-report.json``，可由 ``engine/draftediting_runtime.py apply`` 使用。

用法：
    python tools/build_lyrics_template_selection.py \\
        --workspace C:\\Temp\\jy-ws --map examples/lyrics-template-map.json
"""
import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP = ROOT / "examples" / "lyrics-template-map.json"
MIN_OVERLAP = 0.5


def xml_escape(value):
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def split_by_weights(words, weights):
    """按槽位权重切分词序列；槽位数无法容纳（词数不足）时返回 None。"""
    texts = [word["text"] for word in words]
    slots = len(weights)
    if slots < 1 or len(texts) < slots:
        return None
    total = sum(weights) or slots
    raw = [weight / total * len(texts) for weight in weights]
    quota = [max(1, int(value)) for value in raw]
    while sum(quota) < len(texts):
        quota[max(range(slots), key=lambda index: raw[index] - quota[index])] += 1
    while sum(quota) > len(texts):
        candidates = [index for index in range(slots) if quota[index] > 1]
        if not candidates:
            return None
        quota[min(candidates, key=lambda index: raw[index] - quota[index])] -= 1
    segments, cursor = [], 0
    for take in quota:
        segments.append("".join(texts[cursor:cursor + take]))
        cursor += take
    return segments


def overlap_ratio(card_start, card_end, cues):
    span = card_end - card_start
    if span <= 0:
        return 0.0
    covered = sum(max(0, min(card_end, cue["end_ms"]) - max(card_start, cue["start_ms"]))
                  for cue in cues)
    return min(1.0, covered / span)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Blueprint 工作区（纯 ASCII 路径）")
    parser.add_argument("--map", default=str(DEFAULT_MAP), help="卡与歌词句的对齐配置")
    parser.add_argument("--output", default=None, help="Selection 输出路径，默认工作区 edit.selection")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve(strict=True)
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    if mapping.get("schema") != "jianying-lyrics-template-map/v1":
        raise SystemExit("不支持的映射配置 schema")
    lyrics_path = Path(mapping["lyrics"])
    if not lyrics_path.is_absolute():
        lyrics_path = ROOT / lyrics_path
    lyrics = json.loads(lyrics_path.read_text(encoding="utf-8"))
    cues = lyrics["cues"]
    root = ET.fromstring((workspace / "current_draft.xml").read_text(encoding="utf-8"))
    multi = root.find("multi")
    if multi is None:
        raise SystemExit("canonical XML 缺少 <multi>")
    cards = {node.get("id"): node for node in multi
             if node.tag == "text" and node.find("template") is not None}

    used, lines, report = set(), [], []
    for entry in mapping["cards"]:
        node = cards.get(entry["id"])
        if node is None:
            raise SystemExit("映射引用了不存在的模板卡: " + str(entry["id"]))
        indices = entry["cues"]
        if len(set(indices)) != len(indices) or used.intersection(indices):
            raise SystemExit("歌词句被重复使用: " + str(indices))
        picked = [cues[index] for index in indices]
        subs = node.find("content").findall("sub")
        timing = node.find("time")
        start = int(timing.get("start"))
        end = start + int(timing.get("duration"))
        ratio = overlap_ratio(start, end, picked)
        words = [word for cue in picked for word in cue["words"]]
        segments = split_by_weights(words, [len(sub.get("text") or "") for sub in subs])
        record = {"id": entry["id"], "cues": indices, "start_ms": start, "end_ms": end,
                  "overlap_ratio": round(ratio, 3), "slots": len(subs), "words": len(words),
                  "old": [sub.get("text") for sub in subs]}
        if ratio < MIN_OVERLAP:
            raise SystemExit(f"卡片 {entry['id']} 与所映射歌词的交叠仅 {ratio:.0%}，"
                             f"低于 {MIN_OVERLAP:.0%}")
        if segments is None:
            raise SystemExit(f"卡片 {entry['id']} 的 {len(subs)} 个槽位无法用 {len(words)} 个词填充")
        record["new"] = segments
        report.append(record)
        used.update(indices)
        # 官方规范：模板多输入框只表达目标结果 —— 按输入框顺序给出多个 <sub>。
        fragment = "".join(f'<sub text="{xml_escape(value)}"></sub>' for value in segments)
        lines.append(f'draft.select("#{entry["id"]} content").replaceChildrenXml('
                     f'{json.dumps(fragment, ensure_ascii=False)});')

    output = Path(args.output) if args.output else workspace / "edit.selection"
    # lyra-cli 直连模式要求表达式以 draft.apply() 收尾（Agent 工具会自动补）。
    lines.append("draft.apply();")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (workspace / "lyrics-template-report.json").write_text(
        json.dumps({"schema": "jianying-lyrics-template-apply/v1", "selection": str(output),
                    "expressions": len(lines), "cards": report},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = [row for row in report if row["old"] != row["new"]]
    print(json.dumps({"selection": str(output), "expressions": len(lines),
                      "cards": len(report), "changed_cards": len(changed), "report": report},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
