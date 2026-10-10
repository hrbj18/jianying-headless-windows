"""导出指定命令的完整参数说明，用于封装时对齐官方契约（避免凭猜参数）。

从 ``work/`` 收编入库（``work/`` 是运行时产物目录，不入版本库）。与
``tools/enumerate_all_commands.py`` 的区别：那个批量枚举全部命令产出机器可读的能力清单，
这个只把少数命令的 ``--help`` 原文解析成人读的 flag 列表打印出来，用于核对 typed 封装的
参数名。运行时会**真实调用**官方 ``lyra-cli <path> --help``。

要核对的命令写在下方 ``TARGETS`` 里，按需增删。
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import draftediting_runtime as dr  # noqa: E402
import windows_runtime  # noqa: E402

TARGETS = [
    ["draft", "video", "add"],
    ["draft", "text", "add"],
    ["draft", "subtitle", "add"],
    ["draft", "audio", "add"],
    ["draft", "algo", "tts"],
    ["draft", "algo", "sound-separation"],
    ["draft", "algo", "upscale-resolution"],
    ["material", "search"],
    ["media", "asr"],
    ["lint", "draft"],
]

runtime = windows_runtime.validate_runtime()
install = Path(runtime["install_dir"])
dr.find_official_parent(install)
dr.ensure_packaged_bun(install)
ws = Path(os.environ["LOCALAPPDATA"]) / "Temp" / "jianying-draftediting" / "help-probe"
ws.mkdir(parents=True, exist_ok=True)


def help_text(args):
    out_dir = ROOT / "work" / "lyra-help"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / f"opt-{'_'.join(args)}.json"
    result_path.unlink(missing_ok=True)
    request = {
        "installDir": str(install), "args": list(args) + ["--help"], "cwd": str(ws),
        "env": {"LYRA_CLI_ROOT_WORKSPACE": str(ws),
                "CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE": str(ws)},
        "timeoutMs": 90000, "readOnlyPaths": [str(ws)], "readWritePaths": [str(ws)],
    }
    scratch = Path(tempfile.mkdtemp(prefix="opt-"))
    env = dict(os.environ)
    for key in ("CUSTOM_AGENT_SANDBOX_OWNER", "CUSTOM_AGENT_PARENT_PROCESS_ID",
                "AGENT_HOST_PARENT_PROCESS_ID", "CUSTOM_AGENT_PROCESS_NAME"):
        env.pop(key, None)
    env.update({
        "AGENT_RUNTIME_ADDON_PATH": str(install / "agent_runtime_addon.node"),
        "CUSTOM_AGENT_NATIVE_ADDON_DIR": str(install),
        "TEMP": str(scratch), "TMP": str(scratch), "TMPDIR": str(scratch),
        "LYRA_CLI_ALLOW_DEV_JIANYING_APP": "1",
        "JY_DRAFTEDITING_INPUT_B64": base64.b64encode(
            json.dumps(request, ensure_ascii=False).encode("utf-8")).decode("ascii"),
        "JY_DRAFTEDITING_RESULT": str(result_path),
    })
    try:
        subprocess.run([str(install / "bun.exe"), "--preload",
                        str(install / "Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs"),
                        str(dr.WORKER)],
                       env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return "__TIMEOUT__"
    if not result_path.is_file():
        return ""
    payload = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))

    def dig(node, key):
        if isinstance(node, dict):
            if key in node:
                yield node[key]
            for value in node.values():
                yield from dig(value, key)
        elif isinstance(node, list):
            for item in node:
                yield from dig(item, key)

    for text in dig(payload, "stdout"):
        if isinstance(text, str) and "OPTIONS" in text:
            return text
    return ""


for target in TARGETS:
    name = " ".join(target)
    text = help_text(target)
    if text == "__TIMEOUT__":
        print(f"===== {name}: 超时")
        continue
    if not text:
        print(f"===== {name}: 无输出")
        continue
    block = text.split("OPTIONS:", 1)[-1]
    block = re.split(r"\nEXAMPLES|\nNOTES|\nLEARN MORE", block)[0]
    flags = re.findall(r"(--[a-z][a-z0-9-]*)", block)
    seen, ordered = set(), []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            ordered.append(flag)
    print(f"===== {name} ({len(ordered)}): {' '.join(ordered)}")
