#!/usr/bin/env python3
"""从已导入剪映的 JYPACK 草稿副本调用本机原生引擎渲染。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOLS = ROOT / "tools"
for folder in (HERE, TOOLS):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import jypack_inspect
import windows_runtime
from windows_native_toolchain import compile_helper


PLACEHOLDER = re.compile(r"##_draftpath_placeholder_[^#]+_##[\\/]")
RESULT_SCHEMA = "jianying-jypack-native-render/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def package_timeline_id(source):
    payload = Path(source).read_bytes()
    decoded, _ = jypack_inspect.decode_container(payload)
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(decoded)) as archive:
        name_map, _ = jypack_inspect.safe_names(archive)
        require("draft_content.json" in name_map, "JYPACK 缺少 draft_content.json")
        timeline, _ = jypack_inspect.decrypt_timeline(archive.read(name_map["draft_content.json"]))
    timeline_id = timeline.get("id")
    require(isinstance(timeline_id, str) and timeline_id, "JYPACK 时间线缺少 id")
    return timeline_id


def timeline_files(folder):
    root = Path(folder)
    direct = root / "draft_content.json"
    if direct.is_file():
        yield direct
    timelines = root / "Timelines"
    if timelines.is_dir():
        yield from timelines.glob("*/draft_content.json")


def read_live_timeline(path):
    before = digest(path)
    timeline = windows_runtime._decrypt_metadata_in_memory(path)
    require(digest(path) == before, "读取期间实时草稿发生变化")
    return timeline, before


def find_imported_draft(timeline_id, explicit=None):
    root = windows_runtime.DRAFT_ROOT.resolve()
    if explicit:
        folders = [Path(explicit).resolve(strict=True)]
        require(folders[0] == root or root in folders[0].parents,
                "--draft-dir 必须位于剪映本地草稿目录")
    else:
        folders = sorted((item for item in root.iterdir() if item.is_dir() and not item.is_symlink()),
                         key=lambda item: item.stat().st_mtime_ns, reverse=True)
    for folder in folders:
        for timeline_file in timeline_files(folder):
            try:
                timeline, cipher_hash = read_live_timeline(timeline_file)
            except (OSError, ValueError, windows_runtime.ApplyError):
                continue
            if timeline.get("id") == timeline_id:
                return folder, timeline_file, timeline, cipher_hash
    raise ValueError("没有找到同一 timeline id 的已导入草稿；请先在剪映中导入该 JYPACK，或使用 --import-if-missing")


def import_package(source, timeline_id, timeout):
    runtime = windows_runtime.validate_runtime()
    executable = Path(runtime["install_dir"]) / "JianyingPro.exe"
    subprocess.Popen([str(executable), "-open-draft-pack=" + str(Path(source).resolve())],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return find_imported_draft(timeline_id)
        except ValueError as error:
            last_error = error
        time.sleep(1)
    raise ValueError("剪映没有在限定时间内完成 JYPACK 导入: " + str(last_error))


def resolve_paths(value, draft_dir):
    root = Path(draft_dir).resolve()
    if isinstance(value, dict):
        return {key: resolve_paths(child, root) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_paths(child, root) for child in value]
    if not isinstance(value, str):
        return value
    resolved = PLACEHOLDER.sub(root.as_posix() + "/", value)
    return resolved


def referenced_local_paths(value):
    result = set()
    if isinstance(value, dict):
        for child in value.values():
            result.update(referenced_local_paths(child))
    elif isinstance(value, list):
        for child in value:
            result.update(referenced_local_paths(child))
    elif isinstance(value, str):
        # JSON 字符串内部的字体路径也需要校验。
        for match in re.findall(r"(?<![A-Za-z])([A-Za-z]:/[^\"\\]+)", value):
            result.add(match)
        if "://" not in value and re.fullmatch(r"[A-Za-z]:/.*", value):
            result.add(value)
    return result


def probe_output(path):
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    require(completed.returncode == 0, "ffprobe 无法读取渲染结果: " + completed.stderr.strip())
    return json.loads(completed.stdout)


def validate_media(probe, timeline_duration, audio_expected):
    streams = probe.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    require(video is not None, "渲染结果缺少视频流")
    expected = timeline_duration / 1_000_000
    video_duration = float(video.get("duration") or probe["format"].get("duration", 0))
    require(abs(video_duration - expected) <= max(0.12, 2 / float(video.get("avg_frame_rate", "30/1").split("/")[0])),
            f"视频时长 {video_duration:.3f}s 与时间线 {expected:.3f}s 不一致")
    if audio_expected:
        require(audio is not None, "渲染结果缺少音频流")
    return video, audio


def render(source, output_dir, draft_dir=None, import_if_missing=False,
           import_timeout=120, width=None, height=None, fps=30.0, bitrate=6_000_000, timeout=600):
    source = Path(source).resolve(strict=True)
    require(source.is_file() and source.suffix.lower() == ".jypack", "--input 必须是 .jypack 文件")
    output_dir = Path(output_dir)
    require(output_dir.is_absolute() and not output_dir.exists(), "--out 必须是不存在的绝对目录")
    require("work" in {part.lower() for part in output_dir.parts}, "--out 必须位于 work 目录下")
    timeline_id = package_timeline_id(source)
    try:
        live = find_imported_draft(timeline_id, draft_dir)
    except ValueError:
        if not import_if_missing or draft_dir:
            raise
        live = import_package(source, timeline_id, import_timeout)
    live_dir, timeline_file, timeline, cipher_hash = live
    runtime = windows_runtime.validate_runtime()
    resolved = resolve_paths(timeline, live_dir)
    duration = resolved.get("duration", 0)
    require(type(duration) is int and duration > 0, "时间线 duration 无效")
    canvas = resolved.get("canvas_config", {})
    render_width = width or canvas.get("width")
    render_height = height or canvas.get("height")
    require(type(render_width) is int and type(render_height) is int and
            16 <= render_width <= 8192 and 16 <= render_height <= 8192,
            "输出宽高必须是 16..8192 的整数")
    require(1 <= fps <= 120 and 100_000 <= bitrate <= 100_000_000 and 5 <= timeout <= 43_200,
            "fps、bitrate 或 timeout 超出安全范围")
    missing = sorted(path for path in referenced_local_paths(resolved)
                     if not Path(path.replace("/", os.sep)).exists())
    require(not missing, "草稿引用的本地资源不存在: " + ", ".join(missing[:5]))

    output_dir.mkdir(parents=True)
    (output_dir / "compiler-tmp").mkdir()
    timeline_path = output_dir / "timeline.json"
    timeline_path.write_text(json.dumps(resolved, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    helper = output_dir / "native-export-helper.exe"
    compile_result, toolchain = compile_helper(HERE / "native_export_windows.cpp", helper,
                                               output_dir / "compiler-tmp")
    (output_dir / "compiler.stdout.log").write_bytes(compile_result.stdout)
    (output_dir / "compiler.stderr.log").write_bytes(compile_result.stderr)
    require(compile_result.returncode == 0, "原生渲染辅助程序编译失败")
    env = dict(os.environ)
    env["JY_VIDEOEDITOR_DIR"] = runtime["install_dir"]
    command = [str(helper), "timeline.json", "render.mp4", str(render_width), str(render_height),
               str(fps), str(bitrate), str(timeout)]
    with (output_dir / "native.stdout.log").open("xb") as stdout, \
            (output_dir / "native.stderr.log").open("xb") as stderr:
        completed = subprocess.run(command, cwd=output_dir, env=env, stdout=stdout, stderr=stderr,
                                   timeout=timeout + 30)
    output = output_dir / "render.mp4"
    require(completed.returncode == 0 and output.is_file() and output.stat().st_size > 0,
            "剪映原生渲染失败；请检查 native.stderr.log")
    stdout_text = (output_dir / "native.stdout.log").read_text(encoding="utf-8", errors="replace")
    require("JY_WINDOWS_NATIVE_EXPORT_DONE" in stdout_text and
            "JY_WINDOWS_NATIVE_RESTORE_DONE" in stdout_text,
            "原生引擎没有报告完整导出与恢复事件")
    require(digest(timeline_file) == cipher_hash, "渲染期间实时草稿发生变化")
    probe = probe_output(output)
    video, audio = validate_media(probe, duration, bool(resolved.get("materials", {}).get("audios")))
    (output_dir / "ffprobe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    result = {
        "schema": RESULT_SCHEMA, "status": "rendered", "source": str(source),
        "source_sha256": digest(source), "timeline_id": timeline_id,
        "imported_draft": str(live_dir), "imported_draft_written": False,
        "runtime_profile": runtime["runtime_profile"], "output": str(output),
        "output_sha256": digest(output), "output_size": output.stat().st_size,
        "width": video.get("width"), "height": video.get("height"),
        "video_codec": video.get("codec_name"), "video_duration": float(video.get("duration")),
        "audio_codec": audio.get("codec_name") if audio else None,
        "audio_duration": float(audio.get("duration")) if audio and audio.get("duration") else None,
        "toolchain": toolchain, "runtime_token_used": False,
        "renderer": "Jianying native ExportService",
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True, help="不存在的绝对 work 目录")
    parser.add_argument("--draft-dir", help="可选：已经导入该 JYPACK 的草稿目录")
    parser.add_argument("--import-if-missing", action="store_true")
    parser.add_argument("--import-timeout", type=int, default=120)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--bitrate", type=int, default=6_000_000)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    result = render(args.input, args.out, args.draft_dir, args.import_if_missing,
                    args.import_timeout, args.width, args.height, args.fps, args.bitrate, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("JYPACK 原生渲染失败: " + str(error), file=sys.stderr)
        raise SystemExit(1)
