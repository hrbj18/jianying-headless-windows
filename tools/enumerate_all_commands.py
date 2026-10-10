"""枚举 lyra-cli 全部命令的参数，产出数据驱动封装的能力清单。

从 ``work/`` 收编入库（``work/`` 是运行时产物目录，不入版本库）。运行时会**真实调用**
官方 ``<path> --help``，因此需要本机装好剪映与官方 VMSDK（只读探测，不修改草稿）。

产出同一份 payload 的两处副本：

- ``engine/lyra_commands.json``  —— ``engine/lyra_commands.py`` 读取的权威清单；
- ``work/lyra-capabilities.json`` —— 本地证据副本（便于比对与回溯）。

清单结构::

    {"generated_from": "lyra-cli <path> --help", "count": 152,
     "commands": [{"path": ["draft", "video", "speed"],
                   "options": ["--ref", "--seg-id", ...],
                   "summary": "...", "help_state": "ok"}]}

``help_state`` 非 ``ok``（``__TIMEOUT__`` / ``empty``）的命令没有取到参数表，封装时按
官方原样透传、不做白名单校验，避免把官方新参数挡在门外。
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

TREE = {
    "draft project": ["create", "list", "focus", "delete", "rename", "info"],
    "draft cover": ["set", "clear"],
    "draft extract": ["summary", "structure", "segments"],
    "draft template": ["add", "publish", "render", "slots", "replace"],
    "draft algo": ["query", "wait", "quality-enhance", "upscale-resolution",
                   "ai-frame-interpolation", "ai-matting", "ai-transition", "custom-matting",
                   "chroma-color-matting", "video-tracking", "sound-separation",
                   "loudness-normalize", "denoise", "voice-enhance", "video-stabilize",
                   "tts", "subtitle-recognize", "text-add-tone", "music-beats",
                   "material-understand", "subtitle-keywords"],
    "draft video": ["crop", "speed", "stabilize", "scale", "rotate", "translate", "alpha",
                    "flip", "layer", "volume", "freeze", "add", "remove", "transition",
                    "filter", "effect", "mask", "animation", "beat", "audio-effect", "color",
                    "adjust", "background", "matting-stroke", "mix-mode", "face-beauty",
                    "extract-frames", "extract-music"],
    "draft sticker": ["add", "remove", "update"],
    "draft text": ["translate", "content", "effect", "wrap-width", "add", "remove",
                   "animation", "style"],
    "draft audio": ["volume", "fade", "speed", "add", "remove"],
    "draft segment": ["remove", "split", "duplicate", "move", "update", "info"],
    "draft timeline": ["info", "duration"],
    "draft compound-clip": ["create", "dissolve"],
    "draft filter": ["add", "remove", "update"],
    "draft effect": ["add", "remove", "generate"],
    "draft adjust": ["add", "remove", "update"],
    "draft subtitle": ["add", "template", "remove", "recognize"],
    "draft lyrics": ["add", "animation", "remove", "recognize"],
    "draft keyframe": ["add", "update", "remove", "curve"],
    "draft config": ["show", "set"],
    "draft blueprint": ["init", "sync", "apply", "resource"],
    "material": ["search", "download", "query", "topic", "recommend", "similar", "motiongraph"],
    "media": ["aigc", "transcode-image", "crop-image", "resize-image", "compress",
              "trim-video", "trim-audio", "change-video-speed", "change-audio-speed",
              "rotate", "extract-frames", "extract-audio", "probe", "loudness",
              "measure-box", "beats", "object-matting-track", "asr", "vad", "feature",
              "translate", "understand"],
    "lint": ["command", "media", "algorithm-effect", "draft", "trace"],
}

runtime = windows_runtime.validate_runtime()
install = Path(runtime["install_dir"])
dr.find_official_parent(install)
dr.ensure_packaged_bun(install)
ws = Path(os.environ["LOCALAPPDATA"]) / "Temp" / "jianying-draftediting" / "help-probe"
ws.mkdir(parents=True, exist_ok=True)
out_dir = ROOT / "work" / "lyra-help"
out_dir.mkdir(parents=True, exist_ok=True)


def probe(args):
    result_path = out_dir / f"cap-{'_'.join(args)}.json"
    result_path.unlink(missing_ok=True)
    request = {
        "installDir": str(install), "args": list(args) + ["--help"], "cwd": str(ws),
        "env": {"LYRA_CLI_ROOT_WORKSPACE": str(ws),
                "CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE": str(ws)},
        "timeoutMs": 60000, "readOnlyPaths": [str(ws)], "readWritePaths": [str(ws)],
    }
    scratch = Path(tempfile.mkdtemp(prefix="cap-"))
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
                       errors="replace", timeout=90)
    except subprocess.TimeoutExpired:
        return "__TIMEOUT__", ""
    if not result_path.is_file():
        return "", ""
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
            return "ok", text
    return "", ""


commands = []
for domain, actions in TREE.items():
    domain_parts = domain.split()
    for action in actions:
        path = domain_parts + [action]
        state, text = probe(path)
        options, summary = [], ""
        if state == "ok":
            summary = text.splitlines()[0].strip() if text.splitlines() else ""
            block = text.split("OPTIONS:", 1)[-1]
            block = re.split(r"\nEXAMPLES|\nNOTES|\nLEARN MORE|\nACTIONS", block)[0]
            seen = set()
            for flag in re.findall(r"(--[a-z][a-z0-9-]*)", block):
                if flag not in seen:
                    seen.add(flag)
                    options.append(flag)
        commands.append({"path": path, "options": options, "summary": summary[:160],
                         "help_state": state or "empty"})
        print(f"{' '.join(path):44s} {state or 'empty':8s} {len(options):2d} options", flush=True)

payload = {"generated_from": "lyra-cli <path> --help", "count": len(commands),
           "commands": commands}
serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
for target in (ROOT / "engine" / "lyra_commands.json",
               ROOT / "work" / "lyra-capabilities.json"):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding="utf-8")
ok = sum(1 for item in commands if item["help_state"] == "ok")
print(f"\n合计 {len(commands)} 条命令，成功取到参数 {ok} 条")
print("已写入 engine/lyra_commands.json 与 work/lyra-capabilities.json")
