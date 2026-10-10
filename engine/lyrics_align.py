#!/usr/bin/env python3
"""歌词句与官方模板卡的确定性对齐，以及按槽位权重的文本切分。

对齐规则（不猜时间、不做相似度归一化）：

1. 一句歌词归属**其时间中心所在**的模板卡；中心不落在任何卡时间窗内的句子
   不属于歌词区（例如片头口播），直接排除。
2. 每张卡消费归属它的全部句子，按时间顺序。
3. 逐卡校验：词数不得少于槽位数，且归属句子的时间跨度与卡时间窗的交叠比例
   不低于阈值；任一不满足即判为 skipped 并给出原因，不回退猜测。

这样既避免了"按重叠贪心"串入相邻句（实测本地识别时间轴与原草稿歌词时间存在
数十毫秒到数百毫秒偏移），也避免了"最少句优先"漏掉卡片尾句。
"""
from __future__ import annotations

MIN_OVERLAP = 0.5


def split_by_weights(words, weights):
    """按槽位权重切分词序列；词数不足以填满槽位时返回 None。"""
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


def overlap_ratio(start_ms, end_ms, other_start_ms, other_end_ms):
    span = end_ms - start_ms
    if span <= 0:
        return 0.0
    covered = max(0, min(end_ms, other_end_ms) - max(start_ms, other_start_ms))
    return min(1.0, covered / span)


def cue_words(cues):
    return [word for cue in cues for word in cue["words"]]


def assign_by_center(cards, cues):
    """返回 {card_id: [cue 索引]} 与未被歌词区覆盖的 cue 索引。"""
    ordered = sorted(cards, key=lambda card: card["start_ms"])
    assigned = {card["id"]: [] for card in ordered}
    outside = []
    for index, cue in enumerate(cues):
        center = (cue["start_ms"] + cue["end_ms"]) // 2
        owner = next((card for card in ordered
                      if card["start_ms"] <= center < card["end_ms"]), None)
        if owner is None:
            outside.append(index)
            continue
        assigned[owner["id"]].append(index)
    return assigned, outside


def align_cards(cards, cues, min_overlap=MIN_OVERLAP):
    """把歌词句对齐到模板卡。

    ``cards`` 每项形如 ``{"id", "start_ms", "end_ms", "slots", "weights"}``，
    ``cues`` 为识别结果（含 ``words``）。返回 ``(mapping, report)``：
    ``mapping`` 仅包含可用卡片，``report`` 记录每张卡的判定与原因。
    """
    ordered = sorted(cards, key=lambda card: card["start_ms"])
    assigned, outside = assign_by_center(ordered, cues)
    mapping, report = {}, []
    for card in ordered:
        indices = assigned.get(card["id"]) or []
        picked = [cues[index] for index in indices]
        words = cue_words(picked)
        record = {"id": card["id"], "cues": indices, "slots": card["slots"],
                  "words": len(words), "start_ms": card["start_ms"], "end_ms": card["end_ms"]}
        if not picked:
            record.update(status="skipped", reason="卡时间窗内没有歌词句")
            report.append(record)
            continue
        ratio = overlap_ratio(card["start_ms"], card["end_ms"],
                              min(cue["start_ms"] for cue in picked),
                              max(cue["end_ms"] for cue in picked))
        record["overlap_ratio"] = round(ratio, 3)
        if len(words) < card["slots"]:
            record.update(status="skipped",
                          reason=f"词数 {len(words)} 少于槽位 {card['slots']}")
            report.append(record)
            continue
        if ratio < min_overlap:
            record.update(status="skipped",
                          reason=f"与卡时间窗交叠仅 {ratio:.0%}，低于 {min_overlap:.0%}")
            report.append(record)
            continue
        segments = split_by_weights(words, card["weights"])
        if segments is None:
            record.update(status="skipped", reason="槽位无法用现有词数填充")
            report.append(record)
            continue
        record.update(status="aligned", segments=segments)
        report.append(record)
        mapping[card["id"]] = indices
    return mapping, {"cards": report, "outside_cue_indices": outside,
                     "aligned_cards": len(mapping), "skipped_cards": len(ordered) - len(mapping)}
