#!/usr/bin/env python3
"""用 faster-whisper 从音频或 JYPACK 草稿自动生成带词级时间的歌词。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import jypack_render


SCHEMA = "jianying-auto-lyrics/v1"
PLAN_SCHEMA = "jianying-official-features/v1"
MODELS = {"tiny", "base", "small", "medium", "large-v2", "large-v3", "turbo"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def clean_text(value):
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip()


def direct_mapping(start_ms, duration_ms):
    start = start_ms / 1000
    end = (start_ms + duration_ms) / 1000 if duration_ms else math.inf
    return [{"source_start": start, "source_end": end, "target_start": 0.0,
             "target_end": end - start, "speed": 1.0}]


def jypack_audio_source(source, draft_dir=None, material_id=None):
    timeline_id = jypack_render.package_timeline_id(source)
    live_dir, _, timeline, _ = jypack_render.find_imported_draft(timeline_id, draft_dir)
    timeline = jypack_render.resolve_paths(timeline, live_dir)
    materials = {item.get("id"): item for item in timeline.get("materials", {}).get("audios", [])
                 if isinstance(item, dict) and item.get("id")}
    groups = {}
    for track in timeline.get("tracks", []):
        if track.get("type") != "audio":
            continue
        for segment in track.get("segments", []):
            material = materials.get(segment.get("material_id"))
            if not material or material.get("type") == "text_to_audio":
                continue
            if material_id and material.get("id") != material_id:
                continue
            path = material.get("path")
            target = segment.get("target_timerange", {})
            source_range = segment.get("source_timerange", {})
            target_duration = target.get("duration")
            source_duration = source_range.get("duration")
            if not isinstance(path, str) or not path or not target_duration or not source_duration:
                continue
            row = {
                "material_id": material.get("id"),
                "source_start": source_range.get("start", 0) / 1_000_000,
                "source_end": (source_range.get("start", 0) + source_duration) / 1_000_000,
                "target_start": target.get("start", 0) / 1_000_000,
                "target_end": (target.get("start", 0) + target_duration) / 1_000_000,
                "speed": source_duration / target_duration,
            }
            groups.setdefault(path, []).append(row)
    require(groups, "草稿没有可用于歌词识别的非 TTS 音频片段")
    path, mappings = max(groups.items(), key=lambda item: sum(row["target_end"] - row["target_start"]
                                                              for row in item[1]))
    audio = Path(path)
    require(audio.is_file(), "歌词音频不存在: " + path)
    mappings.sort(key=lambda row: row["target_start"])
    return audio, mappings, {"timeline_id": timeline_id, "imported_draft": str(live_dir)}


def map_time(source_time, mappings):
    for row in mappings:
        if row["source_start"] - 0.001 <= source_time <= row["source_end"] + 0.001:
            value = row["target_start"] + (source_time - row["source_start"]) / row["speed"]
            return min(max(value, row["target_start"]), row["target_end"])
    return None


def transcribe(audio, mappings, model_name="small", language="zh", device="cpu",
               compute_type="int8", allow_download=False):
    require(model_name in MODELS, "不支持的 faster-whisper 模型")
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device=device, compute_type=compute_type,
                         local_files_only=not allow_download)
    clip_start = min(row["source_start"] for row in mappings)
    finite_ends = [row["source_end"] for row in mappings if math.isfinite(row["source_end"])]
    clip_end = max(finite_ends) if finite_ends else None
    clips = f"{clip_start:.3f}" + (f",{clip_end:.3f}" if clip_end is not None else "")
    segments, info = model.transcribe(
        str(audio), language=language, beam_size=5, word_timestamps=True, vad_filter=True,
        condition_on_previous_text=True, clip_timestamps=clips,
        initial_prompt="以下是普通话简体中文歌词，请保持原歌词，不要翻译。")
    cues = []
    for segment in segments:
        words = []
        for word in segment.words or []:
            source_start, source_end = float(word.start), float(word.end)
            target_start, target_end = map_time(source_start, mappings), map_time(source_end, mappings)
            if target_start is None or target_end is None:
                continue
            text = clean_text(word.word)
            if text:
                words.append({"text": text, "start_ms": round(target_start * 1000),
                              "end_ms": max(round(target_end * 1000), round(target_start * 1000) + 1),
                              "confidence": round(float(word.probability), 6)})
        if not words:
            continue
        cue_text = clean_text("".join(item["text"] for item in words))
        if not cue_text:
            continue
        cue = {"id": f"lyric_{len(cues) + 1:04d}", "text": cue_text,
               "start_ms": words[0]["start_ms"], "end_ms": words[-1]["end_ms"], "words": words}
        if cues and cue["start_ms"] < cues[-1]["end_ms"]:
            cue["start_ms"] = cues[-1]["end_ms"]
        if cue["end_ms"] > cue["start_ms"]:
            cues.append(cue)
    require(cues, "faster-whisper 没有在指定音频范围识别到歌词")
    return cues, {"detected_language": info.language,
                  "language_probability": round(float(info.language_probability), 6),
                  "model": model_name, "device": device, "compute_type": compute_type,
                  "clip_start_seconds": clip_start, "clip_end_seconds": clip_end}


def srt_timestamp(milliseconds):
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_outputs(output_dir, result, animation_ref=None):
    output_dir = Path(output_dir)
    require(output_dir.is_absolute() and not output_dir.exists(), "--out 必须是不存在的绝对目录")
    output_dir.mkdir(parents=True)
    (output_dir / "lyrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    srt = []
    for index, cue in enumerate(result["cues"], 1):
        srt.extend([str(index), f'{srt_timestamp(cue["start_ms"])} --> {srt_timestamp(cue["end_ms"])}',
                    cue["text"], ""])
    (output_dir / "lyrics.srt").write_text("\n".join(srt), encoding="utf-8")
    lyrics = []
    for cue in result["cues"]:
        item = {key: cue[key] for key in ("id", "text", "start_ms", "end_ms")}
        if animation_ref:
            item["animation_ref"] = animation_ref
        lyrics.append(item)
    plan = {"schema": PLAN_SCHEMA, "tts": [], "lyrics": lyrics, "templates": []}
    (output_dir / "official-features.plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"lyrics_json": str(output_dir / "lyrics.json"), "srt": str(output_dir / "lyrics.srt"),
            "official_plan": str(output_dir / "official-features.plan.json")}


def run(audio=None, jypack=None, draft_dir=None, material_id=None, start_ms=0, duration_ms=None,
        model="small", language="zh", device="cpu", compute_type="int8", allow_download=False,
        animation_ref=None, output_dir=None):
    require(bool(audio) ^ bool(jypack), "--audio 与 --jypack 必须二选一")
    if jypack:
        source = Path(jypack).resolve(strict=True)
        source_audio, mappings, context = jypack_audio_source(source, draft_dir, material_id)
    else:
        source_audio = Path(audio).resolve(strict=True)
        require(source_audio.is_file(), "--audio 必须是文件")
        mappings, context = direct_mapping(start_ms, duration_ms), {}
    cues, engine = transcribe(source_audio, mappings, model, language, device, compute_type, allow_download)
    result = {"schema": SCHEMA, "source_audio": str(source_audio),
              "source_audio_sha256": digest(source_audio), "mapping": mappings,
              "recognizer": engine, "cue_count": len(cues), "cues": cues, **context}
    outputs = write_outputs(output_dir, result, animation_ref)
    return {"status": "generated", "cue_count": len(cues), **outputs,
            "detected_language": engine["detected_language"], "model": model}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio")
    source.add_argument("--jypack")
    parser.add_argument("--draft-dir")
    parser.add_argument("--material-id")
    parser.add_argument("--start-ms", type=int, default=0)
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument("--model", choices=sorted(MODELS), default="small")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--animation-ref")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    require(args.start_ms >= 0 and (args.duration_ms is None or args.duration_ms > 0),
            "start-ms/duration-ms 无效")
    result = run(args.audio, args.jypack, args.draft_dir, args.material_id,
                 args.start_ms, args.duration_ms, args.model, args.language, args.device,
                 args.compute_type, args.allow_download, args.animation_ref, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError) as error:
        print("歌词自动生成失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
