#!/usr/bin/env python3
"""把歌词按模板槽位直接写入草稿结构，修正官方 apply 的槽位分发缺口。

官方 ``draft edit --update "text=1;target=A|B|C"`` 会把整串文本写进模板共享的
text material，却不重分配 ``text_info_resources[].word_index``，结果是每个输入框
都显示整串（实测 t6 的四个槽全部变成 ``于是|不觉可|问春风``）。本模块在官方 apply
之后按槽位比例重分配 ``word_index`` 并写回各槽子串，使模板槽位与歌词一致。

只写任务自有的草稿副本；不触碰源草稿，不改动模板 ref 与动画 ref。
"""
from __future__ import annotations

import json
from pathlib import Path

import windows_runtime


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mirrors(folder, timeline_id):
    folder = Path(folder)
    return [folder / "draft_content.json", folder / "template-2.tmp",
            folder / "Timelines" / timeline_id / "draft_content.json",
            folder / "Timelines" / timeline_id / "template-2.tmp"]


def read_timeline(folder):
    path = Path(folder) / "draft_content.json"
    return windows_runtime._decrypt_metadata_in_memory(path)


def write_timeline(folder, timeline):
    import tempfile

    payload = windows_runtime.packed(timeline)
    with tempfile.TemporaryDirectory(prefix="jianying-slot-cipher-") as temp:
        staged = Path(temp) / "cipher.bin"
        # 官方加解密入口拒绝覆盖已有输出，因此先落到一次性文件再分发到各镜像。
        windows_runtime._encrypt_metadata_from_memory(payload, staged)
        cipher = staged.read_bytes()
    written = []
    for path in mirrors(folder, timeline["id"]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cipher)
        written.append(str(path))
    require(len(set(written)) == 4, "草稿镜像路径异常")
    return written


def update_text_material(material, value, words):
    """同步一个槽位文本材料的正文、样式区间与字级时间。"""
    content = json.loads(material.get("content") or "{}")
    content["text"] = value
    length = len(value.encode("utf-16-le")) // 2
    for style in content.get("styles") or []:
        style["range"] = [0, length]
    material["content"] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    material["recognize_text"] = value
    material["words"] = {"text": [word["text"] for word in words],
                         "start_time": [word["start_time"] for word in words],
                         "end_time": [word["end_time"] for word in words]}


def redistribute(resources, words, previous_count):
    """按原槽位比例把新词重新分配到各输入框。"""
    count = len(words)
    require(count > 0, "模板卡没有可用词")
    base = max(1, previous_count)
    for resource in resources:
        old = resource.get("word_index") or [0, base]
        start = min(count, round(old[0] * count / base))
        end = min(count, max(start + 1, round(old[1] * count / base)))
        resource["word_index"] = [start, end]
    return count


def rewrite(draft_dir, workspace, cues, mapping):
    """按对齐映射改写草稿里的模板卡；返回改写报告。"""
    draft_dir = Path(draft_dir).resolve(strict=True)
    id_map_path = Path(workspace) / "id_map.json"
    require(id_map_path.is_file(), "缺少 id_map.json；请先完成 blueprint sync")
    id_map = {row["xml_id"]: row["seg_id"]
              for row in json.loads(id_map_path.read_text(encoding="utf-8"))}
    timeline = read_timeline(draft_dir)
    segments = {segment["id"]: segment for track in timeline.get("tracks", [])
                for segment in track.get("segments", [])}
    materials = {}
    for bucket, nodes in timeline.get("materials", {}).items():
        for node in nodes:
            materials[node["id"]] = (bucket, node)
    texts = {node["id"]: node for node in timeline.get("materials", {}).get("texts", [])}

    report = []
    for card_id, indices in mapping.items():
        segment_id = id_map.get(card_id)
        require(segment_id, "id_map 缺少卡片 " + card_id)
        segment = segments.get(segment_id)
        require(segment, "草稿缺少片段 " + segment_id)
        bucket, template = materials.get(segment["material_id"], (None, None))
        require(template is not None and template.get("type") == "text_template_lyrics",
                f"卡片 {card_id} 不是官方歌词模板卡")
        start_ms = segment["target_timerange"]["start"] // 1000
        words = []
        for index in indices:
            for word in cues[index]["words"]:
                words.append({"text": word["text"],
                              "start_time": max(0, word["start_ms"] - start_ms),
                              "end_time": max(1, word["end_ms"] - start_ms)})
        require(words, f"卡片 {card_id} 没有对齐词")
        text = "".join(word["text"] for word in words)
        previous = template.get("origin_word_info") or {}
        previous_count = len(previous.get("words") or []) or len(words)
        info = {"start_time": start_ms, "end_time": start_ms + (segment["target_timerange"]["duration"] // 1000),
                "text": text, "words": words}
        template["origin_word_info"] = json.loads(json.dumps(info))
        template["current_word_info"] = json.loads(json.dumps(info))
        resources = template.get("text_info_resources") or []
        require(resources, f"卡片 {card_id} 没有输入框资源")
        redistribute(resources, words, previous_count)
        slots = []
        for resource in resources:
            span = resource["word_index"]
            subset = words[span[0]:span[1]]
            value = "".join(word["text"] for word in subset)
            material = texts.get(resource.get("text_material_id"))
            if material is not None:
                update_text_material(material, value, subset)
            slots.append(value)
        report.append({"card": card_id, "segment_id": segment_id, "slots": slots,
                       "word_count": len(words), "start_ms": start_ms})
    require(report, "没有任何卡片需要改写")
    written = write_timeline(draft_dir, timeline)
    return {"cards": report, "mirrors": written}
