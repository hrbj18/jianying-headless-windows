#!/usr/bin/env python3
"""把 JYPACK 检查结果与原生渲染结果汇总成一份可复核的 markdown 报告。

配套用法（先检查，再渲染，最后出报告）：

    python engine/jypack_inspect.py --input <sample.jypack> --out <abs>/inspect.json
    python engine/jypack_render.py  --input <sample.jypack> --out <abs>/render --import-if-missing
    python tools/jypack_report.py   --inspect <abs>/inspect.json --render <abs>/render \\
                                    --out <abs>/REPORT.md

报告包含：容器与 CRC 完整性、模板要素清单、包内 TTS 配音、歌词、渲染产物规格、
声轨实测与抽帧清单。渲染目录里若有 ``check-*.png`` 抽帧会自动登记。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

try:
    import audioop  # Python <= 3.12
except ModuleNotFoundError:  # Python 3.13+ 移除了 audioop
    audioop = None


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def audio_stats(path):
    """读取 16bit PCM wav 的峰值/RMS 与分段 RMS，用于确认声轨非静音。"""
    path = Path(path)
    if not path.is_file() or audioop is None:
        return {}
    with wave.open(str(path), "rb") as handle:
        width, rate, channels = handle.getsampwidth(), handle.getframerate(), handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
        segments = []
        step = rate * 5
        for start in range(0, min(handle.getnframes(), step * 7), step):
            chunk = frames[start * channels * width:(start + step) * channels * width]
            segments.append((start // rate, audioop.rms(chunk, width)))
        return {"seconds": round(handle.getnframes() / rate, 2),
                "peak": audioop.max(frames, width), "rms": audioop.rms(frames, width),
                "segments": segments}


def build_report(inspect, render_result, render_dir, audio=None):
    timeline = inspect.get("timeline") or {}
    container = inspect.get("container") or {}
    tts = inspect.get("tts") or {}
    lyrics = inspect.get("lyrics") or {}
    integrity = inspect.get("path_integrity") or {}
    source = inspect.get("source") or {}
    render_dir = Path(render_dir)

    lines = ["# 剪映模板包全功能检查与成片报告", ""]
    if source:
        lines += [f"- 模板包：`{Path(str(source.get('path', ''))).name}`"
                  f"（{int(source.get('size') or 0):,} 字节）",
                  f"- sha256：`{source.get('sha256')}`", ""]

    lines += ["## 1. 容器与完整性", "", "| 项目 | 结果 |", "| --- | --- |",
              f"| JY/ZIP 条目数 | {container.get('entry_count')} |",
              f"| 解包体积 | {int(container.get('unpacked_size') or 0):,} 字节 |",
              f"| 全部条目 CRC 校验 | {'通过' if container.get('crc_valid') else '失败'} |",
              f"| 时间线解密 | {'成功' if container.get('timeline_encrypted') else '—'} |",
              f"| 占位路径引用 | {integrity.get('placeholder_reference_count')} 处，缺失 "
              f"{integrity.get('missing_reference_count')} 处 |", ""]

    lines += ["## 2. 模板要素", "",
              f"- 时长 **{timeline.get('duration_seconds')} 秒**，轨道 "
              f"**{timeline.get('track_count')}** 条", "", "| 素材类型 | 数量 |", "| --- | --- |"]
    for kind, count in (timeline.get("material_counts") or {}).items():
        lines.append(f"| {kind} | {count} |")
    lines.append("")

    if tts.get("detected"):
        lines += ["## 3. 包内配音", "",
                  f"- {tts.get('count')} 段配音，音频随包携带且可解码："
                  f"{'是' if tts.get('all_audio_present') else '否'}",
                  f"- 音色：`{', '.join(tts.get('speakers') or [])}`", ""]
        for item in (tts.get("items") or [])[:8]:
            text = (item.get("text") or "").replace("\n", " ")
            lines.append(f"  - `{item.get('detected_format')}` {item.get('sample_rate')}Hz "
                         f"{item.get('channels')}ch — “{text}”")
        lines.append("")
    if lyrics.get("detected"):
        lines += ["## 4. 歌词", "",
                  f"- 逐字歌词素材 {lyrics.get('material_count')} 个，文字模板 "
                  f"{lyrics.get('template_count')} 个",
                  f"- 模板资源 id：`{', '.join(lyrics.get('template_resource_ids') or [])}`",
                  f"- 识别任务 {len(lyrics.get('recognition_tasks') or [])} 个", ""]

    if render_result:
        lines += ["## 5. 成片渲染", "", "| 项目 | 结果 |", "| --- | --- |",
                  f"| 状态 | {render_result.get('status')} |",
                  f"| 渲染器 | {render_result.get('renderer')} |",
                  f"| 时间线 id | `{render_result.get('timeline_id')}` |",
                  f"| 分辨率 | {render_result.get('width')}×{render_result.get('height')} |",
                  f"| 编码 | {render_result.get('video_codec')} + "
                  f"{render_result.get('audio_codec')} |",
                  f"| 时长 | 视频 {render_result.get('video_duration')}s / 音频 "
                  f"{round(float(render_result.get('audio_duration') or 0), 3)}s |",
                  f"| 文件大小 | {int(render_result.get('output_size') or 0):,} 字节 |",
                  f"| sha256 | `{render_result.get('output_sha256')}` |",
                  f"| 使用 Agent Runtime token | "
                  f"{render_result.get('runtime_token_used')} |", ""]
        if render_result.get("imported_draft"):
            lines += [f"- 导入草稿：`{Path(str(render_result['imported_draft'])).name}`"
                      f"（只读加载：{render_result.get('imported_draft_written')}）", ""]

    if audio:
        lines += ["### 声轨实测", "",
                  f"- 峰值 {audio['peak']} / 32767，整体 RMS {audio['rms']}",
                  f"- 时长 {audio['seconds']} 秒",
                  "- 分段 RMS：" + "，".join(f"{start}s={rms}" for start, rms in audio["segments"]),
                  ""]

    shots = sorted(path.name for path in render_dir.glob("check-*.png"))
    if shots:
        lines += ["## 6. 画面抽帧", "", "| 时间点 | 文件 |", "| --- | --- |"]
        for name in shots:
            lines.append(f"| {name.replace('check-', '').replace('.png', '')} | `{name}` |")
        lines.append("")

    lines += ["## 7. 结论", "",
              "- 容器、路径与素材完整性见第 1 节；有缺失引用时会列在检查报告的 "
              "`path_integrity` 字段里。",
              "- 成片由剪映原生 ExportService 渲染；`runtime_token_used` 为 false 时"
              "表示不需要官方 Agent Runtime 令牌。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inspect", required=True, help="jypack_inspect.py 产出的报告 JSON")
    parser.add_argument("--render", help="jypack_render.py 的输出目录（含 result.json）")
    parser.add_argument("--audio", help="用于声轨实测的 wav（可选）")
    parser.add_argument("--out", required=True, help="输出的 markdown 报告路径")
    args = parser.parse_args(argv)

    inspect = load(args.inspect)
    render_result = None
    render_dir = Path(args.render) if args.render else Path(args.inspect).parent
    if args.render and (Path(args.render) / "result.json").is_file():
        render_result = load(Path(args.render) / "result.json")
    audio = audio_stats(args.audio) if args.audio else {}

    text = build_report(inspect, render_result, render_dir, audio)
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print("报告:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
