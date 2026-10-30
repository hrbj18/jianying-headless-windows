---
name: jianying-windows
description: 在 Windows 通过本机剪映原生运行时理解素材、剪辑、预览和导出，支持效果、固定交付修订及素材缓存管理。用户要求剪映视频制作、草稿修改、重复素材去重或可再生缓存清理时使用。
---

# 剪映 Windows

先读 [本机绑定](references/local.json) 的 `project_root`。入口是该目录的 `jianying.ps1`，
使用项目 `.venv` 与本地配置；尚未安装的源码技能可从 `project.json` 定位仓库根。

**当前编辑页实时修改 / Codex与WorkBuddy共用**：先读 `<project_root>/docs/AGENT-ENTRY.md`，
运行 `jianying.ps1 agent doctor`。当前会话使用 `agent live`，新构建进入首页使用 `agent stage`；
以真实草稿ID、会话和请求UUID提交，不靠退出剪映或重开工程刷新。其它工作流继续按下述分支。

1. 运行 `& '<project_root>\jianying.ps1' doctor`，确认 `status: ready`。保留精确构建、DLL
   指纹和官方签名校验；版本不匹配时按错误停止，保留诊断。
2. 读 `<project_root>/docs/WINDOWS-CLI.md` 对应工作流；参数以各子命令 `--help` 为准。
   用 `workspace --name <ASCII-name>` 建立独立任务和唯一工程引用。官方 CLI 编辑使用
   ASCII 素材、草稿、工作区与 Selection 路径；中文源素材先原样复制，保留原件。
   **素材理解/直播剪辑**：先读 `<project_root>/docs/WINDOWS-MATERIAL-ANALYSIS.md`。
   用 `analyze prepare` 建立源文件哈希、目标和模型标签绑定的任务；按用户已有授权选择百炼 ASR，
   密钥从本机配置引用的凭据文件读取。`analyze read` 按章节和文本预算读取，再实际查看图片，
   提交带真实格子与 ASR ID 的候选。模型部署标识未知时明确标未知；抽样不代表完整观看。
   对候选执行 `detail` 并查看返回的精查图；核对原声 ASR 时间或播放原声，声明实际检查方法。
   `assemble --render` 生成原声 1x 剪辑、真实词时钟字幕和原生预览/成片；结构审阅走下一步的
   故事粗剪分支。语义判断由当前 Agent 完成，脚本输出截图不等于已理解。
   **素材去重/缓存回收**：读 `<project_root>/docs/WINDOWS-DELIVERIES.md`。`media-store`
   以完整哈希复用各卷不可变素材池，原件与可写元数据保持独立；改写共享媒体前使用
   `ensure_private_copy`。缓存按 `cache prepare/apply` 的明确清单和可再生证据处理，保留
   可编辑构建与验收依据；报告区分逻辑大小、唯一分配空间与磁盘空闲变化。
3. 按用户风格用 `build` 构建可编辑快照，或用 `lyra create/init/resource-import/sync/apply`
   完成结构编辑。资源 ref 使用本次导入结果，Selection 末尾包含 `draft.apply();`；
   修改现有片段前完整 sync，`--current-only` 仅用于保留目标的回读。
   **故事粗剪**：直播切片或结构重剪先读 `<project_root>/docs/WINDOWS-STORY-EDITING.md`。
   用 `story compile` 记录观看理由、因果、保留/省略及重排理由，先看原速原声和普通字幕的
   干净粗剪。主题驱动制作可增加事件、片段贡献与停顿覆盖契约，核验统一源/目标帧映射；
   粗剪与包装审稿分别绑定实际 plan/MP4。结构成立后再比较每项处理的新增信息、注意力
   成本与“删掉会损失什么”，保留有作用的长镜头和回应停顿。
   粗剪需要统一静态字幕样式时，在 treatment 内设 `subtitle_style` 再编译；审稿后另改
   编译 plan 的字号或位置会使身份绑定失效。真实双阶段示例见故事文档的本机验证段。
   **参考风格蒸馏/复用**：读 `<project_root>/docs/WINDOWS-EDITING-STYLE.md`，用 `style`
   研究多源范例、冻结条件规则并做留出检验。已有风格直接核验 profile，以明确 treatment 调用
   `style assemble --render`；基础风格投影仍需上述因果审阅。粤仔风格使用已安装的
   `yuezai-editing-style` 规则及其本机绑定。
   专名纠错与不确定字幕省略须记录真实 ASR ID 和理由；保持原声，编辑标题与口播字幕分轨。
   **成片精修**：用户反馈太素，或要求加强节奏、动态构图、反应窗、图形与声音时，读
   `<project_root>/docs/WINDOWS-STYLE-PRODUCTION.md`。保留基础风格 plan/audit，另编完整
   native plan 后走正常构建和验收；`style assemble` 参数保持原契约。粤仔的作品选择仍由
   `yuezai-editing-style` 精修规则负责，本入口只路由执行流程。
