#!/usr/bin/env python3
"""在真实剪映 VMSDK 沙箱中逐条功能测试官方 lyra-cli。

本工具不做任何桩替身：每一条命令都通过剪映自带 VMSDK 沙箱真实执行
``lyra-cli <path> [--flag value ...]``，然后按官方返回的 ``exitCode`` 与 stdout JSON
归类，产出可复核的证据与报告。

三层测试：

1. ``contract``：把 ``engine/lyra_commands.py`` 装出来的 wrapper（白名单、严格模式、
   参数别名）与实时 ``--help`` 逐条比对，确认封装契约与官方一致。
2. ``execute``：按官方 help 里的参数规格自动生成最小可用参数，逐条真实执行，
   把结果归类为 ok / usage / needs_login / api_error / timeout 等。
3. ``workflow``：在一个全新草稿工程上完成真实剪辑链路（建工程 → 导入媒体 →
   视频/文字/音频/贴图 → 关键帧/特效/动画 → 撤销重做 → 结构导出 → 渲染）。

所有写入都限制在 ``work/functional-test/`` 内；用户真实草稿目录只读。
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "tools"))
import draftediting_runtime as dr  # noqa: E402
import lyra_commands  # noqa: E402
import lyra_cli  # noqa: E402
import windows_runtime  # noqa: E402

import enumerate_all_commands as enum_tool  # noqa: E402

EVIDENCE_DIR = ROOT / "work" / "functional-test" / "evidence"
# 官方沙箱要求工作区与草稿都是纯 ASCII 路径；本项目根目录含中文，因此测试根放在
# LOCALAPPDATA 临时目录下，绝不在项目目录里跑官方命令。
WORK = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "jianying-func-test"
# 官方只识别剪映草稿根下的草稿（见 draftediting_runtime.require_draft_root 的实测记录）。
DRAFT_ROOT = Path(windows_runtime.DRAFT_ROOT)
DRAFT_PREFIX = "func-test-"
HELP_CACHE = ROOT / "work" / "lyra-help"
MANIFEST = ROOT / "engine" / "lyra_commands.json"
GLOBAL_FLAGS = {"--help", "--version", "--jq"}

# 官方退出码语义（由真实探测归纳，出现在 classify 里作为兜底）。
EXIT_NEEDS_LOGIN = {5}


@dataclass(frozen=True)
class Outcome:
    """一次真实官方调用的原始结果。"""

    state: str
    exit_code: int | None = None
    err_code: int | None = None
    err_category: str = ""
    message: str = ""
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    detail: str = ""
    automation_exit_code: int | None = None  # lint 用它表达"发现问题"，不是命令失败

    @property
    def ok(self):
        return self.state == "ok"


@dataclass
class OptionSpec:
    """官方 help 里的一个参数定义。"""

    flag: str
    aliases: list = field(default_factory=list)
    type_token: str = ""
    required: bool = False
    choices: list = field(default_factory=list)
    default: str | None = None

    @property
    def takes_value(self):
        return bool(self.type_token)


# --------------------------------------------------------------------------- 真实运行通道

def _read_envelope(result_path):
    """读取官方 worker 的结果文件；尚未写完或不可读时返回 None。"""
    try:
        data = Path(result_path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not data.strip():
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


class OfficialCli:
    """通过剪映官方 VMSDK 沙箱真实执行 lyra-cli。"""

    def __init__(self, timeout=120, scratch_root=None):
        runtime = windows_runtime.validate_runtime()
        self.install = Path(runtime["install_dir"])
        dr.find_official_parent(self.install)
        dr.ensure_packaged_bun(self.install)
        self.timeout = int(timeout)
        self.scratch_root = scratch_root
        self.calls = 0

    def __call__(self, args, cwd, read_write=(), read_only=(), extra_env=None):
        self.calls += 1
        request = {
            "installDir": str(self.install),
            "args": [str(item) for item in args],
            "cwd": str(Path(cwd).resolve()),
            "env": {"LYRA_CLI_ROOT_WORKSPACE": str(Path(cwd).resolve()),
                    "CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE": str(Path(cwd).resolve())},
            "timeoutMs": self.timeout * 1000,
            "readOnlyPaths": [str(Path(p).resolve()) for p in read_only],
            "readWritePaths": [str(Path(p).resolve()) for p in read_write],
        }
        scratch = Path(tempfile.mkdtemp(prefix="lyra-func-", dir=self.scratch_root))
        result_path = scratch / "result.json"
        env = dict(os.environ)
        for key in ("CUSTOM_AGENT_SANDBOX_OWNER", "CUSTOM_AGENT_PARENT_PROCESS_ID",
                    "AGENT_HOST_PARENT_PROCESS_ID", "CUSTOM_AGENT_PROCESS_NAME"):
            env.pop(key, None)
        env.update({
            "AGENT_RUNTIME_ADDON_PATH": str(self.install / "agent_runtime_addon.node"),
            "CUSTOM_AGENT_NATIVE_ADDON_DIR": str(self.install),
            "TEMP": str(scratch), "TMP": str(scratch), "TMPDIR": str(scratch),
            "LYRA_CLI_ALLOW_DEV_JIANYING_APP": "1",
            "JY_DRAFTEDITING_INPUT_B64": base64.b64encode(
                json.dumps(request, ensure_ascii=False).encode("utf-8")).decode("ascii"),
            "JY_DRAFTEDITING_RESULT": str(result_path),
        })
        started = time.monotonic()
        process = None
        try:
            process = subprocess.Popen(
                [str(self.install / "bun.exe"), "--preload",
                 str(self.install /
                     "Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs"),
                 str(dr.WORKER)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # 官方 worker 收尾阶段可能挂住不退出；以结果文件为准，不能干等进程。
            deadline = time.monotonic() + self.timeout + 30
            payload = None
            while True:
                payload = _read_envelope(result_path)
                if payload is not None:
                    break
                if process.poll() is not None:
                    payload = _read_envelope(result_path)
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.4)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
            if payload is None:
                missing = "" if result_path.is_file() else "（未生成结果文件）"
                return Outcome("worker_timeout", message=f"VMSDK worker 超时{missing}",
                               duration_ms=int((time.monotonic() - started) * 1000))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
            shutil.rmtree(scratch, ignore_errors=True)
        return self._interpret(payload, started)

    @staticmethod
    def _interpret(payload, started):
        response = (payload or {}).get("responseMessage") or {}
        result = response.get("result") or {}
        duration = result.get("durationMs") or int((time.monotonic() - started) * 1000)
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        if not response.get("ok"):
            return Outcome("sandbox_rejected", message=json.dumps(
                response, ensure_ascii=False)[:400], duration_ms=duration)
        if result.get("timedOut"):
            return Outcome("timeout", exit_code=result.get("exitCode"),
                           stdout=stdout, stderr=stderr, duration_ms=duration)
        body = {}
        text = stdout.strip()
        if text:
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = {}
        if not isinstance(body, dict):
            body = {}
        exit_code = result.get("exitCode")
        err_code = body.get("err_code")
        base = {"exit_code": exit_code, "err_code": err_code,
                "err_category": str(body.get("err_category") or ""),
                "message": str(body.get("err_msg") or ""),
                "duration_ms": duration, "stdout": stdout, "stderr": stderr}
        if exit_code == 0 and not body:
            return Outcome("unparsed", detail=text[:400], **base)
        if err_code == 0:
            result_body = body.get("result")
            automation = (result_body.get("automation_exit_code")
                          if isinstance(result_body, dict) else None)
            # lint 系列命令用进程退出码表达"发现多少问题"，官方 err_code=0 才算命令成功；
            # 不能因为 exit_code 非 0 就把它当成调用失败。
            if exit_code == 0 or automation is not None:
                return Outcome("ok", automation_exit_code=automation, **base)
        return Outcome(classify(Outcome("", **base)), **base)


LOGIN_HINTS = ("login", "log in", "not logged", "unauthorized", "auth", "credential",
               "token", "sign in", "account")
CONTEXT_HINTS = ("segment", "track", "draft not found", "no draft", "workspace",
                 "not found", "does not exist", "missing")


def classify(outcome):
    """把一次失败按官方语义归类；顺序即优先级。"""
    text = f"{outcome.err_category} {outcome.message}".lower()
    # 官方明确声明"还没实现"或"独立可执行文件不支持"，属于官方的能力边界，不是本封装缺陷。
    if "not implemented yet" in text or "work in progress" in text:
        return "not_implemented"
    if "embedded as a client library" in text:
        return "requires_embedded_library"
    if "model not found" in text:
        return "model_missing"
    if outcome.exit_code in EXIT_NEEDS_LOGIN or any(h in text for h in LOGIN_HINTS):
        return "needs_login"
    # 需要真实前置产物（真实 task id / 模板槽位 / 有效片段目标）才能继续，属于可解释的依赖缺口。
    if any(hint in text for hint in (
            "requires a segment target", "invalid video-tracking task id", "slot not found",
            "requires --target", "requires a fresh --ref", "has type 'segment_",
            "does not support local", "no existing", "requires a non-zero draft canvas",
            "requires different source and target timelines", "requires --deform-seg-id",
            "does not accept", "not a directory", "requires exactly one of",
            "repo root does not look like")):
        return "needs_prerequisite"
    if outcome.err_category == "usage" or outcome.err_code == -100003:
        return "usage"
    if outcome.exit_code == 2:
        return "usage"
    if outcome.exit_code == 0:
        return "api_error"
    if outcome.exit_code == 1:
        # exit 1 是官方业务语义错误（draft not found / already exists / 参数组合不被接受）。
        # 命令本身是可达的，因此保留原文并归入可解释的业务拒绝。
        return "business_error"
    if outcome.exit_code is None:
        return "no_exit_code"
    return f"exit_{outcome.exit_code}"


# --------------------------------------------------------------------------- 官方 help 规格

_OPTION_TYPE_RE = re.compile(
    r"^ {0,12}(?:-[A-Za-z],\s*)?(?P<aliases>--[a-z][a-z0-9-]*(?:,\s*--[a-z][a-z0-9-]*)*)"
    r"(?:\s+(?P<type><[^>]+>|[A-Z][A-Z0-9_]*:[A-Za-z0-9_:{},.\-]+|[A-Z]{2,}))?"
)
_REQUIRED_RE = re.compile(r"\bREQUIRED\b")


def parse_option_specs(help_text):
    """从官方 help 的 OPTIONS 段解析参数规格（类型、必填、候选值）。"""
    specs = []
    for line in enum_tool._section_lines(help_text, {"OPTIONS"}):
        match = _OPTION_TYPE_RE.match(line)
        if not match:
            continue
        aliases = [item.strip() for item in match.group("aliases").split(",")]
        type_token = (match.group("type") or "").strip()
        # 说明文字常以大写词开头（Print / Show / Wait），不能当成类型。
        if type_token and not (type_token.startswith("<") or ":" in type_token
                               or type_token in {"TEXT", "INT", "FLOAT", "BOOL"}):
            type_token = ""
        spec = OptionSpec(flag=aliases[0], aliases=aliases, type_token=type_token,
                          required=bool(_REQUIRED_RE.search(line)))
        if ":" in type_token and "{" in type_token:
            choices = type_token.split("{", 1)[1].rstrip("}")
            spec.choices = [item.strip() for item in choices.split(",") if item.strip()]
        default = re.search(r"\[([^\]]*)\]\s*$", line.strip())
        if default and spec.takes_value:
            spec.default = default.group(1)
        specs.append(spec)
    return specs


def load_help_text(path):
    """优先用已缓存的真实 help；缺失时返回 None（调用方再决定是否真实探测）。"""
    cached = HELP_CACHE / f"dynamic-{enum_tool._safe_name(list(path))}.json"
    if not cached.is_file():
        return None
    try:
        payload = json.loads(cached.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    result = enum_tool.interpret_probe_payload(payload)
    return result.text if result.state == "ok" else None


# --------------------------------------------------------------------------- 参数取值

# 按 flag 语义给真实值，而不是随便填占位文本。键是去掉前缀的 flag 名。
MEDIA_INPUT_FLAGS = {
    "--input", "--path", "--resource", "--source", "--from-path", "--input-path",
    "--video", "--audio", "--image", "--input-video", "--input-audio", "--input-image",
}
DIR_FLAGS = {"--output-dir", "--dir", "--resource-dir", "--workspace", "--input-dir",
             "--out-dir", "--cache-dir"}
FILE_OUTPUT_FLAGS = {"--output", "--output-path", "--out", "--output-file"}
SEGMENT_FLAGS = {"--seg-id", "--segment-id", "--source-seg-id",
                 "--seg-ids", "--segments", "--after-seg-id", "--template-seg-id",
                 "--before-seg-id", "--deform-seg-id"}
# 不同域的命令只接受对应类型的片段：text 命令给 text 段 id，audio 命令给 audio 段 id，
# 否则官方直接回 "target ... has type 'segment_video'"。
SEGMENT_TYPE_BY_DOMAIN = {
    "text": "text", "subtitle": "text", "lyrics": "text", "text-template": "text",
    "audio": "audio",
    "sticker": "sticker",
}
INDEX_FLAGS = {"--target-track", "--seg-index", "--index", "--track-index"}
# 官方定位目标的方式互斥：--seg-id 与 --seg-type/--target-track/--seg-index/--time-window
# 不能同时出现（ValidationError: cannot combine --seg-id with ...）。有真实 seg id 时只传它。
LOCATOR_FLAGS = {"--seg-type", "--target-track", "--seg-index", "--time-window",
                 "--track-index", "--index"}
DURATION_FLAGS = {"--start", "--duration", "--end", "--start-time", "--end-time",
                  "--from", "--to", "--source-from"}
TEXT_VALUE_FLAGS = {"--text", "--content", "--prompt", "--name", "--title", "--label",
                    "--language", "--lang", "--speaker", "--mode", "--op",
                    "--animated-property", "--keyframe-type", "--curve-type", "--seg-type",
                    "--speed", "--source-timeline", "--template-id",
                    "--resource-id", "--task-id"}
# 主动补充的核心参数：官方常把实际必填写得比 REQUIRED 更宽松，缺了会只回 usage。
PROACTIVE_FLAGS = MEDIA_INPUT_FLAGS | DIR_FLAGS | FILE_OUTPUT_FLAGS | SEGMENT_FLAGS | {
    "--ref", "--resource", "--type", "--text", "--content", "--prompt", "--language",
    "--target", "--format", "--params", "--params-json",
} | INDEX_FLAGS | DURATION_FLAGS | TEXT_VALUE_FLAGS

# 少数命令要求"至少给一个有效字段"，官方 help 无法表达这种约束，这里按命令补一个安全值。
PATH_EXTRA_ARGS = {
    ("draft", "adjust", "add"): {"--brightness": "0.1"},
    ("draft", "deform", "apply"): {"--scale": "1"},
}
# 个别命令的参数在别的命令里语义不同，必须按命令排除（否则官方直接报组合错误）。
PATH_SKIP_FLAGS = {
    ("draft", "blueprint", "resource"): {"--title"},
}

# 这些命令的 --seg-id 是可选的"作用域"参数，主动传入反而改变语义（如 extract 只导某段）。
OPTIONAL_SEGMENT_PATHS = {("draft", "extract", "summary"), ("draft", "extract", "structure"),
                          ("draft", "extract", "segments")}

# --type 在官方 help 里常是自由 TEXT，需要按命令给出真实枚举值。
TYPE_DEFAULTS = {
    ("material", "search"): "sticker",
    ("material", "download"): "sticker",
    ("material", "query"): "sticker",
    ("material", "recommend"): "sticker",
    ("material", "similar"): "sticker",
    ("material", "topic"): "sticker",
    ("media", "measure-box"): "sticker",
}
# --mode 在官方 help 里常是自由 TEXT，但取值域被命令限定。
MODE_DEFAULTS = {
    ("draft", "algo", "subtitle-recognize"): "draft",
    ("draft", "algo", "ai-matting"): "auto",
    ("draft", "algo", "quality-enhance"): "auto",
}
# 官方 help 有明确枚举语义的 flag：给真实合法值，避免"用错值"掩盖命令本身行为。
FLAG_VALUE_DEFAULTS = {
    "--ratio": "16:9",
    "--op": "split",
    "--mode": "auto",
    "--type": "text",
    "--language": "zh",
    "--lang": "zh",
    "--speaker": "BV700_streaming",
    "--name": "func-test",
    "--title": "func-test",
    "--label": "func-test",
    "--text": "功能测试",
    "--content": "功能测试",
    "--prompt": "花",
    "--field": "width",
    "--alignment": "center",
    "--typesetting": "horizontal",
    "--sam3-target-object-desc": "object",
    "--seg-type": "video",
    "--speed": "1.0",
    # 官方 help 列出的合法值是 position-x/position-y/scale/scale-x/opacity…，"position" 不被接受。
    "--animated-property": "opacity",
    "--track": "0",
    "--target-timeline": "0",
    "--source-timeline": "0",
    "--params": "points=1000000",
    "--params-json": "{}",
}
# 官方很多数值参数在 help 里只标 TEXT，传非数字会被拒（invalid numeric literal）。
NUMERIC_DEFAULTS = {
    "--scale": "1", "--alpha": "1", "--volume": "1", "--rotation": "0",
    "--width": "640", "--height": "360", "--x": "0", "--y": "0",
    "--speed": "1.0", "--size": "7", "--wrap-width": "20", "--limit": "5",
    "--steps": "1", "--timeout": "30", "--poll-interval": "1", "--quality": "2",
    "--bitrate": "0", "--fps": "0", "--times": "1", "--layer": "1",
}
NUMERIC_HINTS = ("rotation", "scale", "alpha", "volume", "width", "height", "brightness",
                 "contrast", "saturation", "hue", "sharpening", "vignetting", "highlight",
                 "shadow", "white", "black", "fade", "spacing", "offset", "angle", "radius",
                 "strength", "range", "glow", "bitrate", "fps", "quality", "index",
                 "count", "steps", "limit", "interval", "timeout", "temperature", "particle",
                 "diffuse", "smoothing", "timeline", "order", "intensity", "opacity",
                 "degree", "zoom", "blur", "round", "percent")


def make_value(spec, ctx, path):
    """为一条参数生成真实可用取值；返回 None 表示不该主动传这个参数。"""
    flag = spec.flag
    # --format 必须与 --output 后缀一致，不能直接取 choices[0]（jpg）。
    if flag == "--format":
        if tuple(path) == ("draft", "blueprint", "resource"):
            return None  # --format 只有配合 --sync 才合法
        hint = " ".join(path)
        if "image" in hint or "sticker" in hint or "cover" in hint:
            return "png"
        if "audio" in hint or "music" in hint or "asr" in hint:
            return "m4a"
        return "mp4"
    if spec.choices:
        return spec.choices[0]
    if flag == "--target":
        # 官方 selector 语法：seg_id=<真实 id>（见 draft edit 的 SELECTORS 段）。
        return f"seg_id={ctx.seg_id}" if ctx.seg_id else None
    if flag == "--to" and tuple(path) == ("draft", "project", "duplicate"):
        # --to 在时间类参数表里也会出现，必须按命令先判语义。
        return ctx.copy_ref()
    if flag == "--out" and tuple(path) == ("draft", "audio", "fade"):
        return "1s"  # fade 的 --out 是时间，不是输出文件
    if flag == "--mode" and tuple(path) == ("draft", "video", "color", "smart-color"):
        return "0"
    if flag == "--mode" and tuple(path) in MODE_DEFAULTS:
        return MODE_DEFAULTS[tuple(path)]
    if flag in FLAG_VALUE_DEFAULTS:
        return FLAG_VALUE_DEFAULTS[flag]
    if flag == "--ref":
        return ctx.ref
    if flag == "--dir" and tuple(path) == ("draft", "project", "create"):
        return str(ctx.draft_dir)  # create 的 --dir 是新建工程的父目录
    if flag == "--workspace":
        return str(ctx.fresh_workspace(clear=(tuple(path) == ("draft", "blueprint", "init"))))
    if flag in MEDIA_INPUT_FLAGS:
        target = ctx.pick_media(path, flag)
        if flag == "--resource":
            # 官方 draft 命令的 --resource 只接受 local:///<绝对路径> 或 template://<id>。
            return "local:///" + str(target).replace("\\", "/").lstrip("/")
        return str(target)
    if flag in DIR_FLAGS:
        return str(ctx.out_dir)
    if flag in FILE_OUTPUT_FLAGS:
        return str(ctx.output_path(flag, path))
    if flag in SEGMENT_FLAGS:
        return ctx.seg_id_for(path)
    if flag in INDEX_FLAGS:
        return "0"
    if flag in DURATION_FLAGS:
        token = spec.type_token
        if "microsecond" in token:
            return "1000000"
        if "second" in token:
            return "1"
        if "<START,END>" in token or "<duration-list>" in token:
            return "0,1"
        # --end 必须严格大于 --start，否则官方报 invalid time range。
        if flag == "--end":
            return "1s"
        if flag == "--start":
            return "0s"
        return "1s"
    if flag == "--to":
        return "1s"
    if flag in {"--time", "--out", "--in", "--times"}:
        # 官方要求显式单位：裸数字会被 "expects an explicit unit: us, ms, s, or min" 拒绝。
        return "1s"
    if flag == "--points":
        if "keyframe" in path:
            # 官方要求显式时间单位：0s:0.2,1s:0.8
            return "0s:0.2,1s:0.8"
        return "1s"
    if flag == "--params-json":
        return "{}"
    if flag == "--type" and tuple(path) in TYPE_DEFAULTS:
        return TYPE_DEFAULTS[tuple(path)]
    token = spec.type_token
    if token.startswith("INT") or token in {"INT"}:
        return "1"
    if token.startswith("FLOAT") or token in {"FLOAT"}:
        return "1.0"
    if flag in NUMERIC_DEFAULTS:
        return NUMERIC_DEFAULTS[flag]
    bare = flag.lstrip("-")
    if any(hint in bare for hint in NUMERIC_HINTS):
        return "0"  # 官方把不少数值参数标成 TEXT，给数字才不会触发 numeric literal 错误
    if token == "TEXT:DIR":
        return str(ctx.out_dir)
    if token == "TEXT:FILE":
        return str(ctx.media_path("--input"))
    if token.startswith("TEXT:{true,false}") or token == "{false}" or token == "{true}":
        return "true"
    if "<online|test|local_test>" in token:
        return "online"
    if token.startswith("<") or token.startswith("TEXT"):
        return ctx.generic_value(flag)
    return None


class TestContext:
    """真实测试用的素材、草稿工程与取值。"""

    def __init__(self, cli, root, ref_name=None):
        self.cli = cli
        self.root = Path(root)
        self.media_dir = self.root / "media"
        self.out_dir = self.root / "out"
        self.workspace = self.root / "workspace"
        self.draft_dir = DRAFT_ROOT  # 官方唯一识别的草稿父目录
        self.media_files = {}
        self.ref_name = ref_name or (DRAFT_PREFIX + time.strftime("%m%d-%H%M%S"))
        self.ref = "local://" + self.ref_name
        self.seg_id = None
        self.seg_ids = []
        self.ids_by_type = {}
        self.seed_steps = []
        self.create_outcome = None
        self.generic = {}
        self.notes = []
        self.draft_root = None
        self.baseline = {}
        self.created_by_test = False

    def prepare(self):
        for path in (self.media_dir, self.out_dir, self.workspace):
            path.mkdir(parents=True, exist_ok=True)
        self._make_media()
        self.build_draft()

    def build_draft(self):
        """建工程 → 灌入真实片段 → 取真实 id → 存基线。"""
        self._create_draft()
        self._seed_content()
        self.snapshot()

    def _seed_content(self):
        """用官方命令把真实视频/文字/音频写入工程，模拟真实工作里的初始素材。"""
        if not (self.draft_root and self.draft_root.is_dir()):
            return
        video = media_uri(self.media_files["video"])
        audio = media_uri(self.media_files["audio"])
        seeds = [
            # --track 官方要求整数轨道号，写 "video" 会被 ValidationError 拒绝并让工程没有视频段。
            ("video", ["draft", "video", "add", "--ref", self.ref, "--resource", video,
                       "--track", "0", "--start", "0s"]),
            ("text", ["draft", "text", "add", "--ref", self.ref, "--content", "功能测试字幕",
                      "--start", "0s", "--duration", "3s"]),
            ("audio", ["draft", "audio", "add", "--ref", self.ref, "--kind", "music",
                       "--resource", audio, "--start", "0s"]),
        ]
        for kind, args in seeds:
            outcome = self.cli(args, cwd=str(self.root),
                               read_write=self.read_write_paths(),
                               read_only=[str(self.media_dir)])
            self.seed_steps.append({"kind": kind, "state": outcome.state,
                                    "exit_code": outcome.exit_code,
                                    "message": outcome.message[:200]})
        summary = self.cli(["draft", "extract", "summary", "--ref", self.ref],
                           cwd=str(self.root), read_write=self.read_write_paths())
        structure = parse_json_result(summary)
        self.ids_by_type = {}
        for kind in SEGMENT_TYPES:
            ids = find_ids(structure, kind)
            if ids:
                self.ids_by_type[kind] = ids
        # 只接受真正的片段类型；绝不能回退成 draft/track id —— 那会让每条命令报
        # "segment not found"，把整轮测试变成假阴性。
        self.seg_ids = [value for kind in SEGMENT_TYPES
                        for value in self.ids_by_type.get(kind, [])]
        self.seg_id = self.seg_ids[0] if self.seg_ids else None
        self.seed_steps.append({"kind": "extract-summary", "state": summary.state,
                                "ids": {k: v[:3] for k, v in self.ids_by_type.items()},
                                "all_ids": self.seg_ids[:5]})

    def snapshot(self):
        """记录基线工程内容，便于破坏性命令前后复位。"""
        self.baseline = {}
        if self.draft_root and self.draft_root.is_dir():
            for item in self.draft_root.rglob("*"):
                if item.is_file():
                    self.baseline[str(item.relative_to(self.draft_root))] = item.read_bytes()

    def restore(self):
        """把工程恢复到基线；只影响本测试自己创建的工程。"""
        if not self.draft_root or not self.draft_root.is_dir():
            return False
        for item in list(self.draft_root.rglob("*")):
            if item.is_file() and str(item.relative_to(self.draft_root)) not in self.baseline:
                item.unlink(missing_ok=True)
        for relative, content in self.baseline.items():
            target = self.draft_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return True

    def cleanup(self):
        """只删除本测试创建的草稿工程，绝不动用户其他工程。"""
        if self.created_by_test and self.ref_name.startswith(DRAFT_PREFIX):
            shutil.rmtree(DRAFT_ROOT / self.ref_name, ignore_errors=True)

    def refresh_draft_root(self):
        """重新指向本测试的工程目录（create 之后目录才出现）。"""
        candidate = self.draft_dir / self.ref_name
        self.draft_root = candidate if candidate.is_dir() else None
        return self.draft_root

    def ensure_draft(self):
        """命令把工程删掉后重建（含真实片段），保证后续命令仍有可操作目标。"""
        if self.draft_root and self.draft_root.is_dir():
            return False
        self.notes.append("工程被上一条命令删除，已重建并重新灌入片段")
        self.build_draft()
        return True

    def drop_draft(self):
        """执行 create 命令前清空目标，模拟"工程尚不存在"的真实前置条件。"""
        if self.draft_root:
            shutil.rmtree(self.draft_root, ignore_errors=True)
        self.draft_root = None

    def read_write_paths(self):
        paths = [self.root]
        if self.draft_root and self.draft_root.is_dir():
            paths.append(self.draft_root)
        else:
            paths.append(self.draft_dir)  # create 前目标工程还不存在，需要草稿根写权限
        return paths

    def _make_media(self):
        """用 ffmpeg 合成真实素材（不读取用户媒体）。"""
        video = self.media_dir / "sample.mp4"
        audio = self.media_dir / "sample.m4a"
        image = self.media_dir / "sample.png"
        if not video.is_file():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "testsrc2=size=640x360:rate=30:duration=4", "-f", "lavfi", "-i",
                 "sine=frequency=440:sample_rate=48000:duration=4", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
                check=True)
        if not audio.is_file():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "sine=frequency=660:sample_rate=48000:duration=4",
                 "-c:a", "aac", str(audio)], check=True)
        if not image.is_file():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=c=orange:size=320x320:duration=1", "-frames:v", "1", str(image)],
                check=True)
        self.media_files = {"video": video, "audio": audio, "image": image}

    def media_path(self, flag):
        if "audio" in flag or flag == "--audio":
            return self.media_files.get("audio") or self.media_files["video"]
        if "image" in flag or "photo" in flag:
            return self.media_files.get("image") or self.media_files["video"]
        return self.media_files.get("video") or self.media_files["audio"]

    def seg_id_for(self, path):
        """按命令所属域返回对应类型的真实片段 id。"""
        domain = path[1] if len(path) > 1 else ""
        wanted = SEGMENT_TYPE_BY_DOMAIN.get(domain)
        if wanted and self.ids_by_type.get(wanted):
            return self.ids_by_type[wanted][0]
        if domain == "sticker" and self.ids_by_type.get("video"):
            return self.ids_by_type["video"][0]
        for kind in ("video", "text", "audio"):
            if self.ids_by_type.get(kind):
                return self.ids_by_type[kind][0]
        return None

    def copy_ref(self):
        """project duplicate 的目标工程名（必须是合法 local:// ref）。"""
        return "local://" + self.ref_name + "-copy"

    def fresh_workspace(self, clear=False):
        """给 blueprint 命令用的工作区目录；init 需要空目录。"""
        if clear:
            shutil.rmtree(self.workspace, ignore_errors=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        return self.workspace

    def pick_media(self, path, flag):
        """按命令语义挑真实素材：图片命令给 png，音频命令给 m4a，其余给 mp4。"""
        hint = " ".join(path) + " " + flag
        if "image" in hint or "photo" in hint or "sticker" in hint or "cover" in hint:
            return self.media_files.get("image") or self.media_files["video"]
        if "audio" in hint or "music" in hint or "asr" in hint or "vad" in hint:
            return self.media_files.get("audio") or self.media_files["video"]
        return self.media_files.get("video") or self.media_files["audio"]

    def output_path(self, flag, path):
        # 官方按输出后缀判定目标格式：音频命令必须 .aac/.m4a/.mp3，图片命令必须 .jpg/.png。
        hint = " ".join(path) + " " + flag
        if "image" in hint or "sticker" in hint or "cover" in hint:
            suffix = ".png"
        elif "audio" in hint or "asr" in hint or "music" in hint:
            suffix = ".m4a"
        else:
            suffix = ".mp4"
        return self.out_dir / ("-".join(path) + suffix)

    def generic_value(self, flag):
        """非路径类自由文本的稳定占位值。"""
        if flag in self.generic:
            return self.generic[flag]
        if flag == "--language" or flag == "--lang":
            return "zh"
        if flag == "--speaker":
            return "BV700_streaming"
        return "func-test"

    def _create_draft(self):
        """用官方命令真实创建一个全新草稿工程（同时验证 create 命令）。"""
        target = self.draft_dir / self.ref_name
        shutil.rmtree(target, ignore_errors=True)
        self.created_by_test = True
        outcome = self.cli(["draft", "project", "create", "--ref", self.ref,
                            "--dir", str(self.draft_dir)],
                           cwd=str(self.draft_dir), read_write=[self.draft_dir])
        self.create_outcome = outcome
        if not outcome.ok:
            self.notes.append(f"create 未成功: {outcome.state} {outcome.message[:200]}")
        self.draft_root = target if target.is_dir() else None
        if self.draft_root is None:
            self.notes.append("测试工程目录不存在，后续命令将缺少 --ref 目标")


def build_invocation(path, specs, ctx):
    """按官方 help 规格构造一次最小但真实的调用。"""
    args = list(path)
    used = []
    # 官方有些命令要求 --enable / --disable 二选一，属于"必填开关"而非参数。
    flags = {spec.flag for spec in specs}
    if "--enable" in flags and "--disable" in flags:
        args.append("--enable")
        used.append("--enable")
    for flag, value in PATH_EXTRA_ARGS.get(tuple(path), {}).items():
        if flag in flags:
            args += [flag, value]
            used.append(flag)
    has_seg_id = "--seg-id" in flags and bool(ctx.seg_id)
    skip = set(PATH_SKIP_FLAGS.get(tuple(path), set()))
    # 官方成对互斥的参数：--end 与 --duration 只能给一个；lint draft 的 --ref 排除 --input。
    if "--duration" in flags:
        skip.add("--end")
    if tuple(path) == ("lint", "draft") and "--ref" in flags:
        skip.add("--input")
    for spec in specs:
        if has_seg_id and spec.flag in LOCATOR_FLAGS:
            continue  # 与 --seg-id 互斥，官方会直接拒绝
        if spec.flag in skip:
            continue
        if spec.flag in GLOBAL_FLAGS:
            continue
        if not spec.takes_value:
            continue  # 开关一律不加：避免 --wait / --replace 这类长等待或破坏行为
        if spec.flag in SEGMENT_FLAGS and tuple(path) in OPTIONAL_SEGMENT_PATHS:
            continue
        if spec.required or spec.flag in PROACTIVE_FLAGS:
            value = make_value(spec, ctx, path)
            if value is None:
                continue
            args += [spec.flag, str(value)]
            used.append(spec.flag)
    return args, used


# --------------------------------------------------------------------------- 契约层

def check_contract(manifest=None):
    """逐条比对 wrapper 与实时 help：白名单、严格模式、别名。"""
    manifest = manifest or json.loads(MANIFEST.read_text(encoding="utf-8"))
    cli = lyra_cli
    generated = set(getattr(cli, "COMMAND_INDEX", {}))
    rows = []
    for spec in manifest["commands"]:
        path = list(spec["path"])
        name = lyra_commands.function_name(path)
        function = getattr(cli, name, None)
        expected = [flag for flag in spec["options"] if flag not in GLOBAL_FLAGS]
        row = {"path": path, "name": name, "installed": callable(function),
               "generated": name in generated}
        if not row["installed"]:
            row["problem"] = "wrapper 未安装"
            rows.append(row)
            continue
        if not row["generated"]:
            # 手写封装优先（记入 COMMAND_MANUAL_OVERRIDES）：只校验可用性，
            # 白名单属性属于清单生成的函数，不适用于手写实现。
            rows.append(row)
            continue
        problems = []
        if function.allowed_options != expected:
            problems.append(f"白名单不一致: {function.allowed_options} != {expected}")
        if function.strict_options != (spec.get("help_state", "ok") == "ok"):
            problems.append("严格模式与 help_state 不一致")
        if function.command_path != path:
            problems.append("command_path 不一致")
        if set(function.allowed_options) & GLOBAL_FLAGS:
            problems.append("全局开关进入了白名单")
        help_text = load_help_text(path)
        if help_text:
            # 同一参数行可能有多个别名（--path, --input），清单收录全部别名，
            # 契约比对也必须逐个展开，否则会把别名误报成"多余参数"。
            live = [flag for item in parse_option_specs(help_text)
                    for flag in item.aliases if flag not in GLOBAL_FLAGS]
            missing = [flag for flag in live if flag not in expected]
            extra = [flag for flag in expected if flag not in live]
            if missing:
                problems.append(f"实时 help 有但清单缺: {missing}")
            if extra:
                problems.append(f"清单有但实时 help 无: {extra}")
        row["problem"] = "; ".join(problems)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- 执行层

DESTRUCTIVE_HINTS = ("remove", "delete", "clear", "dissolve", "break-apart", "undo",
                     "redo", "trim", "split", "replace", "apply", "publish", "render",
                     "download", "compress", "transcode", "extract", "add", "update",
                     "set", "create", "init", "sync", "recognize", "generate", "tts")


def is_destructive(path):
    return any(part in DESTRUCTIVE_HINTS for part in path)


def run_command(path, ctx, args):
    outcome = ctx.cli(args, cwd=str(ctx.root), read_write=ctx.read_write_paths(),
                      read_only=[str(ctx.media_dir)])
    return {"path": path, "args": args[1:], "state": outcome.state,
            "exit_code": outcome.exit_code, "err_code": outcome.err_code,
            "automation_exit_code": outcome.automation_exit_code,
            "err_category": outcome.err_category, "message": outcome.message[:400],
            "stdout": outcome.stdout[:600], "duration_ms": outcome.duration_ms}


def execute_layer(paths, ctx, restore_before_write=True):
    """逐条真实执行命令；写入类命令执行前把工程复位到基线，保证各条独立可比。"""
    rows = []
    for path in paths:
        help_text = load_help_text(path)
        specs = parse_option_specs(help_text) if help_text else []
        args, used = build_invocation(path, specs, ctx)
        is_create = tuple(path) == ("draft", "project", "create")
        if is_create:
            ctx.drop_draft()  # create 需要"工程不存在"的真实前置条件
        elif restore_before_write and is_destructive(path):
            ctx.restore()
        try:
            row = run_command(path, ctx, args)
        except Exception as exc:  # 真实调用层的异常也要留证据，不能中断整轮
            row = {"path": path, "args": args[1:], "state": "runner_exception",
                   "stdout": "",
                   "message": f"{type(exc).__name__}: {exc}"[:400], "duration_ms": 0}
        row["used_flags"] = used
        if is_create:
            # create 之后工程是空的，必须重新灌入真实片段并重建基线。
            ctx.build_draft()
        else:
            # 上一条命令可能删除或改动了工程：恢复基线，必要时重建，保证各条独立可比。
            if not ctx.ensure_draft():
                ctx.restore()
        rows.append(row)
    return rows


def summarize(rows):
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return counts


# --------------------------------------------------------------------------- 工作流层

def media_uri(path):
    """官方 draft 命令要求 local:///<绝对路径> 形式。"""
    return "local:///" + str(path).replace("\\", "/").lstrip("/")


# 官方 extract/blueprint 结构里真正代表"片段"的类型。
SEGMENT_TYPES = ("video", "text", "audio", "sticker", "image", "photo")


def find_ids(node, wanted_type=None, key=("id", "segment_id", "seg_id")):
    """从官方 extract/blueprint 结构里收集真实 id。"""
    found = []
    if isinstance(node, dict):
        if wanted_type is None or node.get("type") == wanted_type:
            for name in key:
                value = node.get(name)
                if isinstance(value, str) and value:
                    found.append(value)
                    break
        for value in node.values():
            found.extend(find_ids(value, wanted_type, key))
    elif isinstance(node, list):
        for item in node:
            found.extend(find_ids(item, wanted_type, key))
    return found


def parse_json_result(outcome):
    """官方若干命令把结构放在 result.json_result 里（字符串化的 JSON）。"""
    try:
        body = json.loads(outcome.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    result = body.get("result")
    if isinstance(result, dict) and isinstance(result.get("json_result"), str):
        try:
            return json.loads(result["json_result"])
        except json.JSONDecodeError:
            return None
    return result


def workflow_layer(ctx, keep_draft=False):
    """在全新工程上跑一遍真实剪辑链路，每步都真实调用官方 CLI。"""
    steps = []

    def run(name, args, note=""):
        read_write = ctx.read_write_paths()
        before = draft_digest(ctx)
        outcome = ctx.cli(args, cwd=str(ctx.root), read_write=read_write,
                          read_only=[str(ctx.media_dir)])
        after = draft_digest(ctx)
        record = {"step": name, "note": note, "args": args, "state": outcome.state,
                  "exit_code": outcome.exit_code, "message": outcome.message[:400],
                  "stdout": outcome.stdout[:1500], "duration_ms": outcome.duration_ms,
                  "draft_changed": bool(before and after and before != after)}
        steps.append(record)
        return outcome

    ctx.drop_draft()
    ctx.snapshot()
    video = media_uri(ctx.media_files["video"])
    audio = media_uri(ctx.media_files["audio"])
    image = media_uri(ctx.media_files["image"])

    run("01 建工程", ["draft", "project", "create", "--ref", ctx.ref,
                     "--dir", str(ctx.draft_dir)], "官方只在草稿根下识别工程")
    ctx.refresh_draft_root()
    ctx.snapshot()
    run("02 加主视频", ["draft", "video", "add", "--ref", ctx.ref,
                       "--resource", video, "--track", "0", "--start", "0s"],
        "真实 mp4 入轨（--track 官方要求整数轨道号）")
    run("03 加画中画", ["draft", "video", "add", "--ref", ctx.ref,
                       "--resource", video, "--track", "0", "--start", "1s",
                       "--duration", "2s"], "同轨第二段")
    run("04 加文字", ["draft", "text", "add", "--ref", ctx.ref,
                     "--content", "功能测试字幕", "--start", "0s", "--duration", "3s"])
    run("05 加音频", ["draft", "audio", "add", "--ref", ctx.ref, "--kind", "music",
                     "--resource", audio, "--start", "0s"])
    summary = run("06 导出结构", ["draft", "extract", "summary", "--ref", ctx.ref])
    structure = parse_json_result(summary)
    ids = [value for kind in SEGMENT_TYPES
           for value in find_ids(structure, kind)]
    ctx.seg_id = ids[0] if ids else None
    steps[-1]["found_ids"] = ids[:6]
    steps[-1]["seed_steps"] = ctx.seed_steps
    if not ctx.seg_id:
        steps.append({"step": "前置失败", "state": "blocked",
                      "message": "未能从工程结构里取到真实 seg id"})
        if not keep_draft:
            ctx.cleanup()
        return steps
    run("07 视频变速", ["draft", "video", "speed", "--ref", ctx.ref,
                       "--seg-id", ctx.seg_id, "--speed", "1.5"])
    run("08 视频裁剪", ["draft", "video", "crop", "--ref", ctx.ref,
                       "--seg-id", ctx.seg_id, "--ratio", "16:9"])
    run("09 视频调色", ["draft", "video", "adjust", "--ref", ctx.ref,
                       "--seg-id", ctx.seg_id, "--brightness", "0.1",
                       "--saturation", "0.1"])
    run("10 加关键帧", ["draft", "keyframe", "add", "--ref", ctx.ref,
                       "--seg-id", ctx.seg_id, "--animated-property", "opacity",
                       "--points", "0s:0.2,1s:0.8"],
        "官方只接受 position-x/scale/opacity 等属性名，--points 为 REQUIRED")
    run("11 撤销", ["draft", "history", "undo", "--ref", ctx.ref, "--steps", "1"],
        "官方：standalone 版不支持，验证报错文案")
    run("12 重做", ["draft", "history", "redo", "--ref", ctx.ref, "--steps", "1"])
    run("13 加字幕条", ["draft", "subtitle", "add", "--ref", ctx.ref,
                       "--content", "真实字幕", "--start", "0s", "--duration", "2s"])
    run("14 加滤镜", ["draft", "video", "filter", "add", "--ref", ctx.ref,
                     "--seg-id", ctx.seg_id, "--resource", image],
        "需要真实滤镜资源 id")
    run("15 导出模板包", ["draft", "template", "publish", "--ref", ctx.ref,
                        "--dir", str(ctx.out_dir)], "真实产出模板压缩包")
    final = run("16 最终结构", ["draft", "extract", "summary", "--ref", ctx.ref])
    final_structure = parse_json_result(final)
    steps[-1]["segment_ids"] = find_ids(final_structure)[:10]
    steps[-1]["outputs"] = sorted(item.name for item in ctx.out_dir.iterdir())[:10]
    if not keep_draft:
        ctx.cleanup()
    return steps


STATE_LABELS = {
    "ok": "✅ 成功",
    "usage": "⚠️ 官方参数/用法拒绝",
    "business_error": "⚠️ 官方业务拒绝",
    "needs_login": "🔐 需要登录",
    "needs_prerequisite": "➡️ 需真实前置产物",
    "not_implemented": "🚧 官方未实现",
    "requires_embedded_library": "🚧 仅内嵌库支持",
    "model_missing": "📦 本机缺模型",
    "timeout": "⏱️ 超时",
    "worker_timeout": "⏱️ worker 超时",
}


def render_markdown(report):
    """把一次测试报告渲染成可复核的 markdown。"""
    lines = ["# lyra-cli 真实功能测试报告", ""]
    lines.append(f"- 清单命令数：{report.get('command_count', '-')}")
    contract = report.get("contract")
    if contract:
        lines += ["", "## 契约层", "",
                  f"- 检查命令：{contract['checked']}",
                  f"- 问题数：{len(contract['problems'])}"]
        for row in contract["problems"][:20]:
            lines.append(f"  - {' '.join(row['path'])}：{row['problem']}")
    execute = report.get("execute")
    if execute:
        summary = execute["summary"]
        lines += ["", "## 执行层", "", "| 状态 | 数量 |", "| --- | --- |"]
        for state, count in sorted(summary.items(), key=lambda item: -item[1]):
            lines.append(f"| {STATE_LABELS.get(state, state)} | {count} |")
        lines += ["", "| 命令 | 状态 | exit | 参数 | 官方消息 |", "| --- | --- | --- | --- | --- |"]
        for row in execute["rows"]:
            args = " ".join(row.get("args", []))[:120].replace("|", "\\|")
            message = (row.get("message") or "")[:120].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {' '.join(row['path'])} | {STATE_LABELS.get(row['state'], row['state'])} "
                         f"| {row.get('exit_code')} | `{args}` | {message} |")
    workflow = report.get("workflow")
    if workflow:
        lines += ["", "## 工作流层", "",
                  "| 步骤 | 状态 | exit | 工程变化 | 说明 |", "| --- | --- | --- | --- | --- |"]
        for step in workflow["steps"]:
            note = (step.get("note") or "").replace("|", "\\|")
            message = (step.get("message") or "")[:80].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {step['step']} | {STATE_LABELS.get(step['state'], step['state'])} "
                         f"| {step.get('exit_code')} | {step.get('draft_changed')} | {note or message} |")
    return "\n".join(lines) + "\n"


