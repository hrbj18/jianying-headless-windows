import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { appendFileSync, writeFileSync } from "node:fs";

const bridge = globalThis[Symbol.for("custom-agent.runtime-sandbox-bridge")];
if (!bridge) throw new Error("剪映官方 VMSDK bridge 未加载");

const input = JSON.parse(Buffer.from(process.env.JY_DRAFTEDITING_INPUT_B64, "base64").toString("utf8"));
const resultPath = process.env.JY_DRAFTEDITING_RESULT;
// 逐步留痕：官方 bridge 调用是同步阻塞的，卡住时兜底定时器不会触发。
const progressPath = resultPath + ".progress";
function note(stage, extra) {
  try {
    appendFileSync(progressPath, JSON.stringify({ stage, at: Date.now(), ...extra }) + "\n");
  } catch {
    // 留痕失败不影响主流程。
  }
}
note("start", { args: input.args, cwd: input.cwd, pid: process.pid });
const app = input.installDir;
const runtime = `${app}\\Resources\\canvas_agent\\runtime`;
const vmId = `draftediting-${Date.now()}`;
const sandboxSessionId = `session-${randomBytes(8).toString("hex")}`;
const token = randomBytes(32).toString("hex");
const endpoint = `\\\\.\\pipe\\jianying-draftediting-${process.pid}-${Date.now()}`;
const events = [];
const unsubscribe = bridge.subscribeEvents((event) => events.push(event));
const policy = JSON.parse(bridge.basePolicy().fullConfig);
// 官方沙箱规则形状为 { file_path, process_name:"", type }；缺少 process_name
// 会让规则不匹配任何进程。只读规则先于读写规则加入，与官方组装顺序一致。
const declared = new Set((policy.rules || []).map((rule) => rule.file_path));
for (const [paths, type] of [[input.readOnlyPaths, "read_only"], [input.readWritePaths, "read_write"]]) {
  for (const path of paths || []) {
    if (declared.has(path)) continue;
    declared.add(path);
    policy.rules.push({ file_path: path, process_name: "", type });
  }
}
note("policy", { rules: policy.rules.length });

// 兜底：无论桥接调用卡在哪一步，都要留下证据，不能让调用方只看到超时。
const budget = Math.max(20000, Number(input.timeoutMs) + 20000);
const guard = setTimeout(() => {
  try {
    writeFileSync(resultPath, JSON.stringify(
      { error: `官方桥接在 ${budget}ms 内未完成`, stage: "worker-guard-timeout", events }, null, 2), "utf8");
  } catch {
    // 结果文件不可写时只能放弃留痕。
  }
  process.exit(3);
}, budget);
guard.unref?.();

let socket;
let buffer = "";
let resolveReady;
let resolveResponse;
const ready = new Promise((resolve) => (resolveReady = resolve));
const response = new Promise((resolve) => (resolveResponse = resolve));
const server = createServer((client) => {
  socket = client;
  client.setEncoding("utf8");
  client.on("data", (chunk) => {
    buffer += chunk;
    for (;;) {
      const pos = buffer.indexOf("\n");
      if (pos < 0) break;
      const line = buffer.slice(0, pos).trim();
      buffer = buffer.slice(pos + 1);
      if (!line) continue;
      const message = JSON.parse(line);
      if (message.type === "ready") resolveReady(message);
      if (message.type === "response" && message.requestId === "command-1") resolveResponse(message);
    }
  });
});
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(endpoint, resolve);
});

