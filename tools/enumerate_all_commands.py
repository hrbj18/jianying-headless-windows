#!/usr/bin/env python3
"""从官方 ``lyra-cli --help`` 动态递归生成命令能力清单。

本工具保留真实的官方 CLI 调用：每个节点都通过剪映自带 VMSDK 沙箱执行
``lyra-cli <path> --help``。顶层与叶命令从每层 help 动态递归发现；由于官方
``draft --help`` 不列出 ``video/text/subtitle`` 等对象快捷域，另保留一份文档化的
**域级最低种子**；上一版清单路径也作为回归种子逐条实测，但不再硬编码动作树。

发布分两步：

1. 探测结果始终原子写入 ``work/lyra-capabilities.json`` 作为诊断证据；
2. 只有通过旧清单不退化、已知域不丢失、成功率等门禁后，才原子替换
   ``engine/lyra_commands.json``。``--force`` 可显式接受退化，``--evidence-only``
   则永不改写引擎清单。长时间复核可用 ``--reuse-help-evidence`` 复用已验证的成功 help
   与确定性 unsupported 证据；暂态失败与缺失节点仍会真实重试。

模块导入不会调用外部进程；真实探测只在 :func:`main` 或显式实例化
:class:`OfficialHelpProbe` 后发生，便于对解析与发布门禁做纯单元测试。
"""
from __future__ import annotations

import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import draftediting_runtime as dr  # noqa: E402
import lyra_commands  # noqa: E402
import windows_runtime  # noqa: E402

ENGINE_MANIFEST = ROOT / "engine" / "lyra_commands.json"
EVIDENCE_MANIFEST = ROOT / "work" / "lyra-capabilities.json"
HELP_EVIDENCE_DIR = ROOT / "work" / "lyra-help"
GLOBAL_FLAGS = {"--help", "--version", "--jq"}
MIN_SUCCESS_RATIO = 0.50
# 这些前缀来自当前剪映官方 help 与本项目能力文档；它们只是发布下限，实际命令仍动态发现。
REQUIRED_PREFIXES = (
    ("auth",),
    ("draft", "history"),
    ("draft", "deform"),
    ("draft", "edit"),
    ("draft", "text-template"),
)
# 官方 draft 根 help 隐藏的对象快捷域；这里只列域，不列叶动作，叶命令仍以真实 help 为准。
DRAFT_DOMAIN_SEEDS = tuple(("draft", name) for name in (
    "project", "cover", "extract", "template", "algo", "history", "deform", "edit",
    "video", "sticker", "text", "text-template", "audio", "segment", "timeline",
    "compound-clip", "filter", "effect", "adjust", "subtitle", "lyrics", "keyframe",
    "config", "blueprint",
))
_SUBCOMMAND_HEADINGS = ("CLI management", "LYRA DOMAINS", "DOMAINS",
                        "SUBCOMMANDS", "ACTIONS", "COMMANDS")
_HEADING_RE = re.compile(r"^[A-Z][A-Z0-9 _/()&-]*:?$")
_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")
_OPTION_ROW_RE = re.compile(
    r"^ {0,12}(?:-[A-Za-z],\s*)?"
    r"(?P<aliases>--[a-z][a-z0-9-]*(?:\{[^}]*\})?"
    r"(?:,\s*--[a-z][a-z0-9-]*(?:\{[^}]*\})?)*)"
)
_COMMAND_TOKEN = r"[A-Za-z][A-Za-z0-9-]*"
_COMMAND_ALIAS_ROW_RE = re.compile(
    rf"^ {{2,8}}(?P<aliases>{_COMMAND_TOKEN}(?:,\s*{_COMMAND_TOKEN})+)(?:\s+.*)?$"
)
_COMMAND_ROW_RE = re.compile(rf"^ {{2,8}}({_COMMAND_TOKEN})(?: {{2,}}\S|\s*$)")


@dataclass(frozen=True)
class ProbeResult:
    """一次真实或测试替身 help 探测的结果。"""

    state: str
    text: str = ""
    error: str = ""


