# codex-workbuddy-gateway Windows 与三方沟通审计

日期：2026-10-22。方法：使用 agent-reach 的 GitHub CLI 路线核查主线、Windows fork、分支、issue、PR 与代码；后台研究员完成源码审计，主代理另在独立目录安装构建依赖并执行本机诊断和 Windows 回归。未读取客户端密钥、未修改客户端配置、未注册服务或发送业务任务。主机验证结果见末节。

上游固定提交：`fbaaa2ef6d6cb59f48b953a1f27058202a81553f`。源码目录：`C:\Users\Administrator\.agent-reach\research\codex-workbuddy-gateway-20261022`。

Windows fork 固定提交：`e68e3bce8c7fd577b93191add90beb74481dc136`。源码目录：`C:\Users\Administrator\.agent-reach\research\codex-workbuddy-gateway-windows-20261022`。

## 结论

原项目不是三方共享群聊平台，而是 Codex 调用执行器的任务桥接器。原主线不能通过配置直接在 Windows 跑完整桌面队列。找到已有 Windows fork，已实际加入 Windows 启动器、进程/端口核对与计划任务服务，可作为 Codex ↔ WorkBuddy 的现成验证对象。这个 fork **没有移植 DeepSeek 插件，也没有增加三方群聊和共享 transcript**，因此不能满足“同一对话随时指定三者谁回答、另外两者自动具有完整历史”的完整要求。

## 现有平台能力与语义

