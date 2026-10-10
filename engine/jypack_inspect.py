#!/usr/bin/env python3
"""只读检查剪映 .jypack，并识别 TTS、歌词与官方模板包能力。"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import wave
import zipfile


JY_SIGNATURES = {
    b"JY\x03\x04": b"PK\x03\x04",
    b"JY\x01\x02": b"PK\x01\x02",
    b"JY\x05\x06": b"PK\x05\x06",
    b"JY\x06\x06": b"PK\x06\x06",
    b"JY\x06\x07": b"PK\x06\x07",
}
PLACEHOLDER = re.compile(r"^##_draftpath_placeholder_[^#]+_##[\\/](.+)$")
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TIMELINE_BYTES = 256 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def decode_container(payload):
    require(len(payload) <= MAX_PACKAGE_BYTES, ".jypack 超过 2 GiB 安全上限")
    counts = {}
    decoded = payload
    for source, target in JY_SIGNATURES.items():
        count = decoded.count(source)
        if count:
            decoded = decoded.replace(source, target)
            counts[source.hex().upper()] = count
    require(decoded.startswith(b"PK\x03\x04"), "文件不是受支持的 JY/ZIP 容器")
    return decoded, counts


def normalized_zip_name(value):
    """兼容剪映包中未设置 UTF-8 flag、但实际用 UTF-8 写入的文件名。"""
    try:
        return value.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def safe_names(archive):
    names = {}
    total = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace("\\", "/"))
        require(not path.is_absolute() and ".." not in path.parts,
                "包内存在不安全路径: " + info.filename)
        require(not info.flag_bits & 0x1, "不支持 ZIP 层加密条目: " + info.filename)
        require((info.external_attr >> 16) & 0o170000 != 0o120000,
                "包内不允许符号链接: " + info.filename)
        total += info.file_size
        require(total <= MAX_PACKAGE_BYTES, "解压后内容超过 2 GiB 安全上限")
        normalized = normalized_zip_name(path.as_posix())
        require(normalized not in names, "包内文件名规范化后重复: " + normalized)
        names[normalized] = info.filename
    return names, total


def strict_json(payload, label):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, label + " 包含重复字段: " + key)
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(
                               ValueError(label + " 包含非有限数值: " + item)))
    except UnicodeError as error:
        raise ValueError(label + " 不是 UTF-8 JSON") from error
    require(isinstance(value, dict), label + " 顶层必须是对象")
    return value


def decrypt_timeline(payload):
    try:
        return strict_json(payload, "draft_content.json"), False
    except (ValueError, json.JSONDecodeError):
        engine_dir = Path(__file__).resolve().parent
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        import windows_runtime
        plain = windows_runtime._crypto("decrypt", payload)
        return strict_json(plain, "解密后的 draft_content.json"), True


def iter_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)
    elif isinstance(value, str):
        yield value


def packaged_path(value):
    match = PLACEHOLDER.match(value)
    if not match:
        return None
    path = PurePosixPath(match.group(1).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return ""
    return path.as_posix()


def audio_probe(archive, name):
    payload = archive.read(name)
    if payload.startswith(b"ID3"):
        result = {"path": name, "detected_format": "mp3", "valid_audio_header": True}
        if shutil.which("ffprobe"):
            completed = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=codec_name,sample_rate,channels", "-of", "json", "pipe:0"],
                input=payload, capture_output=True, timeout=15)
            result["audio_decodable"] = completed.returncode == 0
            if completed.returncode == 0:
                probe = json.loads(completed.stdout.decode("utf-8"))
                stream = (probe.get("streams") or [{}])[0]
                duration = (probe.get("format") or {}).get("duration") or stream.get("duration")
                result.update({
                    "codec": stream.get("codec_name"),
                    "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
                    "channels": stream.get("channels"),
                    "duration_ms": round(float(duration) * 1000) if duration is not None else None,
                })
        return result
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            frames, rate = source.getnframes(), source.getframerate()
            return {
                "path": name,
                "duration_ms": round(frames * 1000 / rate) if rate else None,
                "sample_rate": rate,
                "channels": source.getnchannels(),
            }
    except (EOFError, wave.Error):
        return {"path": name, "detected_format": "unknown", "valid_audio_header": False}


def parsed_text(material):
    content = material.get("content")
    if not isinstance(content, str):
        return ""
    try:
        value = json.loads(content)
    except ValueError:
        return ""
    return value.get("text", "") if isinstance(value, dict) else ""


def inspect_timeline(timeline, archive, name_map):
    names = set(name_map)
    materials = timeline.get("materials", {})
    require(isinstance(materials, dict), "draft_content.json 缺少 materials 对象")
    audios = materials.get("audios", [])
    tts = [item for item in audios if isinstance(item, dict) and item.get("type") == "text_to_audio"]
    tts_items = []
    for item in tts:
        path = packaged_path(item.get("path", ""))
        row = {
            "id": item.get("id"), "text": item.get("name"),
            "tone_type": item.get("tone_type"), "tone_speaker": item.get("tone_speaker"),
            "resource_id": item.get("resource_id"), "audio_path": path,
            "audio_in_package": bool(path and path in names),
        }
        if row["audio_in_package"] and path.lower().endswith(".wav"):
            row.update(audio_probe(archive, name_map[path]))
        tts_items.append(row)

    texts = [item for item in materials.get("texts", []) if isinstance(item, dict)]
    lyric_texts = [item for item in texts if item.get("type") == "lyrics"]
    lyric_templates = [item for item in materials.get("text_templates", [])
                       if isinstance(item, dict) and item.get("type") == "text_template_lyrics"]
    tasks = timeline.get("config", {}).get("lyrics_taskinfo", [])
    task_rows = []
    seen_tasks = set()
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict) or task.get("id") in seen_tasks:
            continue
        seen_tasks.add(task.get("id"))
        try:
            content = json.loads(task.get("content", "{}"))
        except ValueError:
            content = {}
        utterances = content.get("utterances", []) if isinstance(content, dict) else []
        task_rows.append({
            "id": task.get("id"), "language": task.get("language"), "type": task.get("type"),
            "utterance_count": len(utterances),
            "word_count": sum(len(item.get("words", [])) for item in utterances if isinstance(item, dict)),
        })

    package_materials = materials.get("drafts", [])
    package_files = sorted(name for name in names if name.startswith("Resources/draft_templates/"))
    native_blockers = [key for key in ("stickers", "text_templates", "drafts", "transitions",
                                        "common_mask", "video_effects", "audio_effects")
                       if materials.get(key)]
    if any(item.get("animations") for item in materials.get("material_animations", [])
           if isinstance(item, dict)):
        native_blockers.append("material_animations.animations")
    referenced = sorted({path for value in iter_strings(timeline)
                         if (path := packaged_path(value)) is not None})
    invalid_refs = [path for path in referenced if not path]
    missing_refs = [path for path in referenced if path and path not in names]
    return {
        "timeline": {
            "duration_us": timeline.get("duration"),
            "duration_seconds": round(timeline.get("duration", 0) / 1_000_000, 3),
            "track_count": len(timeline.get("tracks", [])),
            "material_counts": {key: len(value) for key, value in sorted(materials.items())
                                if isinstance(value, list) and value},
        },
        "tts": {
            "detected": bool(tts_items), "count": len(tts_items),
            "all_audio_present": bool(tts_items) and all(item["audio_in_package"] for item in tts_items),
            "speakers": sorted({item.get("tone_speaker") for item in tts_items if item.get("tone_speaker")}),
            "items": tts_items,
        },
        "lyrics": {
            "detected": bool(lyric_texts or task_rows), "material_count": len(lyric_texts),
            "texts": [parsed_text(item) for item in lyric_texts],
            "template_count": len(lyric_templates),
            "template_resource_ids": sorted({item.get("resource_id") for item in lyric_templates
                                             if item.get("resource_id")}),
            "recognition_tasks": task_rows,
        },
        "official_template_package": {
            "detected": bool(package_materials or package_files),
            "draft_material_count": len(package_materials) if isinstance(package_materials, list) else 0,
            "resource_file_count": len(package_files),
            "note": ("检测到 template_package 相关资源" if package_materials or package_files else
                     "该包只有歌词文字模板，未包含可验证 template_package 渲染的官方模板包"),
        },
        "render_readiness": {
            "direct_package_export_supported": not native_blockers,
            "direct_package_export_blockers": native_blockers,
            "imported_draft_native_export": "engine/jypack_render.py 可在剪映完成资源解析后导出",
            "official_export_requires": ["官方 Agent Runtime", "JIANYING_AGENT_RUNTIME_TOKEN",
                                         "已注册的当前 draft_ref"],
            "jypack_is_draft_ref": False,
        },
        "path_integrity": {
            "placeholder_reference_count": len(referenced),
            "missing_reference_count": len(missing_refs),
            "missing_references": missing_refs,
            "invalid_references": invalid_refs,
        },
    }


def inspect_jypack(path, decryptor=decrypt_timeline):
    path = Path(path).resolve(strict=True)
    require(path.is_file() and path.suffix.lower() == ".jypack", "输入必须是 .jypack 普通文件")
    payload = path.read_bytes()
    decoded, signatures = decode_container(payload)
    with zipfile.ZipFile(io.BytesIO(decoded)) as archive:
        bad = archive.testzip()
        require(bad is None, "包内 CRC 校验失败: " + str(bad))
        name_map, unpacked_size = safe_names(archive)
        names = set(name_map)
        require("draft_content.json" in names, "包内缺少 draft_content.json")
        info = archive.getinfo("draft_content.json")
        require(info.file_size <= MAX_TIMELINE_BYTES, "draft_content.json 超过 256 MiB 安全上限")
        timeline, encrypted = decryptor(archive.read(info))
        features = inspect_timeline(timeline, archive, name_map)
    return {
        "schema": "jianying-jypack-inspection/v1",
        "source": {"path": str(path), "size": len(payload), "sha256": sha256(payload)},
        "container": {"entry_count": len(names), "unpacked_size": unpacked_size,
                      "crc_valid": True, "jy_signature_counts": signatures,
                      "timeline_encrypted": encrypted},
        **features,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="待检查的 .jypack")
    parser.add_argument("--out", required=True, help="不存在的绝对 JSON 报告路径")
    args = parser.parse_args(argv)
    output = Path(args.out)
    require(output.is_absolute() and not output.exists(), "--out 必须是不存在的绝对路径")
    report = inspect_jypack(args.input)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print("JYPACK 检查失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
