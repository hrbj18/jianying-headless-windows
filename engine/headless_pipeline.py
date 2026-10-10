#!/usr/bin/env python3
"""无头剪映端到端流水线：自动识别 → 官方歌词模板 → TTS → 官方渲染。

一条命令串起四个环节，每步产物与判定都落盘：

1. ``recognize``  本地 ASR 自动识别（直接音频，或 JYPACK 草稿里的音乐轨），
                  复用 ``engine/lyrics_generate.py`` 的时间映射；
2. ``blueprint``  把草稿复制到剪映草稿根下的 ASCII 工作副本，初始化 Blueprint
                  工作区并同步为 canonical XML；
3. ``align``      读 canonical XML 的官方歌词模板卡，用 ``engine/lyrics_align.py``
                  按"歌词句时间中心归属卡"的确定性规则自动对齐；
4. ``selection``  生成 Selection（模板卡整段替换 + 可选官方 ``<speech>`` TTS）；
5. ``apply``      规范化 canonical XML 后调用官方 ``lyra-cli blueprint apply``；
6. ``render``     可选：调用本机原生 ExportService 渲染成片。

刻意保留的边界：不伪造资源 ref（TTS 音色只能来自草稿已有音色或显式 ``--tone-ref``）、
不猜测歌词时间（对齐失败即记录 skipped）、不修改用户原草稿（默认复制工作副本）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for folder in (HERE, ROOT / "tools"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import draftediting_runtime  # noqa: E402
import lyrics_align  # noqa: E402
import lyrics_generate  # noqa: E402
import lyrics_style  # noqa: E402
import lyra_cli  # noqa: E402
import normalize_canonical_xml  # noqa: E402
import windows_runtime  # noqa: E402


REPORT_SCHEMA = "jianying-headless-pipeline/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def xml_escape(value):
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def ascii_name(prefix):
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


def card_specs(xml_text):
    """从 canonical XML 读取官方歌词模板卡（``<text>`` 内含 ``<template>``）。"""
    root = ET.fromstring(xml_text)
    multi = root.find("multi")
    require(multi is not None, "canonical XML 缺少 <multi>")
    cards = []
    for node in multi:
        if node.tag != "text" or node.find("template") is None:
            continue
        timing = node.find("time")
        require(timing is not None, "模板卡缺少 <time>")
        subs = node.find("content").findall("sub")
        require(subs, "模板卡 <content> 没有 <sub> 输入槽")
        start = int(timing.get("start"))
        cards.append({"id": node.get("id"), "template_ref": node.find("template").get("ref"),
                      "start_ms": start, "end_ms": start + int(timing.get("duration")),
                      "slots": len(subs),
                      "weights": [len(sub.get("text") or "") or 1 for sub in subs]})
    require(cards, "草稿里没有官方歌词模板卡（<text> + <template>）")
    return cards


def tone_refs(resource_map_path):
    """草稿已有的 TTS 音色引用；不联网、不猜造。"""
    path = Path(resource_map_path)
    if not path.is_file():
        return []
    found = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        metadata = entry.get("metadata") or {}
        tone = metadata.get("tone_ref") or entry.get("tone_ref")
        if isinstance(tone, str) and tone and tone not in found:
            found.append(tone)
    return found


def build_selection(cards, mapping, report, tts=False, speech_ref=None):
    """生成 Selection Expression（模板卡目标结果 + 可选 TTS 朗读）。"""
    rows = {row["id"]: row for row in report["cards"]}
    lines, applied = [], []
    for card in cards:
        # 对齐报告里 skipped 的卡没有 segments，映射与报告不一致时一律跳过。
        segments = (rows.get(card["id"]) or {}).get("segments")
        if not mapping.get(card["id"]) or not segments:
            continue
        fragment = "".join(f'<sub text="{xml_escape(text)}"></sub>' for text in segments)
        lines.append(f'draft.select("#{card["id"]} content").replaceChildrenXml('
                     f'{json.dumps(fragment, ensure_ascii=False)});')
        # 实测：整段替换 content 会让官方 apply 重算模板卡时长（t11 曾从 7800ms 收缩到
        # 300ms），进而让后续识别结果落不到任何卡窗内。这里显式写回原时间窗。
        lines.append(f'draft.select("#{card["id"]} time")'
                     f'.attr("start", "{card["start_ms"]}")'
                     f'.attr("duration", "{card["end_ms"] - card["start_ms"]}");')
        if tts:
            require(speech_ref, "启用 TTS 需要可用的音色引用")
            lines.append(f'draft.select("#{card["id"]}").appendXml('
                         f'{json.dumps(f"<speech ref={json.dumps(speech_ref)}></speech>")});')
        applied.append(card["id"])
    require(lines, "没有任何卡片完成对齐，无法生成 Selection")
    # lyra-cli 直连模式要求表达式以 draft.apply() 收尾。
    lines.append("draft.apply();")
    return "\n".join(lines) + "\n", applied


def normalize_workspace(workspace):
    """规范化 canonical XML：字体引用降级 + 主轨素材越界拆分。"""
    workspace = Path(workspace)
    durations = normalize_canonical_xml.resource_durations(workspace)
    report = {}
    for name in normalize_canonical_xml.FILES:
        path = workspace / name
        if not path.is_file():
            report[name] = {"missing": True}
            continue
        text = path.read_text(encoding="utf-8")
        updated, handled = normalize_canonical_xml.normalize_font_ref(text, "drop")
        splits = []
        updated = normalize_canonical_xml.fix_main_range(updated, durations, splits)
        report[name] = {"font_ref_handled": len(handled), "main_splits": splits,
                        "changed": updated != text}
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    return report


def working_copy(draft_dir, draft_root, prefix):
    """把草稿复制成草稿根下的 ASCII 工作副本（官方链路要求 ASCII + 草稿根）。"""
    source = Path(draft_dir).resolve(strict=True)
    require(source.parent == Path(draft_root).resolve(),
            f"源草稿必须位于剪映草稿根下: {draft_root}")
    target = Path(draft_root) / ascii_name(prefix)
    require(not target.exists(), "工作副本已存在，请重试")
    shutil.copytree(source, target, copy_function=shutil.copy2)
    return target


LYRIC_SUBTITLE_STYLE = {
    "size": "5", "color": "#FFFFFF", "outline_color": "#000000", "outline_width": "39.999999",
    "offset_y": "-25.035032%", "scale": "2.154607",
}


def existing_subtitle_windows(xml_text):
    """canonical XML 里已有字幕的时间窗（官方要求句级字幕不得重叠）。"""
    root = ET.fromstring(xml_text)
    multi = root.find("multi")
    if multi is None:
        return []
    windows = []
    for node in multi:
        if node.tag != "subtitle":
            continue
        timing = node.find("time")
        if timing is None:
            continue
        start = int(timing.get("start") or 0)
        windows.append((start, start + int(timing.get("duration") or 0)))
    return windows


def fit_subtitle_cues(cues, blocked, min_duration_ms=200):
    """把识别句裁剪成不重叠、且不覆盖已有字幕的字幕区间。"""
    fitted, previous_end = [], 0
    for cue in cues:
        start, end = cue["start_ms"], cue["end_ms"]
        for blocked_start, blocked_end in blocked:
            if start < blocked_end and end > blocked_start:
                start = max(start, blocked_end)
        start = max(start, previous_end)
        if end - start < min_duration_ms:
            continue
        fitted.append({"id": cue["id"], "text": cue["text"], "start_ms": start, "end_ms": end})
        previous_end = end
    return fitted


def lyric_subtitle_selection(cues, style=None, id_prefix="lyric", colors=None):
    """把识别歌词生成普通字幕卡 Selection。

    实测：官方歌词动效模板（``text_template_lyrics``）在离线原生渲染里不产出可见文字，
    而普通 ``<subtitle>`` 正常渲染（草稿原有的 TTS 字幕帧已确认）。因此提供这条
    可渲染的歌词落地路径，样式沿用草稿已有字幕的白色描边大字；``colors`` 可按句覆盖颜色。
    """
    merged = {**LYRIC_SUBTITLE_STYLE, **(style or {})}
    palette = [color for color in (colors or []) if color]
    require(cues, "没有可用于生成字幕的歌词句")
    lines = []
    for index, cue in enumerate(cues, 1):
        tint = palette[(index - 1) % len(palette)] if palette else merged["color"]
        node = (
            f'<subtitle id="{id_prefix}_{index:02d}">'
            f'<time start="{cue["start_ms"]}" duration="{max(1, cue["end_ms"] - cue["start_ms"])}"></time>'
            f'<transform align-self="center" justify-self="center" '
            f'offset_y="{merged["offset_y"]}" scale="{merged["scale"]}"></transform>'
            f'<content><sub text="{xml_escape(cue["text"])}" size="{merged["size"]}" '
            f'color="{tint}" text_alpha="1" text_outline_color="{merged["outline_color"]}" '
            f'text_outline_width="{merged["outline_width"]}"></sub></content>'
            f'</subtitle>')
        lines.append(f'draft.select("multi").appendXml({json.dumps(node, ensure_ascii=False)});')
    lines.append("draft.apply();")
    return "\n".join(lines) + "\n"


def lyric_template_selection(cues, template_ref, id_prefix="lyric"):
    """用官方歌词/字幕模板为每个识别句生成一张模板卡。

    模板卡的文字仍由模板引擎渲染，输入槽是 ``<content><sub>``；这里按句生成，
    因此每个模块只需 1 个输入槽（与检索到的可用模板一致）。
    """
    require(cues, "没有可用于生成模板卡的歌词句")
    lines = []
    for index, cue in enumerate(cues, 1):
        node = (
            f'<text id="{id_prefix}_{index:02d}">'
            f'<time material_start="0" start="{cue["start_ms"]}" '
            f'duration="{max(1, cue["end_ms"] - cue["start_ms"])}"></time>'
            f'<template ref="{template_ref}"></template>'
            f'<content><sub text="{xml_escape(cue["text"])}"></sub></content>'
            f'</text>')
        lines.append(f'draft.select("multi").appendXml({json.dumps(node, ensure_ascii=False)});')
    lines.append("draft.apply();")
    return "\n".join(lines) + "\n"


def usable_template_assets(assets):
    """从检索结果里挑出资源完整（能读出输入槽）的模板候选。"""
    usable = []
    for asset in assets or []:
        metadata = asset.get("metadata") or {}
        if metadata.get("text_template_slots") and not metadata.get("text_template_slots_error"):
            usable.append(asset)
    return usable


def register_lyric_animation(workspace, resource_id, title=None):
    """把官方"歌词动效"（lyric_animation）模板登记到工作区资源库。

    歌词动效与字幕模板是两类资源：前者没有输入槽定义，也不带 content.json，
    只有 LyricStyle.json。官方 apply 只会为资源库里登记过的 ref 准备资源，
    因此这里按 lyric_animation 类型显式登记，让 apply 走该类路径。
    """
    workspace = Path(workspace).resolve(strict=True)
    path = workspace / "resource_map.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    for entry in entries:
        if entry.get("resource_id") == resource_id:
            return entry.get("asset_id")
    used = 0
    for entry in entries:
        match = re.fullmatch(r"lyric_animation(\d+)", str(entry.get("asset_id")))
        if match:
            used = max(used, int(match.group(1)))
    name = f"lyric_animation{used + 1}"
    entries.append({"asset_id": name, "lyra_resource": f"vimo://{resource_id}",
                    "resource_id": resource_id, "title": title or resource_id,
                    "type": "lyric_animation"})
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return name


def merge_resource_map(workspace, probe):
    """把子工作区检索到的新资源合并回主工作区资源库。"""
    workspace, probe = Path(workspace), Path(probe)
    main_path, probe_path = workspace / "resource_map.json", probe / "resource_map.json"
    main = json.loads(main_path.read_text(encoding="utf-8")) if main_path.is_file() else []
    extra = json.loads(probe_path.read_text(encoding="utf-8")) if probe_path.is_file() else []
    known = {entry.get("resource_id") for entry in main}
    added = [entry for entry in extra if entry.get("resource_id") not in known]
    if added:
        main_path.write_text(json.dumps(main + added, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return added


def search_templates(workspace, keywords, timeout):
    """按多个关键词检索官方模板并去重。

    检索在独立子工作区进行：主工作区 sync 之后已登记草稿自带的歌词模板，
    官方会认为该类型需求已满足，从而抑制新结果返回（实测只回本地资源）。
    检索结果随后合并回主工作区资源库，ref 才能被 Selection 引用。
    """
    workspace = Path(workspace)
    probe = workspace / "resource-search"
    if not probe.exists() or not any(probe.iterdir()):
        draftediting_runtime.blueprint_init(probe)
    seen, unique = set(), []
    for keyword in keywords:
        try:
            result = draftediting_runtime.blueprint_resource_search(
                probe, [{"type": "subtitle_template", "keyword": keyword}], timeout)
        except Exception:  # noqa: BLE001 - 单个关键词失败不影响其余检索
            continue
        for asset in (result["result"].get("result") or {}).get("assets") or []:
            key = asset.get("asset_id")
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(asset)
    merge_resource_map(workspace, probe)
    return unique


def pick_template(assets, ref=None, resource_id=None):
    """从检索结果里挑模板：优先 resource_id，其次 asset_id。"""
    for asset in assets:
        if resource_id and asset.get("resource_id") == resource_id:
            return asset
        if ref and asset.get("asset_id") == ref:
            return asset
    return None


def search_usable_template(workspace, keyword, timeout=300):
    """检索资源完整的官方歌词/字幕模板，返回可直接用作 ref 的候选。"""
    keywords = [part.strip() for part in str(keyword).split(",") if part.strip()] or ["歌词"]
    assets = search_templates(workspace, keywords, timeout)
    usable = usable_template_assets(assets)
    require(usable, f"检索不到资源完整的官方歌词模板（keywords={keywords}）；"
                    f"请用 --template-keyword 换关键词，或用 --template-ref 指定 ref")
    chosen = usable[0]
    return {"asset_id": chosen["asset_id"], "resource_id": chosen.get("resource_id"),
            "title": chosen.get("title"), "source": "search",
            "usable_count": len(usable), "searched": len(assets)}


def template_resource_report(draft_dir):
    """检查歌词模板卡的本地资源是否完整。

    渲染引擎读取模板目录下的 ``content.json``（EffectSDK 的图元树与字幕参数）；
    缺失时 ``InfoStickerManager::addTemplate`` 直接失败，整张模板卡被跳过，
    画面上不会有任何文字——而且是静默的，所以必须在渲染前显式检查。
    """
    folder = Path(draft_dir).resolve(strict=True)
    candidates = sorted((folder / "Timelines").glob("*/draft_content.json"))
    source = (max(candidates, key=lambda path: path.stat().st_mtime_ns)
              if candidates else folder / "draft_content.json")
    timeline = windows_runtime._decrypt_metadata_in_memory(source)
    rows = []
    for node in timeline.get("materials", {}).get("text_templates", []) or []:
        location = node.get("path") or ""
        if not location:
            continue
        base = Path(str(location).replace("/", os.sep))
        rows.append({"resource_id": node.get("resource_id"), "name": node.get("name"),
                     "path": str(base),
                     "content_json": (base / "content.json").is_file()})
    missing = [row for row in rows if not row["content_json"]]
    return {"templates": rows, "missing_content_json": missing,
            "complete": bool(rows) and not missing}


def sync_draft_mirrors(draft_dir):
    """把官方 apply 写入的时间线同步到草稿的所有镜像。

    实测：``blueprint apply`` 只更新 ``Timelines/<id>/draft_content.json``，而根目录的
    ``draft_content.json`` 与 ``template-2.tmp`` 仍是旧内容；渲染读取时优先取根文件，
    因此不同步就会出现"改了草稿但成片没变化"的假象。
    """
    folder = Path(draft_dir).resolve(strict=True)
    timelines = sorted((folder / "Timelines").glob("*/draft_content.json"))
    require(timelines, "草稿缺少 Timelines/<id>/draft_content.json")
    source = max(timelines, key=lambda path: path.stat().st_mtime_ns)
    targets = [folder / "draft_content.json", folder / "template-2.tmp",
               source.parent / "template-2.tmp"]
    written = []
    for target in targets:
        shutil.copyfile(source, target)
        written.append(str(target))
    return {"source": str(source), "written": written}


def official_apply_animation(workspace, ref, draft_root, resource, lyrics, timeout=600,
                             max_rounds=8):
    """套用官方歌词动效，并在结束时**复核**是否真的全部落地。

    实测（读回落地后的草稿确认）：**一次 ``update`` 即作用于整组歌词**——套用一句后
    整组歌词段都带上了动效模板，动效内容落在 ``materials.texts``（含逐词展开）与
    ``lyrics_effects`` 上。因此这里不做"逐句循环"，而是"套用一次 → 重新同步复核 →
    仍有未套用的才补"，并设硬上限；收尾时再同步一次，把仍未套用的句子写入
    ``leftover``，由调用方决定是否失败（避免"静默漏套但仍然报告成功"）。
    """
    wanted = [line for line in lyrics if line]
    applied, failed, rounds = [], [], 0
    for rounds in range(1, max_rounds + 1):
        draftediting_runtime.blueprint_sync(workspace, ref, draft_root)
        xml_text, mapping = lyra_cli.load_workspace_views(workspace)
        pending = lyra_cli.pending_lyric_segments(xml_text, mapping, wanted)
        if not pending:
            break
        _xml_id, seg_id, body = pending[0]
        try:
            lyra_cli.lyrics_animation_update(draft_root, ref, seg_id, resource,
                                             workspace=workspace, timeout=timeout)
            applied.append(body)
        except Exception as error:  # noqa: BLE001 - 记录后跳过该句，避免死循环
            failed.append({"text": body, "error": str(error)[:200]})
            wanted = [line for line in wanted if line != body]
    draftediting_runtime.blueprint_sync(workspace, ref, draft_root)
    xml_text, mapping = lyra_cli.load_workspace_views(workspace)
    leftover = [item[2] for item in lyra_cli.pending_lyric_segments(xml_text, mapping, wanted)]
    return {"applied": applied, "failed": failed, "leftover": leftover, "rounds": rounds,
            "applied_count": len(applied), "failed_count": len(failed),
            "leftover_count": len(leftover)}


def run(draft_dir, out, jypack=None, audio=None, draft_root=None, material_id=None,
        start_ms=0, duration_ms=None, model="small", language="zh", device="cpu",
        compute_type="int8", allow_download=False, tts=False, tone_ref=None, copy_draft=True,
        render=False, bitrate=6_000_000, timeout=600, workspace=None, draft_prefix="headless-run",
        slot_mode="apply", lyric_target="template", template_ref=None,
        template_keyword="歌词,卡拉OK,字幕,手写字幕,发光字幕,逐字歌词", search_timeout=300,
        lyrics_json=None, template_resource_id=None, lyric_animation=None,
        lyrics_engine="local", recognize_mode=None, recognize_seg_id=None,
        recognize_timeout=1800):
    out = Path(out).resolve()
    require(not out.exists(), "--out 必须是不存在的目录")
    out.mkdir(parents=True)
    draft_root = Path(draft_root or windows_runtime.DRAFT_ROOT).resolve()
    require(bool(jypack) ^ bool(audio), "--jypack 与 --audio 必须二选一")
    source_draft = Path(draft_dir).resolve(strict=True)
    report = {"schema": REPORT_SCHEMA, "status": "running", "started_at": time.time(),
              "source_draft": str(source_draft), "out": str(out), "steps": {}}

    def step(name, value):
        report["steps"][name] = value
        report["steps"][name]["at"] = time.time()
        (out / "pipeline-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return value

    # 1. 自动识别（本地 ASR；official 引擎需要工作副本与工作区，延后到第 2 步之后）
    lyrics_dir = out / "01-recognize"
    cues = []
    if lyrics_engine == "official":
        step("recognize", {"status": "deferred", "engine": "official",
                           "reason": "官方识别需要先建立工作副本与 Blueprint 工作区"})
    elif lyrics_json:
        source = Path(lyrics_json).resolve(strict=True)
        payload = json.loads(source.read_text(encoding="utf-8"))
        cues = payload["cues"]
        require(cues, "复用的识别结果没有歌词句")
        lyrics_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, lyrics_dir / "lyrics.json")
        step("recognize", {"status": "reused", "source": str(source), "cue_count": len(cues),
                           "recognizer": payload.get("recognizer")})
    else:
        lyrics = lyrics_generate.run(
            audio=audio, jypack=jypack, draft_dir=None if audio else str(source_draft),
            material_id=material_id, start_ms=start_ms, duration_ms=duration_ms, model=model,
            language=language, device=device, compute_type=compute_type,
            allow_download=allow_download, output_dir=str(lyrics_dir))
        cues = json.loads(Path(lyrics["lyrics_json"]).read_text(encoding="utf-8"))["cues"]
        step("recognize", {"status": "ok", "model": lyrics["model"],
                           "detected_language": lyrics["detected_language"],
                           "cue_count": lyrics["cue_count"], "lyrics_json": lyrics["lyrics_json"],
                           "srt": lyrics["srt"], "official_plan": lyrics["official_plan"]})

    # 2. 工作副本 + Blueprint 工作区
    draft = working_copy(source_draft, draft_root, draft_prefix) if copy_draft else source_draft
    require(str(draft).isascii(), "工作副本路径必须是纯 ASCII；请用 --draft-prefix 指定 ASCII 前缀")
    ref = draftediting_runtime.local_ref(draft.name)
    workspace_path = Path(workspace).resolve() if workspace else draftediting_runtime.default_workspace(
        ascii_name("ws"))
    draftediting_runtime.blueprint_init(workspace_path)
    sync = draftediting_runtime.blueprint_sync(workspace_path, ref, draft_root)
    step("blueprint", {"status": "ok", "draft": str(draft), "ref": ref,
                       "workspace": str(workspace_path),
                       "segment_count": sync["result"]["result"].get("segment_count")})

    # 2b. 官方歌词识别（lyra-cli draft lyrics recognize）
    official_sentences = []
    if lyrics_engine == "official":
        require(not tts, "official 引擎与 --tts 不能同时使用")
        recognized = lyra_cli.lyrics_recognize(
            draft_root, ref, language=language, mode=recognize_mode, seg_id=recognize_seg_id,
            timeout=recognize_timeout, workspace=workspace_path)
        cues = lyra_cli.recognized_cues(recognized)
        official_sentences = [cue["text"] for cue in cues]
        require(cues, "官方识别没有返回任何歌词句")
        lyrics_dir.mkdir(parents=True, exist_ok=True)
        (lyrics_dir / "lyrics.json").write_text(
            json.dumps({"schema": "jianying-lyrics/v1",
                        "recognizer": "lyra-cli draft lyrics recognize",
                        "language": language, "sentences": official_sentences,
                        "cues": cues}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        step("recognize", {"status": "ok", "engine": "official", "language": language,
                           "cue_count": len(cues), "sentences": official_sentences,
                           "lyrics_json": str(lyrics_dir / "lyrics.json")})

    # 2c. official 引擎：直接用官方歌词动效命令落地，随后同步镜像并渲染
    if lyrics_engine == "official":
        resource = lyric_animation or template_resource_id
        require(resource, "official 引擎需要歌词动效资源，例如 "
                          "--lyric-animation vimo://7591420714515844395（浪漫氛围）")
        resource = str(resource)
        if not resource.startswith("vimo://"):
            resource = f"vimo://{resource}"
        animation = official_apply_animation(workspace_path, ref, draft_root, resource,
                                            official_sentences, timeout=timeout)
        require(animation["applied_count"] > 0,
                "官方歌词动效一次都没有落地：applied=0"
                f"（failed={animation['failed_count']}）"
                + (f"；首个失败原因: {animation['failed'][0]['error']}"
                   if animation["failed"] else ""))
        require(not animation["leftover"],
                f"官方歌词动效未全部落地，仍有 {animation['leftover_count']} 句未套用: "
                + ", ".join(animation["leftover"][:5]))
        report["working_draft"] = str(draft)
        step("selection", {"status": "skipped", "reason": "official 引擎不使用 Selection"})
        step("apply", {"status": "ok", "engine": "official", "resource": resource,
                       "executed_count": animation["applied_count"], **animation})
        step("slots", {"status": "skipped", "reason": "official 引擎由官方命令落地动效"})
        if render:
            require(jypack, "渲染需要 --jypack 作为时间线来源")
            step("mirrors", {"status": "ok", **sync_draft_mirrors(draft)})
            import jypack_render  # 延迟导入：渲染链路会编译原生辅助程序
            rendered = jypack_render.render(str(jypack), str(out / "06-render"),
                                            draft_dir=str(draft), bitrate=bitrate)
            step("render", {"status": "ok", "output": rendered["output"],
                            "output_size": rendered["output_size"],
                            "video_duration": rendered["video_duration"]})
        else:
            step("render", {"status": "skipped", "reason": "未启用 --render"})
        report["status"] = "completed"
        report["finished_at"] = time.time()
        (out / "pipeline-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    # 3. 歌词落地目标：官方歌词模板卡，或可渲染的普通字幕卡
    xml_text = (workspace_path / "current_draft.xml").read_text(encoding="utf-8")
    mapping, alignment, cards = {}, None, []
    resources = template_resource_report(draft)
    replacement = None
    if lyric_target == "template":
        if lyric_animation:
            # 歌词动效（lyric_animation）模板：显式登记后按该类型引用。
            name = register_lyric_animation(workspace_path, lyric_animation, lyric_animation)
            replacement = {"asset_id": name, "resource_id": lyric_animation,
                           "title": lyric_animation, "source": "lyric_animation"}
        elif template_ref or template_resource_id:
            # 显式指定也要先检索：apply 只会为检索登记过的 ref 下载模板资源。
            keywords = [part.strip() for part in str(template_keyword).split(",")
                        if part.strip()] or ["歌词"]
            assets = search_templates(workspace_path, keywords, search_timeout)
            asset = pick_template(assets, ref=template_ref, resource_id=template_resource_id)
            require(asset, f"检索结果里没有匹配的模板（ref={template_ref}, "
                           f"resource_id={template_resource_id}）；可用: "
                           f"{[(a.get('asset_id'), a.get('resource_id'), a.get('title')) for a in assets][:14]}")
            replacement = {"asset_id": asset.get("asset_id"),
                           "resource_id": asset.get("resource_id"),
                           "title": asset.get("title"), "source": "explicit",
                           "resource_readable": bool((asset.get("metadata") or {}).get("text_template_slots"))}
        elif not resources["complete"]:
            # 原模板是 lyric_animation 类，无头链路不支持；自动换成资源完整的官方模板。
            replacement = search_usable_template(workspace_path, template_keyword,
                                                 search_timeout)
        if replacement is None:
            cards = card_specs(xml_text)
            mapping, alignment = lyrics_align.align_cards(cards, cues)
            (out / "03-alignment.json").write_text(
                json.dumps(alignment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            step("align", {"status": "ok", "cards": len(cards),
                           "aligned": alignment["aligned_cards"],
                           "skipped": alignment["skipped_cards"],
                           "outside_cues": alignment["outside_cue_indices"],
                           "report": str(out / "03-alignment.json")})
        else:
            step("align", {"status": "skipped", "reason": "改用检索到的可用官方模板逐句生成",
                           "replacement": replacement})
    else:
        step("align", {"status": "skipped", "reason": "字幕模式直接按识别句时间生成字幕"})
    step("template-resources", {"status": "ok" if resources["complete"] else "incomplete",
                                "templates": len(resources["templates"]),
                                "missing": resources["missing_content_json"],
                                "replacement": replacement})

    # 4. Selection（含可选 TTS）
    speech_ref = tone_ref
    if tts and not speech_ref:
        candidates = tone_refs(workspace_path / "resource_map.json")
        require(candidates, "草稿没有可用的 TTS 音色引用；请用 --tone-ref 指定官方音色")
        speech_ref = candidates[0]
    if lyric_target == "template" and replacement:
        # 官方对带 <template> 的歌词卡同样执行"句级字幕不得重叠"校验。
        blocked = existing_subtitle_windows(xml_text)
        fitted = fit_subtitle_cues(cues, blocked)
        require(fitted, "识别句与已有字幕全部冲突，没有可写入的歌词模板卡")
        selection_text = lyric_template_selection(fitted, replacement["asset_id"])
        applied = [cue["id"] for cue in fitted]
        tts_applied = False
        selection_note = {"mode": "replacement-template", "template_ref": replacement["asset_id"],
                          "template_title": replacement.get("title"),
                          "kept": len(fitted), "dropped": len(cues) - len(fitted)}
    elif lyric_target == "template":
        selection_text, applied = build_selection(cards, mapping, alignment, tts=tts,
                                                  speech_ref=speech_ref)
        tts_applied = bool(tts)
        selection_note = None
    else:
        require(not tts, "字幕模式的 TTS 请生成独立配音段；当前实现不追加 <speech>")
        blocked = existing_subtitle_windows(xml_text)
        fitted = fit_subtitle_cues(cues, blocked)
        require(fitted, "识别句与已有字幕全部冲突，没有可写入的歌词字幕")
        draft_style = lyrics_style.extract(draft) if lyric_target == "style" else None
        if lyric_target == "style":
            require(draft_style, "草稿里没有可提取样式的歌词模板（lyric_animation）")
        colors = (draft_style or {}).get("colors")
        selection_text = lyric_subtitle_selection(fitted, colors=colors)
        selection_note = {"blocked_windows": blocked, "kept": len(fitted),
                          "dropped": len(cues) - len(fitted)}
        if draft_style:
            selection_note["lyric_style"] = draft_style
        (out / "03-subtitle-cues.json").write_text(
            json.dumps({"schema": "jianying-lyric-subtitles/v1", **selection_note,
                        "cues": fitted}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        applied = [cue["id"] for cue in fitted]
        tts_applied = False
    selection_path = draftediting_runtime.write_selection(workspace_path, selection_text)
    step("selection", {"status": "ok", "cards": applied, "tts": tts_applied,
                       "lyric_target": lyric_target,
                       "speech_ref": speech_ref if tts_applied else None,
                       "selection": str(selection_path),
                       **({"subtitle_plan": selection_note} if selection_note else {})})

    # 5. 规范化 + 官方 apply
    normalization = normalize_workspace(workspace_path)
    step("normalize", {"status": "ok", "files": normalization})
    apply_result = draftediting_runtime.blueprint_apply(workspace_path, draft, ref, selection_path)
    detail = apply_result["result"]["result"]
    require(detail.get("executed_count", 0) > 0, "官方 apply 没有执行任何命令")
    validation = detail.get("xmldraft_validation") or {}
    require(validation.get("decision") == "pass", "官方 apply 后的草稿校验未通过")
    step("apply", {"status": "ok", "executed_count": detail.get("executed_count"),
                   "planned_count": detail.get("planned_count"),
                   "commands": detail.get("cmd_list"),
                   "validation": validation.get("summary")})

    # 5b. 可选：修正模板槽位分发（官方 apply 会把整串写进共享文本材料）
    if slot_mode == "direct" and lyric_target == "template":
        import lyrics_slot_direct
        rewritten = lyrics_slot_direct.rewrite(draft, workspace_path, cues, mapping)
        step("slot-rewrite", {"status": "ok", "cards": rewritten["cards"],
                              "mirrors": rewritten["mirrors"]})
    elif slot_mode == "direct":
        step("slot-rewrite", {"status": "skipped", "reason": "字幕模式没有模板槽位"})

    # 6. 可选渲染
    if render:
        require(jypack, "渲染需要 --jypack 作为时间线来源")
        # 官方 apply 只写 Timelines 下的时间线，渲染却优先读根文件，必须先同步镜像。
        step("mirrors", {"status": "ok", **sync_draft_mirrors(draft)})
        import jypack_render  # 延迟导入：渲染链路会编译原生辅助程序
        output_dir = out / "06-render"
        result = jypack_render.render(jypack, str(output_dir), draft_dir=str(draft),
                                      bitrate=bitrate, timeout=timeout)
        step("render", {"status": "ok", "output": result["output"],
                        "output_size": result["output_size"],
                        "video_duration": result["video_duration"]})
    else:
        step("render", {"status": "skipped", "reason": "未启用 --render"})

    report["status"] = "completed"
    report["finished_at"] = time.time()
    report["working_draft"] = str(draft)
    (out / "pipeline-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="执行端到端流水线")
    runner.add_argument("--draft", required=True, help="剪映草稿根下的源草稿（含官方歌词模板卡）")
    runner.add_argument("--out", required=True, help="不存在的绝对目录")
    runner.add_argument("--jypack", help="JYPACK 源：用于取音乐轨识别，并作为渲染时间线")
    runner.add_argument("--audio", help="直接音频源（与 --jypack 二选一）")
    runner.add_argument("--draft-root", help="剪映草稿根，默认取本机运行时")
    runner.add_argument("--material-id")
    runner.add_argument("--start-ms", type=int, default=0)
    runner.add_argument("--duration-ms", type=int)
    runner.add_argument("--model", choices=sorted(lyrics_generate.MODELS), default="small")
    runner.add_argument("--language", default="zh")
    runner.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    runner.add_argument("--compute-type", default="int8")
    runner.add_argument("--allow-download", action="store_true")
    runner.add_argument("--tts", action="store_true", help="为对齐后的模板卡追加官方 <speech> 朗读")
    runner.add_argument("--tone-ref", help="官方 TTS 音色引用；省略时取草稿已有音色")
    runner.add_argument("--no-copy", dest="copy_draft", action="store_false",
                        help="直接作用于源草稿（默认复制工作副本）")
    runner.add_argument("--draft-prefix", default="headless-run", help="工作副本名称前缀（须为 ASCII）")
    runner.add_argument("--workspace", help="Blueprint 工作区（须为纯 ASCII 且为空）")
    runner.add_argument("--render", action="store_true", help="应用后调用本机原生引擎渲染")
    runner.add_argument("--slot-mode", choices=("apply", "direct"), default="apply",
                        help="apply：只用官方 apply；direct：apply 后再按槽位改写草稿文本")
    runner.add_argument("--lyric-target", choices=("template", "subtitle", "style"),
                        default="template",
                        help="template：官方歌词模板卡（原模板损坏时自动检索替换）；"
                             "style：用草稿里 lyric_animation 模板的样式生成等效字幕；"
                             "subtitle：普通字幕，可离线使用")
    runner.add_argument("--template-ref", help="直接指定可用的官方模板 ref，跳过检索")
    runner.add_argument("--template-keyword",
                        default="歌词,卡拉OK,字幕,手写字幕,发光字幕,逐字歌词",
                        help="检索官方歌词模板的关键词，逗号分隔（单关键词只返回少量结果）")
    runner.add_argument("--template-resource-id", help="按官方 resource_id 精确选择模板")
    runner.add_argument("--lyric-animation",
                        help="官方歌词动效（lyric_animation）模板的 resource_id，"
                             "例如 7591420714515844395（浪漫氛围）")
    runner.add_argument("--template-search-timeout", type=int, default=300)
    runner.add_argument("--lyrics-json", help="复用已有识别结果，跳过 ASR（只换模板时更快）")
    runner.add_argument("--lyrics-engine", choices=("local", "official"), default="local",
                        help="local：本机 faster-whisper 识别（离线）；"
                             "official：官方 draft lyrics recognize + animation update")
    runner.add_argument("--recognize-mode", choices=("draft", "segment"),
                        help="official 引擎的识别范围；整稿识别会按来源重复识别同一段歌词")
    runner.add_argument("--recognize-seg-id", help="official 引擎在 mode=segment 时的目标段 id")
    runner.add_argument("--recognize-timeout", type=int, default=1800)
    runner.add_argument("--bitrate", type=int, default=6_000_000)
    runner.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    result = run(
        draft_dir=args.draft, out=args.out, jypack=args.jypack, audio=args.audio,
        draft_root=args.draft_root, material_id=args.material_id, start_ms=args.start_ms,
        duration_ms=args.duration_ms, model=args.model, language=args.language,
        device=args.device, compute_type=args.compute_type, allow_download=args.allow_download,
        tts=args.tts, tone_ref=args.tone_ref, copy_draft=args.copy_draft, render=args.render,
        bitrate=args.bitrate, timeout=args.timeout, workspace=args.workspace,
        draft_prefix=args.draft_prefix, slot_mode=args.slot_mode,
        lyric_target=args.lyric_target, template_ref=args.template_ref,
        template_keyword=args.template_keyword, search_timeout=args.template_search_timeout,
        lyrics_json=args.lyrics_json, template_resource_id=args.template_resource_id,
        lyric_animation=args.lyric_animation, lyrics_engine=args.lyrics_engine,
        recognize_mode=args.recognize_mode, recognize_seg_id=args.recognize_seg_id,
        recognize_timeout=args.recognize_timeout)
    print(json.dumps({"status": result["status"], "out": result["out"],
                      "working_draft": result.get("working_draft"),
                      "steps": {name: {key: value for key, value in step.items()
                                       if key not in {"at", "commands", "report", "files"}}
                                for name, step in result["steps"].items()}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print("流水线失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
