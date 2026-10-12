#!/usr/bin/env python3
"""从官方 lyra-cli 二进制里挖掘命令的真实参数约束。

官方 help 只列出参数名，不写清取值域、互斥关系和必填组合。这些约束往往只存在于
CLI 二进制的字符串里（例如 ``--tracker-type`` 只接受 ``1/motion`` 与 ``2/surface``、
``--wait false`` 才能避开崩溃路径、``template://`` 资源方案前缀等）。本工具把
"挖字符串"这一步固化成可复现的流程，用于定位"参数怎么传才对"。

用法：

    # 扫描本机已安装的 lyra-cli.exe，输出内置关注组的命中情况
    python tools/mine_cli_strings.py

    # 指定二进制，或自定义关注词（可重复）
    python tools/mine_cli_strings.py --exe <path> --pattern task_id --pattern segment_filter

    # 对比两个版本（例如剪映 11.5 与 11.6），确认能力是否变化
    python tools/mine_cli_strings.py --compare <other-lyra-cli.exe>

    # 机器可读输出
    python tools/mine_cli_strings.py --json --out work/cli-strings.json

命中结果会给出命中次数与上下文片段，便于判断某字符串是"命令定义"还是"错误文案"。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

# 默认关注组：都是排查过程中真正决定"参数怎么传"的字符串。
DEFAULT_GROUPS = {
    "任务与轮询": ["task_id", "query_command", "wait_command", "output-track-data",
                   "poll-interval", "tracking-time-range", "invalid task id"],
    "段类型": ["segment_filter", "segment_video_effect", "segment_picture_adjust",
               "segment_sticker", "segment_image_sticker", "property=filter",
               "property=effect"],
    "资源方案": ["vimo://", "template://", "local:///", "expects template://",
                 "supports vimo only"],
    "素材检索与下载": ["material download", "material query", "material topic",
                       "resource-dir", "resource_pool", "unsupported material type",
                       "non-empty template id"],
    "模板": ["template add", "unzip failed", "template.json", "template publish",
             "template slot", "--template-seg-id"],
    "未实现与内嵌库限制": ["not implemented yet", "kCommonNotImplemented",
                           "embedded as a client library"],
    "崩溃相关": ["tracker-type", "--tracker-type", "tracker_type", "wait expects true or",
                 "MotionGraph", "Lumi", "invalid_client_source"],
}


def candidate_executables():
    """按版本从新到旧列出本机剪映安装目录里的 lyra-cli.exe。"""
    apps = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "JianyingPro/Apps"
    if not apps.is_dir():
        return []
    found = [folder / "lyra-cli.exe" for folder in apps.iterdir()
             if folder.is_dir() and (folder / "lyra-cli.exe").is_file()]
    return sorted(found, key=lambda path: path.parent.name, reverse=True)


def scan(path, patterns):
    """在二进制里统计每个关注词的命中次数并截取上下文。"""
    payload = Path(path).read_bytes().decode("latin-1")
    report = {}
    for pattern in patterns:
        count = payload.count(pattern)
        if not count:
            report[pattern] = {"count": 0, "samples": []}
            continue
        samples, start = [], 0
        while len(samples) < 3:
            index = payload.find(pattern, start)
            if index < 0:
                break
            context = re.sub(r"[\x00-\x1f]+", " ",
                             payload[max(0, index - 70):index + 70])
            samples.append(context.encode("ascii", "replace").decode("ascii").strip())
            start = index + len(pattern)
        report[pattern] = {"count": count, "samples": samples}
    return report


def print_report(title, path, report, groups):
    print("=" * 30, title)
    print("exe:", path)
    grouped = {}
    for group, patterns in groups.items():
        grouped[group] = {pattern: report[pattern] for pattern in patterns
                          if report.get(pattern, {}).get("count")}
    for group, hits in grouped.items():
        if not hits:
            continue
        print(f"-- {group}")
        for pattern, info in hits.items():
            print(f"   {pattern:34} x{info['count']:<4} {info['samples'][0][:110]}")
    others = {pattern: info for pattern, info in report.items()
              if info["count"] and pattern not in
              {p for patterns in groups.values() for p in patterns}}
    for pattern, info in others.items():
        print(f"   {pattern:34} x{info['count']:<4} {info['samples'][0][:110]}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exe", help="lyra-cli 可执行文件路径（默认按版本自动发现）")
    parser.add_argument("--pattern", action="append", default=[],
                        help="自定义关注词，可重复；给了它就不再使用内置关注组")
    parser.add_argument("--compare", help="与另一个版本对比命中差异")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", help="把 JSON 结果写入该文件")
    args = parser.parse_args(argv)

    exe = Path(args.exe) if args.exe else next(iter(candidate_executables()), None)
    if not exe or not Path(exe).is_file():
        parser.error("找不到 lyra-cli.exe；请用 --exe 指定")
    exe = Path(exe)

    if args.pattern:
        groups = {"自定义": list(dict.fromkeys(args.pattern))}
    else:
        groups = DEFAULT_GROUPS
    patterns = [pattern for patterns in groups.values() for pattern in patterns]

    report = scan(exe, patterns)
    result = {"exe": str(exe), "groups": groups, "report": report}
    if args.compare:
        other = Path(args.compare)
        if not other.is_file():
            parser.error(f"对比目标不存在: {other}")
        result["compare"] = {"exe": str(other), "report": scan(other, patterns)}

    if args.json or args.out:
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8", newline="\n")
            print("JSON:", args.out)
        if args.json:
            print(text.encode("ascii", "replace").decode("ascii"))
        return 0

    print_report("lyra-cli 字符串约束", exe, report, groups)
    if "compare" in result:
        print()
        print_report("对比版本", result["compare"]["exe"],
                     result["compare"]["report"], groups)
        changed = [pattern for pattern in patterns
                   if report[pattern]["count"] != result["compare"]["report"][pattern]["count"]]
        print()
        print("命中数有差异的关注词（可用于判断版本是否改变能力）:",
              ", ".join(changed) if changed else "无")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
