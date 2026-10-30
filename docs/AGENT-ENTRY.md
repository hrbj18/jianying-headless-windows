# Codex / WorkBuddy 公共入口

本机唯一正式入口：`D:\刘宇钊\codex_work\jianying-headless-windows\jianying.ps1`。
项目可位于中文目录，运行环境固定为旁边的 `.venv`；命令从任何工作目录调用均可。
WorkBuddy 的旧 worktree 仅作历史源码参考，视频任务调用上面的正式入口。

## 1. 开始任务

需要向用户展示剪辑过程时，先按 [剪辑过程记录](EDITING-PROCESS.md) 创建本轮 run，并调用 `process window` 显示附着剪映的原生文字小窗，无需网页。
先记录可核对的剪辑依据，后续通过 `process execute` 包装本入口已有命令，展示真实计划、参数、回执及原生预览。
每一步派发前检查页面的暂停和待处理意见；不补写旧任务理由，不重放旧任务。

```powershell
$entry = 'D:\刘宇钊\codex_work\jianying-headless-windows\jianying.ps1'
& $entry agent --client workbuddy doctor
& $entry agent capabilities
```

Codex 将 `--client` 改成 `codex`。该字段是审计标签，不证明命令真的来自某个客户端。
真实双客户端验收必须保存各自宿主的实际命令与结果，不能在一个终端改标签冒充。
本机完整验收工具为 `tools/verify_agent_session.py`：只操作明确指定的 `AgentIntegration_1022`
8秒专用草稿。`--out` 由脚本自行建立，调用前保留该路径不存在。

`doctor` 必须返回 `ready`：检查精确剪映构建、官方签名、DLL指纹、公共Python依赖、
实际含 `windows.h` 的编译/链接、原生桥校验和、草稿与索引路径。ASR凭据只报告是否可用，
不发送音频、不打印密钥；需要新转写时另读 WINDOWS-MATERIAL-ANALYSIS.md 并核对授权。
缺依赖时使用本项目Python按错误提示安装需求文件，再运行体检；避免临时换系统Python或改编译函数。

## 2. 选择当前编辑页

```powershell
& $entry agent --client workbuddy live status
& $entry agent --client workbuddy live segments
```

`report` 给出真实 `draft_id`、路径、主时间线、`session`、时长和预览时间码。
`segments` 给出真实 `segment_id` / `track_id`。用户明确指定草稿优先；否则以当前页面为目标。
明确目标与当前页面不一致时停止该修改，先报告目标不一致；后台其它草稿可独立构建与导出。
重新进入草稿后剪映可能重分配草稿ID，以新status为准。

窗口未打开或仍在首页时，`live status` 会拒绝，不会自行启动窗口或猜草稿。
编辑命令既不切换工程，也不使用磁盘覆盖后重开来刷新。人类点图标显示窗口后，编辑照常同步；
日常结束时最小化，保持工程会话存活。

## 3. 实时修改、历史与保存

```powershell
$draft = '<status.report.draft_id>'
$session = '<status.report.session>'
$segment = '<segments中的真实ID>'
$request = [guid]::NewGuid().ToString()
& $entry agent --client workbuddy live trim --draft-id $draft --session $session --segment-id $segment --seconds 4 --request-id $request
& $entry agent --client workbuddy live undo --draft-id $draft --session $session --request-id ([guid]::NewGuid().ToString())
& $entry agent --client workbuddy live redo --draft-id $draft --session $session --request-id ([guid]::NewGuid().ToString())
& $entry agent --client workbuddy live save --draft-id $draft --session $session
```

每次**新的修改**使用新UUID；重发同一业务请求沿用原UUID。已确认的相同请求返回
`already_completed:true, dispatched:false`；同ID不同内容或先前结果不确定均拒绝。
两个客户端共享进程外命令锁、连接状态和审计目录，不能同时写同一草稿。
操作由当前会话的原生Qt模型提交，使用剪映自己的撤销/重做并自动保存；`save` 是保存回读确认，
不是模拟Ctrl+S。成功至少满足 `confirmed`、同一会话、根/主时间线一致和预览时长匹配。
业务动作数不等于原生历史条目数。首次LUT修改实测包含资源迁移、强度修改两条记录；
undo/redo每次操作一条，必须按实际完整时间线状态确认，不凭一次undo未恢复全部字段推断不可撤销。

