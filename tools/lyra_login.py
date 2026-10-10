#!/usr/bin/env python3
"""官方 lyra-cli 账号登录（分步链接授权）。

用法：

    python tools/lyra_login.py --status     # 只查当前登录态
    python tools/lyra_login.py             # 发起授权并等待用户完成（默认 5 分钟）
    python tools/lyra_login.py --wait 600  # 自定义等待秒数

脚本会真实调用官方分步登录：先取得 ``login_url``，把链接交给用户打开并授权，
然后轮询官方收尾命令直到登录成功。整个过程只通过剪映官方 VMSDK 沙箱执行，
不做任何模拟。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "tools"))
import draftediting_runtime as dr  # noqa: E402
import functional_test as ft  # noqa: E402


def workspace():
    """ASCII 工作区：官方沙箱要求路径可编码为 ASCII。"""
    path = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "jianying-func-test"
    path.mkdir(parents=True, exist_ok=True)
    return path


def call(cli, args, ws):
    return cli(args, cwd=str(ws), read_write=[str(ws)])


def show_status(cli, ws):
    for args in (["auth", "status"], ["auth", "me"]):
        outcome = call(cli, args, ws)
        print(f"$ lyra-cli {' '.join(args)} -> {outcome.state} (exit {outcome.exit_code})")
        print(outcome.stdout.strip() or outcome.message[:200] or "(无输出)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="只查看当前登录态")
    parser.add_argument("--wait", type=int, default=300, help="等待用户授权的秒数（默认 300）")
    parser.add_argument("--timeout", type=int, default=180, help="单次官方命令超时秒数")
    args = parser.parse_args(argv)

    cli = ft.OfficialCli(timeout=args.timeout)
    ws = workspace()

    if args.status:
        return show_status(cli, ws)

    start = call(cli, ["auth", "login", "--link-url", "--no-wait"], ws)
    if not start.ok:
        print("发起登录失败:", start.state, start.message[:300], file=sys.stderr)
        return 1
    body = json.loads(start.stdout)
    result = body.get("result") or {}
    login_url = result.get("login_url")
    device_code = result.get("device_code")
    user_code = result.get("user_code")
    handoff = result.get("session_handoff")
    if not (login_url and device_code and user_code):
        print("官方未返回完整登录参数:", json.dumps(result, ensure_ascii=False)[:400],
              file=sys.stderr)
        return 1

    print("请在浏览器打开下面的授权链接，登录剪映账号并确认 CLI 授权：")
    print()
    print("  " + login_url)
    print()
    print(f"有效期约 {result.get('expires_in', '?')} 秒；脚本会一直轮询直到授权完成。")

    complete_args = ["auth", "login", "--device-code", device_code,
                     "--user-code", user_code]
    if handoff:
        complete_args += ["--session-handoff", handoff]

    deadline = time.monotonic() + max(args.wait, 30)
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        outcome = call(cli, complete_args, ws)
        if outcome.ok:
            print(f"\n登录成功（第 {attempt} 次轮询）：")
            print(outcome.stdout.strip()[:600])
            return show_status(cli, ws) or 0
        message = outcome.message or outcome.stderr or ""
        if "not ready" not in message and "pending" not in message:
            print("非等待类错误:", outcome.state, message[:300], file=sys.stderr)
            return 1
        if attempt % 5 == 0:
            print(f"  仍在等待授权…（第 {attempt} 次，剩余 "
                  f"{int(deadline - time.monotonic())} 秒）", flush=True)
        time.sleep(3)

    print("等待超时，链接已失效；请重新运行本脚本获取新链接。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
