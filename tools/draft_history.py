#!/usr/bin/env python3
"""草稿快照式撤销/重做（官方 standalone 版不支持 history undo/redo 的替代方案）。

官方 lyra-cli 明确拒绝：

    draft history undo / redo is only available when lyra-cli is embedded
    as a client library; the standalone executable does not support it yet

官方同时把 ``draft blueprint cancel`` 也限制成仅内嵌库可用。因此本项目用**工程文件快照**
在本机实现等价的撤销/重做：每次快照记录工程目录的完整内容，撤销/重做即在快照之间切换。

用法：

    python tools/draft_history.py --ref func-test-xxx --snapshot     # 记录一个还原点
    python tools/draft_history.py --ref func-test-xxx --list         # 查看还原点
    python tools/draft_history.py --ref func-test-xxx --undo         # 回退一步
    python tools/draft_history.py --ref func-test-xxx --redo         # 前进一步
    python tools/draft_history.py --ref func-test-xxx --restore 2    # 直接恢复到第 2 个还原点
    python tools/draft_history.py --ref func-test-xxx --clear        # 清空历史

快照保存在 ``%LOCALAPPDATA%\\Temp\\jianying-draft-history\\<ref>``，不写入草稿目录本身，
因此不会被剪映当成草稿内容。只操作指定的 ``--ref``，不动其他工程。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import windows_runtime  # noqa: E402

DRAFT_ROOT = Path(windows_runtime.DRAFT_ROOT)
HISTORY_ROOT = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
                / "Temp" / "jianying-draft-history")


def draft_dir(ref):
    name = ref.split("://", 1)[-1]
    path = DRAFT_ROOT / name
    if not path.is_dir():
        raise SystemExit(f"草稿不存在: {path}")
    return path


def history_dir(ref):
    path = HISTORY_ROOT / ref.split("://", 1)[-1]
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_state(ref):
    """当前游标状态：按时间顺序的还原点列表 + 当前位置。"""
    state_file = history_dir(ref) / "state.json"
    if state_file.is_file():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"points": [], "index": -1}


def write_state(ref, state):
    (history_dir(ref) / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def copy_tree(source, target):
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    for item in Path(source).rglob("*"):
        if item.is_file():
            relative = item.relative_to(source)
            destination = Path(target) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def snapshot(ref, label=None):
    """把当前工程内容记录为一个还原点。"""
    state = read_state(ref)
    # 在历史中间新建快照时，丢弃"未来"分支。
    for stale in state["points"][state["index"] + 1:]:
        shutil.rmtree(history_dir(ref) / stale, ignore_errors=True)
    state["points"] = state["points"][:state["index"] + 1]
    name = f"{len(state['points']):03d}-{int(time.time())}"
    copy_tree(draft_dir(ref), history_dir(ref) / name)
    state["points"].append(name)
    state["index"] = len(state["points"]) - 1
    write_state(ref, state)
    print(f"已记录还原点 #{state['index']} ({name})"
          + (f" {label}" if label else ""))
    return state


def restore(ref, index, redo_point=True):
    state = read_state(ref)
    if not state["points"]:
        raise SystemExit("还没有任何还原点，先运行 --snapshot")
    if not 0 <= index < len(state["points"]):
        raise SystemExit(f"还原点序号超出范围: {index}")
    current = state["index"]
    if redo_point and current >= 0 and current != index:
        name = f"redo-{int(time.time())}"
        copy_tree(draft_dir(ref), history_dir(ref) / name)
        state["points"].insert(index + 1 if index < current else index, name)
        if index > current:
            index += 1
    copy_tree(history_dir(ref) / state["points"][index], draft_dir(ref))
    state["index"] = index
    write_state(ref, state)
    print(f"已恢复到还原点 #{index}")
    return index


def show_list(ref):
    state = read_state(ref)
    if not state["points"]:
        print("还没有还原点")
        return
    for position, name in enumerate(state["points"]):
        mark = "->" if position == state["index"] else "  "
        print(f"{mark} #{position}  {name}")
    print(f"历史目录: {history_dir(ref)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", required=True, help="草稿引用，如 func-test-1010-183523")
    parser.add_argument("--snapshot", action="store_true", help="记录一个还原点")
    parser.add_argument("--undo", action="store_true", help="回退一步")
    parser.add_argument("--redo", action="store_true", help="前进一步")
    parser.add_argument("--restore", type=int, help="直接恢复到指定还原点序号")
    parser.add_argument("--list", action="store_true", help="列出还原点")
    parser.add_argument("--clear", action="store_true", help="清空该草稿的历史")
    args = parser.parse_args(argv)

    if args.clear:
        shutil.rmtree(HISTORY_ROOT / args.ref.split("://", 1)[-1], ignore_errors=True)
        print("历史已清空")
        return 0
    if args.list:
        show_list(args.ref)
        return 0
    if args.snapshot:
        snapshot(args.ref)
        return 0
    state = read_state(args.ref)
    if args.restore is not None:
        return 0 if restore(args.ref, args.restore) >= 0 else 1
    if args.undo:
        if state["index"] <= 0:
            print("没有更早的还原点可回退")
            return 2
        return 0 if restore(args.ref, state["index"] - 1, redo_point=False) >= 0 else 1
    if args.redo:
        if state["index"] + 1 >= len(state["points"]):
            print("没有更晚的还原点可前进")
            return 2
        return 0 if restore(args.ref, state["index"] + 1, redo_point=False) >= 0 else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