裁剪目前只接受已验证的单视频草稿，或明确选中的独立静音副画面；一般主轨重排需离线构建。
其它已迁入命令：`split/delete/subtitle/import/append/audio-fade/audio-volume/audio-keyframe/move`，
以及已有资源的 `filter-value/remove-filter/remove-effect/transition-duration`，参数以各自 `--help` 为准。
跨轨移动限定已有、未锁定的副视频轨和简单1倍速静音片段，帧对齐、无重叠、不扩展总时长。
音量关键帧只调整已有点；添加任意效果、登录算法和H265尚不属于该实时入口。
已有自定义速度曲线可用 `speed-controls/curve-gradient` 修改原生斜率；HSL 用
`color-controls/hsl`，本地双类别声音链用 `audio-controls/audio-dsp`。声音两节点须具有各自
唯一且稳定的 `constant_material_id`；旧空标识会使不同类别的滑杆读到同一参数槽，实时入口
明确拒绝该情况。五项普通控件不代表五项独立关键帧自动化。实际验收范围见
[高级画面与声音](WINDOWS-NATIVE-AV.md)。
多轨曲线斜率修改已在30秒8视频/8音频/3字幕工程实际验证，限定选中静音视频、独立曲线、
不含片段动画且保持全部片段时间范围。它不自动重定时对白、字幕或其它音轨。

降噪用`denoise-controls/denoise-switch --enabled true|false`，同样要求真实draft、session、
音频片段和新请求UUID。GUI只提供开关；正常切换会采用剪映的mode1/全局rate，不能冒充强度
滑块，也不修改全局设置来保留某个校准值。保存JSON可能省略false和mode1，按正式原生默认
解释并保留原始快照。校准强度与开关历史分别验收，不能从噪声底下降单独推断人声保真。

工程LUT用`lut-library/lut-controls/lut-select/lut-value`；色温/色调用
`white-balance-controls/white-balance --parameter temperature|tint --value <native值>`。
修改需新UUID、精确会话和已初始化的原生参数。LUT/白平衡修改会保护全部其余时间线，
未准备的红色HSL原生模式在派发前拒绝；该模式实际影响画面，不能当无关UI标志忽略。
新LUT工程的package2计划会预置，保留用户显式false。任意CUBE的标准色彩一致性仍未通过。

独立实验LUT33兼容滤镜已有真实原生编辑/出片，不替代上述原生LUT路线；只接固定来源资源，
须用显式`native_filter_name`保留正常可见滤镜卡片。`filter-controls`返回正式控件显示与
启用条件，不能只凭setter成功宣称可编辑。具体计划字段、色块及实拍残差见
[高级画面与声音](WINDOWS-NATIVE-AV.md)。

`color-preset-save --draft-id ... --session ... --segment-id ... --request-id <新UUID>`
通过真实原生handle正常保存当前完整调色预设，返回`preset`路径/摘要及四通道曲线核对；
仅适用于已绑定完整曲线的当前视频。已构造preset manager须属于主GUI线程，错误owner会在
派发前拒绝。无论成功或不确定均不重复提交；保存JSON本身不代表自定义预设应用已验收。

错误后的完成标准：读取对应审计与当前status，确定是否已提交；不自动重放 `needs-inspection`。
会话或保存版本变化时重新读取状态，重新判断用户目标，再生成新业务请求。

```powershell
& $entry agent live minimize --draft-id $draft
& $entry agent live release --draft-id $draft
```

`minimize` 调用当前Qt窗口；`release` 排空原生请求后真正卸载桥接，剪映继续运行。
普通CLI结束仅断开客户端；下一命令可重连。超时或不确定连接不会强制卸载。

用户明确要求切换到另一个草稿时，可先结束当前已保存的编辑页，再从首页首次打开新稿：

```powershell
& $entry agent live close --draft-id $draft --session $session --request-id ([guid]::NewGuid().ToString())
& $entry agent stage --build '<已验证的新build>' --open
```

`close` 必须带精确会话与请求 UUID，先确认暂停、保存回读并备份元数据，再发送正常可取消的
`QWindow.close` 事件；不调用私有强制关闭、不终止进程、不跳过确认框。只有原生检查确认已无
编辑草稿才报告 `home-without-edit-draft`。取消、超时、其它草稿抢先打开或状态不明均停止，
不自动重放；`stage --open` 本身仍拒绝替换已有编辑页。最小化或无焦点时以经 DLL 指纹绑定的
Qt 窗口列表定位唯一 MainWindow，不恢复焦点，也不发送鼠标键盘事件。

