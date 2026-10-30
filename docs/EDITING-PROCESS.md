# 剪辑过程文字小窗

默认使用附着剪映的原生桌面文字小窗，不需要浏览器。群聊顶部“剪辑文字窗”调用同一本机入口。
小窗以 Win32 owned window 绑定已验证剪映进程的主窗口，只移动和修改自己的窗口；跟随剪映位置，剪映最小化或切到其它应用时隐藏，回到剪映前台时显示。
默认位于剪映右上方，可拖动标题栏调整相对位置，支持收起/展开、关闭和暂停后续步骤；只在剪映上方显示，不设系统全局置顶，不抢键盘焦点。
读取窗口位置和所属进程属于此桌面功能的运行逻辑；无鼠标键盘模拟、桌面截图、UI 自动化，也不修改剪映 ABI、DLL 或原生窗口状态。

```powershell
.\jianying.ps1 process window
.\jianying.ps1 process window-status
.\jianying.ps1 process window --compact
.\jianying.ps1 process window --expand
.\jianying.ps1 process window --close
```

默认跟随最新 run；`window --run '<run UUID>'` 可固定某轮。相同进程只有一个小窗，重复打开不创建多个实例。
已完成的动作显示最近记录和“待命”，不冒充正在剪辑。没有动作时不唤醒 agent。编辑器进程退出后小窗结束，下一次需要显示时再次调用正常入口。
`window-status` 核对真实 PID/创建时间、窗口句柄、Win32 owner、是否可见与隐藏原因。`editor-minimized`、`editor-in-background` 是跟随隐藏，并非启动失败。

`http://127.0.0.1:5178/editing` 保留为可选历史详情页，视频对比在该页；文字小窗独立读本地记录，不依赖网页/Vite 服务。

## 执行者工作方式

新剪辑任务创建一个 run，先记录简洁的剪辑依据（素材观察、取舍、预期效果），再将每一步现有命令放进 `process execute`。
展示可核对的剪辑结论、证据和参数，不输出私密推理过程。旧回执只能作为历史导入，不补写当时未记录的理由，不重放旧操作。

```powershell
.\jianying.ps1 process create --title '本轮剪辑' --objective '这次要解决的具体问题'
.\jianying.ps1 process window
.\jianying.ps1 process note --run '<run UUID>' --stage selection --title '镜头取舍' --text '已查看哪些素材，选择哪个区间，原因与预期效果'
.\jianying.ps1 process execute --run '<run UUID>' --spec 'C:\JianyingProcess\work\step.json'
.\jianying.ps1 process inspect --run '<run UUID>'
```

`step.json` 的例子（ID 为本次业务操作的新 UUID；同一步重查沿用原 ID）：

```json
{
  "id": "68a276c8-cd37-4a48-8718-71db1cc100c5",
  "title": "检查人物反应镜头",
  "stage": "review",
  "reason": "检查切点后人物表情是否完整，字幕是否遮挡主体。",
  "changes": [],
  "args": ["preview", "--build", "C:\\job\\build", "--out", "C:\\job\\preview-new", "--at", "2.2"]
}
```

阶段：`plan / selection / rough / refine / subtitle / sound / review / delivery`。
`changes` 可记录 `{ "label": "字幕字号", "before": 8.2, "after": 7.6 }`。`args` 为现有 CLI 参数数组，无 shell 拼接。
`agent live` 参数同原调用说明，真实 draft/session/request ID、原生命令锁和验收要求继续生效。
构建后读取实际 plan 生成时间线；preview/export 成功回执将真实媒体及 SHA256 登记到过程页。
技术验证、实际执行和审美评审分开记录。画面判断须查看实际原生帧/成片后再写审片结论。

## 暂停与意见

页面“本步结束后暂停”不会杀死当前原生操作。当前步骤完成后，后续 `process execute` 在派发前检查暂停标志。
提交调整意见只写入当前 run；未处理意见同样阻止下一步。恢复仅允许下一次显式执行，不会唤醒任何 agent。
执行者读取 `process inspect`，处理具体意见并记入新的计划，再明确确认：

```powershell
.\jianying.ps1 process acknowledge --run '<run UUID>' --note-id '<实际意见 UUID>' --summary '已处理的具体意见、后续动作及影响范围'
```

确认之后仍须通过新动作回执核对结果，不能把“已处理意见”当作“修改已执行”。不要在无人处理时冒充自动继续。
操作已完成时同 ID 不重复执行；派发中、运行中、失败或不确定的旧动作拒绝自动重试。先检查原始回执、现有草稿及进程状态。
心跳超过 15 秒未更新显示“回执待核对”，不推断任务成功，不重派发。

## 文件与本机服务

记录位于本项目 `.local/editing-process/<run UUID>/`，与 Codex 私有记忆分开。真实渲染和媒体留在各自工作目录。
原生小窗实例锁、控制消息和状态位于 `.local/editing-overlay/`，GUI 运行时为项目已有 Python/Tk。无需新平台或外部依赖。
Agent Group 现有 Vite 服务的同源 `/api/editing/window` 只调用固定的 `process window`，不接受自定义命令或文件路径；其它 `/api/editing/` 接口继续提供可选历史详情。
只服务已登记、文件大小和 SHA256 均匹配的 MP4/PNG/JPEG；视频支持 Range。页面不能指定任意磁盘路径或执行命令。
没有通过 `process` 接入的旧命令不会自动出现在过程页。后续剪辑应遵循本工作方式；历史结果明确标注历史。