def draft_digest(ctx):
    """工程文件的内容指纹，用于判断命令是否真的改变了工程。"""
    import hashlib
    if not ctx.draft_root or not ctx.draft_root.is_dir():
        return None
    digest = hashlib.sha256()
    for item in sorted(ctx.draft_root.rglob("*")):
        if item.is_file():
            digest.update(str(item.relative_to(ctx.draft_root)).encode("utf-8"))
            digest.update(item.read_bytes())
    return digest.hexdigest()


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", choices=["contract", "execute", "workflow", "all"],
                        default="all")
    parser.add_argument("--only", help="只跑路径包含该子串的命令")
    parser.add_argument("--limit", type=int, help="最多跑多少条命令")
    parser.add_argument("--timeout", type=int, default=120, help="单条命令超时秒数")
    parser.add_argument("--keep-draft", action="store_true",
                        help="保留测试草稿工程便于人工复核（默认测完删除）")
    args = parser.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = [list(spec["path"]) for spec in manifest["commands"]]
    if args.only:
        paths = [path for path in paths if args.only in " ".join(path)]
    if args.limit:
        paths = paths[:args.limit]

    report = {"command_count": len(paths)}
    if args.layer in ("contract", "all"):
        rows = check_contract(manifest)
        bad = [row for row in rows if row.get("problem")]
        report["contract"] = {"checked": len(rows), "problems": bad}
        print(f"契约层: 检查 {len(rows)} 条，问题 {len(bad)} 条")
    if args.layer == "workflow":
        cli = OfficialCli(timeout=args.timeout)
        ctx = TestContext(cli, WORK)
        ctx.prepare()
        steps = workflow_layer(ctx, keep_draft=args.keep_draft)
        report["context"] = {"ref": ctx.ref, "draft_root": str(ctx.draft_root),
                             "workspace": str(ctx.root)}
        report["workflow"] = {"steps": steps, "summary": summarize(steps)}
        print("工作流层:", json.dumps(summarize(steps), ensure_ascii=False))
    elif args.layer in ("execute", "all"):
        cli = OfficialCli(timeout=args.timeout)
        ctx = TestContext(cli, WORK)
        ctx.prepare()
        report["context"] = {
            "ref": ctx.ref, "draft_root": str(ctx.draft_root),
            "workspace": str(ctx.root), "media": {k: str(v)
                                                  for k, v in ctx.media_files.items()},
            "create": {"state": getattr(ctx.create_outcome, "state", None),
                       "message": getattr(ctx.create_outcome, "message", "")[:200]},
            "notes": ctx.notes,
        }
        rows = execute_layer(paths, ctx)
        report["execute"] = {"rows": rows, "summary": summarize(rows)}
        print("执行层:", json.dumps(summarize(rows), ensure_ascii=False))
        if not args.keep_draft:
            ctx.cleanup()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = EVIDENCE_DIR / f"functional-{args.layer}-{stamp}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline="\n")
    markdown = EVIDENCE_DIR / f"functional-{args.layer}-{stamp}.md"
    markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print("报告:", target)
    print("Markdown:", markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