首次打开若停在本机已验证的“磁盘空间不足”提示，保留原请求，不重发 `stage --open`。
`agent cancel-low-disk --pid <精确进程> --birth <进程代际> --request-id <UUID>` 只取消这一个
提示：核对完整原生文案、可见状态、QML 类和固定构建后调用正常 `QWindow.close`，通过官方
QML 的取消回调结束等待。它使用同一固定桥 DLL 的独立引用/临时连接，原连接保持；成功还须
原连接健康检查证明之前的同步任务已返回。相同请求 ID 不二次投递；其它提示或不明结果均拒绝。
该命令不确认低磁盘风险继续工作、不修改 confirmedClose，也不模拟输入。依据见
[原生等待研究](research/native-stage-modal-wait-20261028.md)。

本轮新增`agent quit-home --pid <精确进程> --birth <进程代际> --request-id <新UUID>`，
仅在原生检查明确`NO_EDIT_DRAFT`后调用真实`QCoreApplication.quit()`普通槽；当前编辑页仍
存在或首页状态不明时拒绝。正常退出须观察该进程实际exit code 0，不强杀、不模拟输入、
不重复派发未确认退出。该命令只退出，不启动新实例。重启后的PID、birth、session及全部
QObject绑定必须重新发现，不能复用旧值。

## 4. 新建与导出

```powershell
& $entry workspace --name campaign
& $entry build --plan '<ASCII任务目录\plan.json>' --out '<ASCII任务目录\build>'
& $entry verify-build --build '<ASCII任务目录\build>'
& $entry export --build '<ASCII任务目录\build>' --out '<新的ASCII任务目录\export>'
& $entry agent stage --build '<ASCII任务目录\build>' --open
```

`verify-build` 参数以当前 `--help` 为准。`stage` 完整复制已验证的新草稿到其声明目标，验证哈希，
由剪映正常草稿发现入口扫描。`--open` 只负责从首页首次进入该草稿；已有其它编辑页时拒绝替换。
无需手写首页索引，也不要求退出剪映来显示新草稿。当前不运行剪映时先保留已准备好的草稿，
由用户打开软件；不要把“staged”当作“当前编辑页已连接”。

```powershell
& $entry export-draft --draft-dir '<status.report.draft_path>' --out '<新的ASCII任务目录\saved-export>'
```

实时修改后导出**保存后的草稿**，不要从修改前的不可变build重导。导出期间同一草稿停止新编辑。
后台任务使用独立草稿/工作区；当前只验证一个可视编辑会话加独立后台任务，不能宣称多个GUI页同时同步。
导出完成要求 `encoded-and-decoded`、完整解码、源未变，再核对实际画面与声音。
帧数检查区分精确整数帧、微秒量化边界与真正的分数帧，不通过删除末帧来凑数。
以 `status` 与 `accepted_frame_range` 判断验收；微秒量化边界可有 `frame_delta:1`，
精确整数帧仍必须落在单点区间，不能统一把“相差一帧”当作通过。

## 路径、状态与维护

`local-settings.json` 的 `draft_root` 是草稿目录，`draft_index_path` 是首页索引文件，两者可在不同磁盘。
本机前者在D盘、后者在C盘。明确配置优先；未配置时只从唯一有效索引根推导，多根歧义即拒绝。
冷发布 `publish` 仍保留关闭剪映的索引事务保护；当前页同步和新草稿发现使用 `agent live/stage`。

`workspace_root/live-editor-state/` 保存请求审计、修改前备份、连接代际和跨客户端锁。
命令stdout是单个JSON结果，诊断走stderr；退出码0代表该命令完成，2代表拒绝或需检查。
该入口不携带第三方账号登录态，不复制密钥到工程。原生桥精确绑定11.4.7.14462，离线导出的版本范围另列于project.json。

源码升级后按备份清单恢复；不能用 `git reset --hard` 丢弃原有未提交改动。首次集成前备份见
`D:\JianyingHeadless\backups\formal-integration-20261022-114231-af7ea2\manifest.json`。

## 参考学习与动态图形

参考复刻、信息图包装或 OrkasVideoStudio / HyperFrames 接入时，读
[OVS 与 HyperFrames 制作链](WINDOWS-OVS-HYPERFRAMES.md)。先完成参考证据与 OVS 计划校验，
将实拍和文字保留为原生轨，再沿本页 build、preview、export、stage 验收。