4. 参数编辑读 `<project_root>/docs/WINDOWS-EDIT-ACTIONS.md`，以真实 `seg_id` 编写
   `edit-actions` 计划，先完成 Blueprint 结构，再做参数和动画。涉及转场、滤镜、特效、
   蒙版尺寸/位置/羽化或蒙版本体关键帧时，必须先读
   `<project_root>/docs/WINDOWS-VFX.md` 并运行 `vfx catalog`；精确 preset、范围和兼容
   规则以该页为准。软边与羽化动画按该页使用现代 `mask/circle-soft`。
   左右推移使用 `slide-left-compat` / `slide-right-compat`；滤镜 `value` 为强度，轻微抖动与模糊
   目前使用原包默认参数，`value:1` 不代表可调幅度或半径。按该页逐项范围选择，资源滑杆元数据
   不代表已开放编辑。零强度滤镜的保存值可能省略 `value`，由正常入口按零值读回校验。
   只将 `applied-and-read-back` 作为保存值验证，继续做渲染验收。
5. 经 typed 动作修改的保存草稿交付前，执行 `vfx freeze-draft --draft-dir ... --out <新ASCII-work目录>`，
   确认 `frozen-and-read-back` 或 `already-draft-owned`，保留整个 Resources。
   读 `<project_root>/docs/WINDOWS-NATIVE-PREVIEW.md`，用 `preview --build ...` 或
   `--draft-dir ... --out <新ASCII-work目录> --at <秒列表>` 检查带时间戳的原生 PNG。
   竖屏显式传 `--width 640`，避免默认按画布比例计算的高度超过 CPU 帧输出限制。
   确认 `native-frames-captured` 和源数据不变，查看切点前、中、后及蒙版动画/边缘。
   雾化也直接使用暂停播放器，核对 `preview_route:native-player-capture-frame`、VEF1 时间戳
   与 `player_state`。旧 v2 仅升级预览副本，须查看 `resource_upgrades`；交付工程使用已冻结 v3
   才代表永久升级。预览不经导出取帧，完整成片仍按下一步验收。
6. 保存工程用 `export-draft`，不可变构建用 `export --build`；输出到新的 ASCII work 目录。
   确认 `encoded-and-decoded`，检查实际整片画面和声音，再交付 MP4 与含素材的工程。
   **固定交付/修订**：先读 `<project_root>/docs/WINDOWS-DELIVERIES.md`。首次独立交付可用
   `publish`；已有四位交付清单先 `delivery inspect`，新修订验收后以 `delivery promote`
   替换对应 slot、归档旧版。内部试剪留在工作目录，不另登记第五条；其它用户项目保持独立。

默认在任务草稿或副本操作，沿用用户对目标工程的修改要求；读到的是已保存磁盘状态。
动作逐步提交，兼容模块也非原子写入；保持 GUI 与其它任务不修改同一工程。失败时查看审计、
完成步骤及 `before/`，保留恢复资料，不自动回滚或整批重放。正常声明主时间线的读回不能靠
旧根镜像掩盖；历史草稿兼容的准确边界见视觉效果文档。

全程通过官方 CLI、VMSDK、原生服务和已审核兼容模块操作，画面由剪映原生引擎渲染；
预览与导出无需 GUI 控制。未知效果或能力缺口保留错误及工程，不静默删除效果，也不降级为
鼠标、键盘、桌面截图、实验 monkeypatch、开发信任开关或破解程序。在线资源沿用已有授权；
云端 ASR 只读用户明确提供或允许复用的凭据源，密钥和临时云地址留在本机私有配置/任务缓存，
交付仅含脱敏审计。Windows 本地快照不代表额外网络沙箱。GUI 保存和冷重开需另行验收。