let finalResult;
let created;
try {
  const workerEnv = {
    CUSTOM_AGENT_SANDBOX_ENDPOINT: endpoint,
    CUSTOM_AGENT_SANDBOX_TOKEN: token,
    CUSTOM_AGENT_SANDBOX_SESSION_ID: sandboxSessionId,
    CUSTOM_AGENT_SANDBOX_VM_ID: vmId,
    CUSTOM_AGENT_SANDBOX_WORKER_GENERATION: "1",
    CUSTOM_AGENT_SANDBOX_POLICY_VERSION: "1",
    CUSTOM_AGENT_SANDBOX_OWNER: "0",
    CUSTOM_AGENT_PROCESS_NAME: "hub-agent-tool-worker",
    CUSTOM_AGENT_LYRA_CLI_COMMAND: `${app}\\lyra-cli.exe`,
  };
  const payload = Buffer.from(JSON.stringify({
    executablePath: `${app}\\bun-packaged-server.exe`,
    environment: Object.entries(workerEnv).map(([name, value]) => ({ name, value })),
  }), "utf8").toString("base64");
  const bootstrap = [
    "$ErrorActionPreference = 'Stop'",
    `$payloadJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${payload}'))`,
    "$payload = $payloadJson | ConvertFrom-Json",
    "foreach ($entry in @($payload.environment)) { [Environment]::SetEnvironmentVariable([string]$entry.name, [string]$entry.value, [EnvironmentVariableTarget]::Process) }",
    "$startInfo = New-Object System.Diagnostics.ProcessStartInfo",
    "$startInfo.FileName = [string]$payload.executablePath",
    `$startInfo.Arguments = '\"${runtime}\\hub-agent-tool-worker.mjs\"'`,
    "$startInfo.UseShellExecute = $false",
    "$targetProcess = [System.Diagnostics.Process]::Start($startInfo)",
    "$targetProcess.WaitForExit()",
    "exit [int]$targetProcess.ExitCode",
  ].join("\n");
  note("create-process:begin", { vmId });
  created = await bridge.createProcess({
    vmId,
    fullConfig: JSON.stringify(policy),
    executablePath: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    arguments: ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", bootstrap],
    environment: [],
    currentDirectory: input.cwd,
    inheritParentEnvironment: true,
    inheritHandles: false,
  });
  note("create-process:done", { processId: created?.processId, success: created?.success });
  await Promise.race([
    ready,
    Bun.sleep(15000).then(() => { throw new Error("官方 worker 启动超时"); }),
  ]);
  note("worker-ready");
  const now = Date.now();
  socket.write(`${JSON.stringify({
    type: "request",
    protocolVersion: 2,
    requestId: "command-1",
    sandboxSessionId,
    runId: "draftediting-run",
    toolCallId: "draftediting-command",
    workerGeneration: 1,
    policyVersion: 1,
    sentAt: now,
    deadline: now + input.timeoutMs,
    request: {
      sandboxSessionId,
      runId: "draftediting-run",
      toolCallId: "draftediting-command",
      policyVersion: 1,
      toolId: "__sandbox_process_run",
      input: {
        command: `${app}\\lyra-cli.exe`,
        args: input.args,
        cwd: input.cwd,
        env: input.env || {},
        timeoutMs: input.timeoutMs,
        label: "DraftEditing:lyra-cli",
        ownerRunId: "draftediting-run",
      },
      context: {},
    },
  })}\n`);
  const responseMessage = await Promise.race([
    response,
    Bun.sleep(input.timeoutMs + 15000).then(() => { throw new Error("官方命令执行超时"); }),
  ]);
  finalResult = { created, responseMessage, events };
  socket.write(`${JSON.stringify({
    type: "shutdown",
    protocolVersion: 2,
    requestId: "shutdown-1",
    sandboxSessionId,
    workerGeneration: 1,
  })}\n`);
  await Bun.sleep(300);
} catch (error) {
  finalResult = { created, error: String(error), code: error?.code, stack: error?.stack, events };
} finally {
  writeFileSync(resultPath, JSON.stringify(finalResult, null, 2), "utf8");
  unsubscribe?.();
  socket?.destroy();
  server.close();
  await bridge.killProcess(vmId).catch(() => {});
  await Promise.race([bridge.shutdown().catch(() => {}), Bun.sleep(3000)]);
  process.exit(0);
}