1. 主线 README 直接说明首期只有 WorkBuddy，DeepSeek Harness 桥接独立保留、尚未接入聚合接口。[README L3](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/README.md#L3)
2. 源码确实只创建 `WorkBuddyProvider`，以单元素数组注册给 HubEngine，没有 CodexProvider 或 DeepSeekProvider。[platform/cli.ts L43-L44](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/cli.ts#L43)
3. 未实现 provider 会被 engine 明确拒绝，不能在 .env 或 JSON 中写一个名字就接入。[engine.ts L48-L51](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/engine.ts#L48)
4. UI 是新建任务/成果/事件/返工的工作台。执行器下拉菜单只有 WorkBuddy，运行时根据真正注册的 providers 生成；没有 @三者、聊天消息序列或共享 thread 的实现。[ui.ts L9](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/ui.ts#L9)、[L27-L30](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/ui.ts#L27)
5. HTTP/MCP 接收 provider、task、workspace、单一 provider sessionId、model 等字段；没有 conversation/thread 对象或 messages 数组、历史广播目标。[contracts.ts L3-L27](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/contracts.ts#L3)
6. 本机存储是 hub_runs 和 hub_events；源码注释明确“平台记录不会替代 provider 自己的执行历史”。[store.ts L6-L15](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/store.ts#L6)
7. WorkBuddy 派发 prompt 是目标、目录、约束、验收、反馈；DeepSeek 也是同类任务封装。这不是把 Codex 整段对话、另一执行器工具日志、系统提示自动镜像给所有人。[coordinator.ts L149-L150](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/coordinator.ts#L149)、[deepseek-coordinator.ts L127-L128](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/deepseek-coordinator.ts#L127)
8. 返工保持各执行器原有会话，可复用该执行器自己的历史；“同一个 WorkBuddy 会话继续执行”不能等同于三种客户端共享一个会话。[coordinator.ts L101-L102](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/coordinator.ts#L101)、[deepseek-coordinator.ts L83-L93](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/deepseek-coordinator.ts#L83)
9. 官方限制说明尚无自动会话轮换或上下文成本管理，执行器事件主要来自主动报告，不保证完整工具轨迹。[AGENT_HUB.md L124](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/docs/AGENT_HUB.md#L124)

因此，“共享缓存”需要拆开：

- 共享项目文件：可通过统一 workspace 达成；仍需 agent 实际读取文件。
- 共享任务目标、回报、成果路径：项目已有此能力。
- 三方自动共享完整聊天历史：项目当前未实现。
- 模型服务商的 prompt cache / 运行时 KV cache：项目没有跨平台缓存协议，不应声称可共享，也不应把简报截断误称缓存命中或 token 费用节省。

## 主线 Windows 硬阻塞

- WorkBuddy 端口和进程校验硬编码 `/usr/sbin/lsof`、`/bin/ps`；原生退出使用 macOS 的 `osascript` 和 `com.tencent.workbuddy.mac`。[native-desktop-trigger.ts L150-L218](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/native-desktop-trigger.ts#L150)
- 领取 helper 追溯父进程使用 Unix ps，Windows 即使手动启动 helper 仍会受阻。[desktop-queue.ts L23-L38](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/desktop-queue.ts#L23)
- WorkBuddy 服务安装显式要求 macOS launchd。[service-cli.ts L58-L59](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/service-cli.ts#L58)
- Hub install 同样显式拒绝非 darwin。[platform/cli.ts L65-L71](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/cli.ts#L65)
- 所有 bin 启动器都是 /bin/sh；可通过直接 node dist 规避启动器，但规避不了以上业务代码。[bin/workbuddy-gateway](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/bin/workbuddy-gateway)
- ensureWorkspace 首次自动调用 installService，因此不是只改可执行文件路径就能绕过。[workspace-manager.ts L46-L48](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/workspace-manager.ts#L46)

旧 desktop-acp 兼容路线在源码上使用本机交互式 session 注册及 HTTP ACP，未见同样的 macOS 硬编码，可作为极小范围的“已有 live session 是否存在”探测；但是 Hub WorkBuddyProvider 拒绝非 desktop-queue，该兼容路线也不能解决 DeepSeek 与三方历史问题。[acp-live.ts L89-L137](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/acp-live.ts#L89)、[platform/workbuddy.ts L19](https://github.com/dudu555-djiao/codex-workbuddy-gateway/blob/fbaaa2ef6d6cb59f48b953a1f27058202a81553f/src/platform/workbuddy.ts#L19)

## 找到现成 Windows fork

[wuxuanren2008-ux/codex-workbuddy-gateway-windows](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows) 基于上游 v0.7.0 `5a41c45`，包含三次额外提交，最后为 e68e3bc。另六个 fork 头部均与上游已知提交一致，没有额外 Windows 功能；上游查询时仅 main、零 issue、零 PR，未发现其他合并/待合并 Windows 路线。[fork 网络 API](https://api.github.com/repos/dudu555-djiao/codex-workbuddy-gateway/forks)、[分支 API](https://api.github.com/repos/dudu555-djiao/codex-workbuddy-gateway/branches)、[来源声明](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/UPSTREAM.md#L7)

Windows fork 已有：

- `scripts/launch.mjs` 读取 .env、保持字面参数、映射 gateway/doctor/worker/service/hub/hub-mcp，避免需要 POSIX shell。[launch.mjs L5-L15](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/scripts/launch.mjs#L5)
- Windows 可执行文件/配置目录的覆盖项 `WORKBUDDY_CLI_ELECTRON`、`WORKBUDDY_CONFIG_DIR`。[config.ts L62-L71](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/src/config.ts#L62)
- Windows 计划任务服务和受限、隐藏的 PowerShell supervisor；需要当前用户已登录。[WINDOWS.md L38-L49](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/docs/WINDOWS.md#L38)
- Codex 标准 MCP 注册命令已提供，不需另造平台。[WINDOWS.md L18-L28](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/docs/WINDOWS.md#L18)
- 作者声明在 Node24.19 / WB5.7.6 进行小文件、同会话修改、服务重启后的继续派工验证；这些是作者的一台机器结果，尚不是本用户机器或视频实测。[WINDOWS-VALIDATION.md L3-L36](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/docs/WINDOWS-VALIDATION.md#L3)
- 最新提交的 Windows desktop regression Actions 为 success。[CI 运行](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/actions/runs/38156182157)

Windows fork 仍然只注册 WorkBuddyProvider。[fork platform/cli.ts L44-L45](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/src/platform/cli.ts#L44)

## DeepSeek：Windows fork 没有修复

1. 插件 installer 明确仅 macOS。[installer L21](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/scripts/install-deepseek-plugin.mjs#L21)
2. 插件 transport 启动时发现 `process.getuid` 非函数立即抛出 unsupported-platform，Windows 必然受阻；它还依赖 Unix UID、chmod 和私有 AF_UNIX socket。[transport L44-L53](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/deepseek-plugin/transport.mjs#L44)、[L128-L131](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/deepseek-plugin/transport.mjs#L128)
3. 原生 API 插件把 session-controller 版本严格固定为 0.2.0-rc.2，非该版本明确抛出 unsupported-version，不能只声称可尝试新版。[adapter.mjs L7-L25](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/deepseek-plugin/adapter.mjs#L7)
4. Root 另行确认本机 Harness App 是 0.2.1-rc.2；若其 session-controller 版本随 App 为 0.2.1-rc.2，会触发上述不匹配。应以其实际包版本为最终证据，不能仅据 App 显示版本替代 controller 版本。
5. DSH桥接在工作台之外，是 Codex的另一个MCP；原生会话控制器只提供 health/sessions/create/session/prompt/events/cancel，不是跨平台 transcript 服务器。[adapter.mjs L8](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/deepseek-plugin/adapter.mjs#L8)

WSL并不能仅凭一项配置解决：Windows 原生 Host 插件仍跑 Windows Node，getuid 仍不存在；即便另起 Linux Host，也不再是用户同一 Windows 原生桌面会话，且 WorkBuddy 的进程路径和本机剪映资源仍需处理。此为根据以上架构得出的推断。

## 不改源码时的最小验证建议

完整目标当前不成立；不要为了展示“已打通”去安装上游 macOS 服务、移除 getuid 检查、复制模型密钥或把 DeepSeek API 当 Harness。

若用户接受先实现双端：使用该 Windows fork 的现成配置，固定 e68e3bc；只覆盖真实 WorkBuddy.exe 路径与历史目录，保持 `WORKBUDDY_BACKEND=desktop-queue`。先构建和针对 Windows 的回归；再由 root 在独立测试目录验证：Codex 生成随机 nonce → WorkBuddy 原生会话实际创建文件 → Codex只读验收 → 同会话返工保留 nonce → 服务重启后恢复相同 session。区分 queued、claimed、completed、accepted。不要在本轮仅研究任务中声称已经完成安装和实机闭环。

示例配置只说明键名，配置目录应由本机实际发现结果确定：

```ini
WORKBUDDY_BACKEND=desktop-queue
WORKBUDDY_CLI_ELECTRON="D:\刘宇钊\软件\WorkBuddy\WorkBuddy.exe"
WORKBUDDY_CONFIG_DIR="C:\Users\Administrator\<实际WorkBuddy历史目录>"
```

若完整三方群聊/上下文同步不可妥协，应结束对这个项目的配置尝试，按“已有支持三执行器与 shared transcript 的平台”继续选型，而非在此 fork 上偷偷开发新聊天层。未来作者若同时交付 DSH Windows transport、兼容版本支持、DeepSeekProvider/CodexProvider、统一conversation store和历史投递策略，才具备再次验证完整目标的基础。

## 许可证范围

上游未提供 LICENSE，GitHub API license=null；Windows fork 的 MIT 仅覆盖其明确列出的新增文件，没有把上游完整工程变成 MIT。此处只记录仓库事实，不据此推导法律结论或要求额外审批。[UPSTREAM.md L11-L13](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/UPSTREAM.md#L11)、[Windows新增许可范围](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/LICENSE-WINDOWS-ADDITIONS.md#L3)

## 补充：两个现成 MCP 并列，由 Codex 一个对话主持

另行只读审计 [FuJackGao/dsh-collab](https://github.com/FuJackGao/dsh-collab)，固定提交 `aa811e2c886a6e98e184729c63ff04449c381cf8`。源码目录 `C:\Users\Administrator\.agent-reach\research\dsh-collab-20261022`。项目 MIT，未运行或安装插件。

可以把“一个入口由你指定执行者”与“真正三方完整历史自动同步”分开交付：在 Codex 注册 WorkBuddy Windows MCP 和 DSH Collab MCP，用户在 Codex 对话内说“这条让 WorkBuddy 回答 / 这条让 DSH 回答 / 这条 Codex 回答”，Codex选择相应工具，将必要上下文写进任务参数、把原始回复和来源带回当前对话。这是现成MCP配置加主持agent执行规约，不需要开发新平台。Codex通过摘要注入实现上下文传递；另外两端不会自动具有完整原始聊天，也不会被动同步每条消息。原生回答先回工具，再由Codex展示，不能把展示气泡理解为三个客户端都连接到同一原生thread。

Windows fork 已提供可直接作为 Codex MCP command/args 的 Node 启动器，文档给出两个 MCP 注册命令；传 `workbuddy_send_task.objective` 或 Hub `task` 可以附带这次要求的摘要。[Windows注册说明 L18-L28](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/docs/WINDOWS.md#L18)、[WorkBuddy MCP send schema](https://github.com/wuxuanren2008-ux/codex-workbuddy-gateway-windows/blob/e68e3bce8c7fd577b93191add90beb74481dc136/src/server.ts#L47)

DSH Collab 的 MCP 本身是单文件、零依赖 Node，默认stdio；`dsh_task` 接收 instruction/cwd/lane/model/wait/timeoutSec，返回执行结果。Codex可把摘要放在instruction。[MCP工具契约 L14-L33](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/mcp/dsh-mcp.mjs#L14)、[调用与回传 L108-L119](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/mcp/dsh-mcp.mjs#L108)

它不使用上游的 getuid/AF_UNIX 插件；插件走 Host webServer HTTP，默认 `http://127.0.0.1:3080`。默认目录、路径规范化明显面向Windows。源码未见固定0.2.0版本锁，因此值得在本机0.2.1环境做服务能力匹配核对，但“无版本锁”不等于已经兼容。[HTTP目标](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/mcp/dsh-mcp.mjs#L7)、[Windows目录规范化 L92-L97](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/harness/dsh-bridge.mjs#L92)

但后端必须安装到真实DSH Host composition：复制插件、在对应profile cordis.patch.yml插入配置并重载。插件依赖 `@deepseek-ai/dsh-tools`、webServer/agents/subagents/tools服务，调用agents.create和subagents.startContinuable；与单纯配置一个外部MCP不同，不能只装Codex侧就运行。[Host依赖 L16-L31](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/harness/dsh-bridge.mjs#L16)、[创建owner L236-L244](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/harness/dsh-bridge.mjs#L236)、[创建编码子代理 L289-L305](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/harness/dsh-bridge.mjs#L289)

该方案运行的是 Harness管理的专门编码/评审子代理，不能承诺接管用户正在用的某个DSH桌面主对话。WorkBuddy端继续原生绑定会话。二者可共享项目文件、由Codex转述重要信息，但不是对称三人群聊。

DSH Collab README 所说“跨任务记忆”也有范围：Host历史仅最近40条协作指令和汇报，注入时每条截取前2000字符；CLI task.mjs有NDJSON历史存储与随请求发送，但MCP实现提交时只发送instruction/cwd/lane/model，不传history。没有自动读取当前Codex完整对话或WorkBuddy历史的逻辑。[Host历史 L163-L182](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/harness/dsh-bridge.mjs#L163)、[MCP提交 L108-L115](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/mcp/dsh-mcp.mjs#L108)、[CLI历史附带 L178-L180](https://github.com/FuJackGao/dsh-collab/blob/aa811e2c886a6e98e184729c63ff04449c381cf8/codex-plugin/plugins/dsh/skills/dsh-collab/scripts/task.mjs#L178)

故更新建议：如果“在一个Codex对话内指定谁执行并自动传递必要上下文”可接受，Windows fork + DSH Collab 是值得验证的现成组合，不必另造平台。如果“另外两个平台始终完整共享同一历史/系统与工具上下文”是硬需求，此组合仍未满足，须明确说明能力差距。禁止把这个组合在未实机安装和往返测试前写成已打通。


## 本机验证结果（主代理，2026-10-22）

- Node.js v24.21.0；Codex CLI 0.163.0-alpha.11。
- WorkBuddy 5.8.3：`D:\刘宇钊\软件\WorkBuddy\WorkBuddy.exe`，运行中；历史/设置目录 `C:\Users\Administrator\.workbuddy`。
- DSH 桌面 0.2.1-rc.2：`D:\DeepSeekHarness`，本次未运行，`dsh` 不在 PATH。App 版本不能替代内部 session-controller 包版本的证据。
- 未发现 18491 CDP 监听，18488 的 `/json/version` 不是可用 CDP；旧 ACP 注册仅一份，缺 endpoint/url、PID 已失效。

实际验证：

1. 在隔离的 Windows fork 目录执行 `npm ci --ignore-scripts --no-audit --no-fund` 和 `npm run build`，依赖安装、TypeScript 构建通过。
2. 仅对诊断命令设置 `WORKBUDDY_BACKEND=desktop-queue`、上述真实应用路径及配置目录，执行 `node scripts/launch.mjs doctor`。Node、Windows、应用路径、桌面路线检查通过；但 `ok:false, online:false, ready:false, persistentServiceConnected:false, connectionStatus:offline, taskSent:false`。识别到安装不等于已连接。
3. 现成 `npm run test:windows` 报告 95 项、92 通过、3 失败。失败均为 `test/platform.test.ts` 临时目录清理 hook 的 `ENOTEMPTY`。该测试子进程未正常退出；超过两分钟后核对 PID、父进程及精确测试路径，仅停止该测试子进程，运行器随后退出。不能声称回归全通过，也不能将清理失败推定为业务连接失败。
4. 直接导入上游纯 Node `deepseek-plugin/transport.mjs` 并调用 `startTransport({})`，在目录和服务创建之前实际返回 `platform:win32, getuid:undefined, code:bridge/unsupported-platform`，消息为 `This bridge requires Unix filesystem ownership checks`，复现 Windows 平台硬阻塞。
5. 未重启或结束 WorkBuddy，未启动 DSH Host，未安装服务/计划任务，未注册 MCP，未修改客户端配置、会话、模型或凭据。测试进程已退出，原剪映实现文件未修改。

测试日志：`gateway-windows-tests-20261022.log`（历史本机证据：`%USERPROFILE%/.agent-reach/research/gateway-windows-tests-20261022.log`，未随源码分发）。

## 对共享缓存的判断

共享对话上下文需要统一消息历史和跨执行器的历史投递。这个 gateway/Windows fork 保存任务、反馈与结果，没有自动读取当前 Codex 完整对话并同步给另外两个执行器。

Codex 同一对话作为入口，配上现成 WorkBuddy Windows MCP 与另一个现成 DSH MCP，可按接口设计派给指定执行器、显式传递必要摘要并拿回结果；本机三方组合未完成实测。这是上下文转述，各运行时仍保持独立会话，不等于三端拥有同一份完整历史。

服务端 prompt/KV cache 是另一层。OpenAI 的复用要求匹配模型、上下文前缀及缓存作用域；DeepSeek也有自己的前缀缓存。本地 gateway 无法把两个服务的模型 KV 状态合为一份。同样文字的共享不等于计算缓存共享；同供应商、同模型、同前缀的实际命中应以 usage 指标判断，不能承诺固定节费比例。

一手依据：[OpenAI Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)、[DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache/)、[Codex App Server](https://learn.chatgpt.com/docs/app-server)。

采用结论：现成 Windows fork 是可继续验证的 WorkBuddy 通道，当前仍无法仅靠配置满足三方共享对话的完整目标。在“不另造平台”的范围内，本轮未新增聊天前端、conversation store、历史广播层或移除原插件的平台/版本校验。