def _dig(node, key):
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for value in node.values():
            yield from _dig(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from _dig(item, key)


def _safe_name(path):
    return "root" if not path else "_".join(path)


def probe_payload_matches_invocation(payload, install, path):
    """缓存证据必须来自当前剪映安装，并且参数与本次 help 路径完全一致。"""
    result = (((payload or {}).get("responseMessage") or {}).get("result") or {})
    actual_command = os.path.normcase(os.path.normpath(str(result.get("command") or "")))
    expected_command = os.path.normcase(os.path.normpath(str(Path(install) / "lyra-cli.exe")))
    return (actual_command == expected_command and
            result.get("args") == list(path) + ["--help"])


def interpret_probe_payload(payload):
    """把 VMSDK 结果严格解释为 help；非零退出或普通错误文本绝不能算成功。"""
    response = (payload or {}).get("responseMessage") or {}
    result = response.get("result") or {}
    texts = [value for value in _dig(payload, "stdout")
             if isinstance(value, str) and value.strip()]
    if result.get("timedOut"):
        return ProbeResult("timeout", error="lyra-cli help 超时")
    if (response.get("ok") is not True or result.get("ok") is not True or
            result.get("exitCode") != 0):
        detail = {
            "response_ok": response.get("ok"),
            "result_ok": result.get("ok"),
            "exit_code": result.get("exitCode"),
            "stderr": str(result.get("stderr") or "")[-400:],
            "stdout": (texts[0][-400:] if texts else ""),
        }
        detail_text = (detail["stderr"] + "\n" + detail["stdout"]).lower()
        # 官方参数解析器明确表示动作不存在时，这是确定性删除证据，不应继续保留旧能力。
        unsupported = (result.get("exitCode") == 2 and any(marker in detail_text for marker in (
            "arguments were not expected", "unknown command", "no such command",
        )))
        return ProbeResult("unsupported" if unsupported else "error",
                           error=json.dumps(detail, ensure_ascii=False))
    # 外层 worker 也可能写 stdout；只接受具备 CLI help 基本结构的那一段。
    text = next((value for value in texts if "USAGE:" in value), "")
    if not text:
        sample = texts[0][-400:] if texts else str(result.get("stderr") or "")[-400:]
        return ProbeResult("invalid_help", error="没有可识别的 USAGE help: " + sample)
    return ProbeResult("ok", text=text)


class OfficialHelpProbe:
    """通过剪映官方 VMSDK 沙箱真实执行 ``lyra-cli <path> --help``。"""

    def __init__(self, workspace=None, timeout=90, evidence_dir=HELP_EVIDENCE_DIR,
                 reuse_evidence=False):
        runtime = windows_runtime.validate_runtime()
        self.install = Path(runtime["install_dir"])
        dr.find_official_parent(self.install)
        dr.ensure_packaged_bun(self.install)
        default_workspace = (Path(os.environ["LOCALAPPDATA"]) / "Temp" /
                             "jianying-draftediting" / "help-probe")
        self.workspace = Path(workspace or default_workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.timeout = int(timeout)
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.reuse_evidence = bool(reuse_evidence)

    def __call__(self, path):
        path = list(path)
        result_path = self.evidence_dir / f"dynamic-{_safe_name(path)}.json"
        if self.reuse_evidence and result_path.is_file():
            try:
                cached_payload = json.loads(
                    result_path.read_text(encoding="utf-8", errors="replace"))
                cached = (interpret_probe_payload(cached_payload)
                          if probe_payload_matches_invocation(
                              cached_payload, self.install, path)
                          else ProbeResult("stale"))
            except (OSError, json.JSONDecodeError):
                cached = ProbeResult("invalid")
            if cached.state in {"ok", "unsupported"}:
                return cached
        result_path.unlink(missing_ok=True)
        request = {
            "installDir": str(self.install),
            "args": path + ["--help"],
            "cwd": str(self.workspace),
            "env": {"LYRA_CLI_ROOT_WORKSPACE": str(self.workspace),
                    "CUSTOM_AGENT_LYRA_CLI_ROOT_WORKSPACE": str(self.workspace)},
            "timeoutMs": self.timeout * 1000,
            "readOnlyPaths": [str(self.workspace)],
            "readWritePaths": [str(self.workspace)],
        }
        scratch = Path(tempfile.mkdtemp(prefix="lyra-enum-"))
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
        try:
            subprocess.run(
                [str(self.install / "bun.exe"), "--preload",
                 str(self.install /
                     "Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs"),
                 str(dr.WORKER)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=self.timeout + 5, check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult("timeout", error="VMSDK worker 超时")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if not result_path.is_file():
            return ProbeResult("empty", error="VMSDK 未生成结果文件")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            return ProbeResult("invalid", error=f"结果文件不可解析: {exc}")
        return interpret_probe_payload(payload)


def _section_lines(text, headings):
    """取一个 help 章节的原始行，遇到下一个全大写标题即停止。"""
    wanted = {heading.rstrip(":") for heading in headings}
    active = False
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = raw_line.strip()
        normalized = stripped.rstrip(":")
        if not active:
            if normalized in wanted and stripped.endswith(":"):
                active = True
            continue
        if raw_line == raw_line.lstrip() and stripped and _HEADING_RE.fullmatch(stripped):
            break
        yield raw_line.expandtabs(4)


def parse_help(text):
    """解析官方 help，返回摘要、参数 flag 与下一层命令名。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    summary = next((line.strip() for line in normalized.splitlines() if line.strip()), "")
    options, seen_flags = [], set()
    for line in _section_lines(normalized, {"OPTIONS"}):
        match = _OPTION_ROW_RE.match(line)
        if not match:
            continue
        for flag in _FLAG_RE.findall(match.group("aliases")):
            if flag not in seen_flags:
                seen_flags.add(flag)
                options.append(flag)
    # 根 help 把命令拆在 ``CLI management`` 与 ``LYRA DOMAINS`` 两节，子层则使用
    # ``SUBCOMMANDS``；必须合并所有命令章节，不能命中第一节后就停止。
    command_lines = []
    for heading in _SUBCOMMAND_HEADINGS:
        command_lines.extend(_section_lines(normalized, {heading}))
    subcommands, seen_commands = [], set()
    for line in command_lines:
        alias_match = _COMMAND_ALIAS_ROW_RE.match(line)
        if alias_match:
            names = [name.strip() for name in alias_match.group("aliases").split(",")]
        else:
            match = _COMMAND_ROW_RE.match(line)
            names = [match.group(1)] if match else []
        for name in names:
            if name not in seen_commands:
                seen_commands.add(name)
                subcommands.append(name)
    return {"summary": summary[:160], "options": options, "subcommands": subcommands}


def _path_tuple(spec):
    return tuple(spec.get("path") or ())


def discover_commands(probe, previous=None, max_depth=8, seeds=DRAFT_DOMAIN_SEEDS,
                      workers=1):
    """从根 help 与域级种子递归发现叶命令；可有限并发执行真实 help 探测。"""
    previous = previous or {"commands": []}
    previous_by_path = {_path_tuple(spec): spec for spec in previous.get("commands", [])}
    # 官方父 help 会隐藏部分仍可调用的旧动作；把上一版路径作为回归种子逐条真实复核，
    # 既不靠手写动作树，也不会因父列表省略而静默删命令。
    queue = deque([(), *(tuple(path) for path in seeds), *previous_by_path])
    seen, commands, groups, failures, unsupported = set(), [], [], [], []
    probe_count = 0

    def safe_probe(path):
        try:
            result = probe(path)
            if not isinstance(result, ProbeResult):
                raise TypeError("probe 必须返回 ProbeResult")
            return result
        except Exception as exc:  # 单点异常必须变成门禁失败，不能丢掉整批证据
            return ProbeResult("exception", error=f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max(int(workers), 1)) as executor:
        while queue:
            batch = []
            while queue:
                path = queue.popleft()
                if path in seen:
                    continue
                seen.add(path)
                batch.append(path)
            if not batch:
                continue
            probe_count += len(batch)
            # executor.map 保留输入顺序，使并发探测生成的清单仍然确定性排序。
            results = list(executor.map(safe_probe, batch))
            for path, result in zip(batch, results):
                if result.state != "ok":
                    record = {"path": list(path), "state": result.state,
                              "error": result.error}
                    if result.state == "unsupported" and path:
                        # 这是完整的负向能力证据，不是探测失败；不安装 wrapper，单独留痕。
                        unsupported.append(record)
                        continue
                    failures.append(record)
                    if path:
                        old = previous_by_path.get(path)
                        if old is not None:
                            commands.append(dict(old))
                        else:
                            commands.append({"path": list(path), "options": [], "summary": "",
                                             "help_state": result.state})
                    continue
                parsed = parse_help(result.text)
                children = parsed["subcommands"]
                if children:
                    groups.append({"path": list(path), "children": children})
                    if len(path) >= max_depth:
                        failures.append({"path": list(path), "state": "max_depth",
                                         "error": f"超过递归深度 {max_depth}"})
                        continue
                    for child in children:
                        queue.append(path + (child,))
                    continue
                if path:
                    commands.append({"path": list(path), "options": parsed["options"],
                                     "summary": parsed["summary"], "help_state": "ok"})
                else:
                    failures.append({"path": [], "state": "no_commands",
                                     "error": "根 help 未解析出命令域"})
    payload = {
        "generated_from": "recursive lyra-cli <path> --help",
        "count": len(commands),
        "commands": commands,
        "discovery": {
            "probed": probe_count,
            "groups": groups,
            "failures": failures,
            "unsupported": unsupported,
        },
    }
    return payload


def _has_prefix(paths, prefix):
    return any(path[:len(prefix)] == prefix for path in paths)


def validate_candidate(candidate, previous=None, required_prefixes=REQUIRED_PREFIXES,
                       min_success_ratio=MIN_SUCCESS_RATIO):
    """返回阻止发布到 ``engine/`` 的具体原因；空列表表示可以安全发布。"""
    previous = previous or {"commands": []}
    commands = candidate.get("commands") or []
    errors = []
    if candidate.get("count") != len(commands):
        errors.append("candidate.count 与 commands 长度不一致")
    paths = [_path_tuple(spec) for spec in commands]
    if len(paths) != len(set(paths)):
        errors.append("候选清单含重复命令路径")
    names = [lyra_commands.function_name(path) for path in paths]
    if len(names) != len(set(names)):
        errors.append("候选清单含映射到同一函数名的命令路径")
    if not commands:
        errors.append("候选清单为空")
        return errors

    current_by_path = {_path_tuple(spec): spec for spec in commands}
    for old in previous.get("commands", []):
        old_path = _path_tuple(old)
        current = current_by_path.get(old_path)
        if current is None:
            # 旧枚举器把若干命令组误当叶命令；动态枚举出其子命令属于有效展开。
            if not any(path[:len(old_path)] == old_path and len(path) > len(old_path)
                       for path in paths):
                errors.append("旧命令路径消失且没有展开为子命令: " + " ".join(old_path))
        elif old.get("help_state") == "ok" and current.get("help_state") != "ok":
            errors.append("已成功解析的命令退化: " + " ".join(old_path))
        elif old.get("help_state") == "ok":
            missing_options = ((set(old.get("options") or []) - GLOBAL_FLAGS) -
                               set(current.get("options") or []))
            if missing_options:
                errors.append("已成功解析的命令丢失参数: " + " ".join(old_path) +
                              " -> " + ", ".join(sorted(missing_options)))

    previous_ok = sum(1 for spec in previous.get("commands", [])
                      if spec.get("help_state") == "ok")
    current_ok = sum(1 for spec in commands if spec.get("help_state") == "ok")
    ratio = current_ok / len(commands)
    if current_ok < previous_ok:
        errors.append(f"成功解析命令数从 {previous_ok} 降到 {current_ok}")
    if ratio < min_success_ratio:
        errors.append(f"成功解析率 {ratio:.1%} 低于门槛 {min_success_ratio:.1%}")

    for prefix in required_prefixes:
        if not _has_prefix(paths, tuple(prefix)):
            errors.append("缺少已知官方命令域: " + " ".join(prefix))

    for failure in (candidate.get("discovery") or {}).get("failures", []):
        path = tuple(failure.get("path") or ())
        # 即使旧清单同一路径此前也失败，本次失败仍可能掩盖它已经变成命令组或新增参数；
        # 默认发布必须是一次完整发现，任何失败只能由人工复核后用 --force 显式接受。
        errors.append("本次 help 探测未完成: " + (" ".join(path) or "<root>") +
                      f" ({failure.get('state')})")
    return list(dict.fromkeys(errors))


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path, payload):
    """在目标同目录落临时文件并 ``os.replace``，避免中断留下半个 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        # 读回验证后才替换；JSON 结构损坏时保留旧清单。
        json.loads(temp_path.read_text(encoding="utf-8"))
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="官方 help 探测工作区（默认使用 LOCALAPPDATA 临时目录）")
    parser.add_argument("--timeout", type=int, default=15, help="每次官方 help 调用超时秒数")
    parser.add_argument("--workers", type=int, default=4, help="真实 help 探测并发数（默认 4）")
    parser.add_argument("--max-depth", type=int, default=8, help="命令树最大递归深度")
    parser.add_argument("--reuse-help-evidence", action="store_true",
                        help="复用已验证的成功/unsupported help，只真实重试缺失或暂态失败节点")
    parser.add_argument("--evidence-only", action="store_true",
                        help="只更新 work/ 证据，不改写 engine/lyra_commands.json")
    parser.add_argument("--publish-evidence", action="store_true",
                        help="不重新探测，复核并发布现有 work/lyra-capabilities.json")
    parser.add_argument("--force", action="store_true",
                        help="明确接受门禁错误并强制发布（仍保留诊断证据）")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.workers <= 0 or args.max_depth <= 0:
        parser.error("--timeout、--workers、--max-depth 必须是正整数")
    if args.publish_evidence and args.evidence_only:
        parser.error("--publish-evidence 与 --evidence-only 不能同时使用")

    previous = load_json(ENGINE_MANIFEST, {"commands": []})
    if args.publish_evidence:
        candidate = load_json(EVIDENCE_MANIFEST, {})
        if not candidate.get("commands") or not candidate.get("discovery"):
            parser.error("现有 work/lyra-capabilities.json 不是可发布的动态枚举证据")
    else:
        probe = OfficialHelpProbe(workspace=args.workspace, timeout=args.timeout,
                                  reuse_evidence=args.reuse_help_evidence)
        candidate = discover_commands(probe, previous=previous, max_depth=args.max_depth,
                                      workers=args.workers)
        atomic_write_json(EVIDENCE_MANIFEST, candidate)
    errors = validate_candidate(candidate, previous=previous)

    discovery = candidate["discovery"]
    ok = sum(1 for spec in candidate["commands"] if spec.get("help_state") == "ok")
    print(f"探测 {discovery['probed']} 个 help 节点，发现 {candidate['count']} 条叶命令，"
          f"成功取参 {ok} 条，失败 {len(discovery['failures'])} 条，"
          f"官方不支持 {len(discovery.get('unsupported', []))} 条")
    print(("正在复核现有诊断证据 " if args.publish_evidence else "诊断证据已写入 ") +
          str(EVIDENCE_MANIFEST))
    if errors:
        print("发布门禁未通过：", file=sys.stderr)
        for error in errors:
            print("- " + error, file=sys.stderr)
        if not args.force:
            print("未改写 engine 清单；复核后可使用 --force 显式接受。", file=sys.stderr)
            return 2
    if args.evidence_only:
        print("--evidence-only：未改写 engine 清单")
        return 0 if not errors else 2
    atomic_write_json(ENGINE_MANIFEST, candidate)
    print("已原子发布到", ENGINE_MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
