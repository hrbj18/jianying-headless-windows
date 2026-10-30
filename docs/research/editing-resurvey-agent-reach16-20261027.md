# Agent Reach 1.6 更新后的剪辑能力复查

日期：2026-10-27。范围：更新 Agent Reach 并重新寻找适合本机 Windows、已有剪映项目、用户对标视频及 10-23 多素材的叙事/审美/节奏能力。全程未使用 computer use，未改剪映草稿。本次不把文档完整、工具可执行或模型自评分等同于成片质量提升。

## 更新与检索证据

Agent Reach 从 1.5.0 更新到 1.6.0（uv），运行官方 setup 完成，默认渠道 5/5 准备成功；已刷新 `.agents/skills/agent-reach` 及安装器识别的 Claude Code/OpenClaw 副本。安装回执在 `%USERPROFILE%/.agent-reach/installation-report.md`。

新版实际执行 GitHub search/read、网页 Exa search，取得非空项目与正文；随后 `check github` 的 gh/API 搜索、读取及 `check web` 的 Exa/Jina 检查均通过。没有使用登录浏览器。find-skills 的 `video editing narrative`、`cinematography` 只作发现入口，安装量不参与适配评分。

原始搜索、Ripple checkout 和本机实验保存在 `%USERPROFILE%/.agent-reach/research/editing-20261027/`。检索结果只是线索；下列结论另外核对了一手仓库、许可证、Skill、依赖或执行代码。

## 结论

最值得优先验证的是 **Qwen-MM-Plugins 的 api/Omni + video-edit 方法**：为参考片和素材补充联合声音/画面理解，再输出可复核的段落与剪辑决定。其价值在于补足此前只看抽帧、读转写的感知缺口。它仍不能证明拥有大师审美，官方 Windows 路线为 WSL2，原生 Windows 未验证。

第二个候选 **CutCraft** 的剪辑审稿方法比包装模板更贴题，但知识规则仍由当前 Agent 执行，不是新训练的剪辑模型。第三个 **Music Video Director** 只适合确定了音乐驱动方向的活动短片：提供音乐段落、动作、镜头关系与情绪曲线的组织方法，不适合机械套在财经口播参考上。

这三个都没有剪映原生直出。本项目可继续承担原生轨道、保存与导出；若以后试用，只取它们的感知结果和编辑决定，转换为现有计划，不另建编辑平台。当前新候选未进行成片 A/B 质量实测。

## 12 个候选复查

分数为下一步验证的主观适配度，不是作品质量：叙事/选段35、声画与节奏25、Windows及现有剪映接入25、实现证据15。热度不参与；未本机运行会在状态列明确说明。

| 候选 | 分数 | 适合补什么 | 实现与本机限制 |
|---|---:|---|---|
| [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins) | 78 | 实拍剪辑方法、联合声画理解、时间定位、音乐/声音事件分析 | Apache-2.0；读到 api/video-edit Skill 与节奏/声音规则；模型服务需单独配置，官方 Windows 仅 WSL2；未运行模型 |
| [CutCraft](https://github.com/chang416/cutcraft) | 72 | 多 take 按叙事节拍选择、动作切、视线匹配、J/L-cut、环境声接缝、每镜修色、审稿 | MIT；读到 Skill、editorial-craft、helper清单及测试入口；未运行完整剪辑链；没有证明其规则能独立提升本素材审美 |
| [Music Video Director](https://github.com/guigulaoshi/music-video-director-skill) | 66 | 音乐段落与能量曲线、动作方向、景别递进、歌词/画面关系 | MIT；有 Python CLI 和 EDL；创作判断由 Agent 承担；本机未运行，音乐驱动条件下才优先 |
| [RoughCut Agent / video-os-v2](https://github.com/mocchalera/video-os-v2) | 63 | 事件高点检索、语义/音频检索、连续性、粗剪到细剪与QA | MIT；现行正式界面为 macOS Studio，Marlin 路线偏 Apple Silicon；全栈较重，不能视为本机即用 |
| [Smart Video Editor](https://github.com/Fagan1024/smart-video-editor) | 56 | 带时间的可用画面判断、避开遮挡/失焦、按叙事排序 | MIT；已读 Skill/build.py；脚本执行上游 Agent 的决定，无独立审美模型；默认固定镜长、全局 look 的建议需审慎 |
| [Ripple](https://github.com/conmeara/ripple) | 52 | 同轴画面/波形/词时钟/切点检查、VIDEO.md、结构化交接 | Apache-2.0；本机 doctor/study 实跑。参考片硬切漏检、缺词时钟，详见后文；不能采信默认推断 |
| [cutroom](https://github.com/Young-1231/cutroom) | 49 | 长视频分层日志、窄区间检索、来源证据、对白片段审查 | MIT；Python3.12/Claude SDK；README仍将多视频项目列为M3，和83份短素材混剪不够匹配；未本机运行 |
| [oh-my-cassette](https://github.com/Cassette-Editor/oh-my-cassette) | 35 | 通过 MCP 委托现成编辑服务 | MIT的是桥接器；编辑主体在 Cassette 服务，会准备/上传素材；不是可复用的开源剪辑判断内核，不优先接入 |
| [ReelBrain](https://github.com/Q00/ReelBrain) | 不列入开源推荐 | 叙事、留存、风格、连续性角色及显式反馈记忆 | 根许可证为 Sustainable Use，含用途和分发限制；不能按标准开放许可项目推荐 |
| [roughcut](https://github.com/shivampkumar/roughcut) | 暂不评分 | 每素材 best moments、声音保留决策、结构化 EDL | 根许可证未检出；语音阶段为 MLX、理解为Gemini、故事为Claude；需先明确许可和Windows路线 |
| [ecliptic-ai/skills](https://github.com/ecliptic-ai/skills) | 暂不评分 | 节拍分析、共享时间线、音乐蒙太奇 | 检查树未找到许可证；不可仅凭源码可见就视为可复用开源能力 |
| [ButterCut 原仓库](https://github.com/barefootford/buttercut) | 不列入标准开源推荐 | 素材库和粗剪输出 | 原仓库为PolyForm Noncommercial附商业视频输出许可，非此前某MIT fork所能概括；正式支持Apple Silicon，免费核心单轨，多轨属Pro |

星数快照用于判断维护规模：Qwen3149、CutCraft53、Music Video Director61、video-os-v2为5、Smart Video Editor10、Ripple0、cutroom0、Cassette119。小仓库不自动否定，但没有充分实测时不应强推。

## 为什么 Qwen 比前次包装工具更贴题

[api Skill](https://github.com/QwenLM/Qwen-MM-Plugins/blob/main/src/capabilities/api/skill/SKILL.md) 中，VL 路线读取图像/视频帧；Omni 的 `perceive_media` 和 AV 工具能把画面与音频一起交给模型，支持带时间的事件分析。对用户素材，可以提出有证据的问题：机器狗动作什么时候完成，孩子在看什么，环境音/主持人话语是否在切点被截断，对标某个切点与语义或声音变化是否对应。返回结果仍需原片核对。

[安装说明](https://github.com/QwenLM/Qwen-MM-Plugins/blob/main/docs/en/installation.md) 明确 Windows 当前走 Ubuntu WSL2，原生 Windows 未验证。API 可走 DashScope 或兼容的自托管端点；这不是一个保证能在6GB显卡本地常驻的方案。本轮没有上传素材、调用付费模型或安装WSL。

它的 [pacing-rhythm.md](https://github.com/QwenLM/Qwen-MM-Plugins/blob/main/src/capabilities/video-edit/skill/craft/pacing-rhythm.md) 也有不适合照搬的条款：固定镜长上限、每1–2个feature shot插“breathing card”、小于1.25x缩放“不值得”。这些不是通用审美规律，机械应用可能重现用户反感的版式感。应按10-23素材真实动作和本轮明确偏好处理，不能整份Skill无条件执行。

## Ripple 实测：不能按 README 选工具

检出提交 `2ef88ed5fce6dd2896ef250da1c7ca2d34eca4c4`（package0.13.1）。使用现有FFmpeg/Node，在独立研究目录执行：

1. `doctor`：FFmpeg/ffprobe/x264可用，但 `ready:false`；缺有效词时钟支持和模型。把PATH中一个名为`main`的命令当Whisper也有误认风险，本轮没有据此执行转写。
2. 从用户参考复制前33秒成独立样本；`study`返回 `ok:true`，但 `cuttingRhythm:null`、`pacing:null`、`tail:null`、`sceneChanges:[]`，生成“single-take or dissolve-led”建议。
3. 使用此前已验证的PySceneDetect0.6.7.1，针对同一个样本交叉检测，得到15段、14个候选切点：0.767、6.100、7.333、8.133、8.867、10.333、20.600、21.567、22.300、23.167、25.433、27.733、30.400、32.033。

两种检测器定义不同，14个候选不都必然是摄影镜头硬切；但与既有实看画面一致，参考明显包含素材切换，不能因Ripple的空列表推断整段是单镜头。它输出的speechRatio=1也只是静音阈值度量，不代表模型听懂了全部声音。故降低优先级，保留其可视检查思路，不用于自动决定参考节奏。

## 更适合本项目的下一次验证

先用联合声画分析补充参考及两段真实动作（S029、S083）的事件/声音时间线，再用CutCraft式的动作、视线、句尾和环境声审稿规则比较两个剪法。用现有剪映原生轨道制作，保留来源和切点。验证目标是能否指出并修正具体错误，而不是输出更高的自评分、更多字卡或更多特效。

固定源码快照：Qwen `d7ca19a9c8b60f02a86350706ff5e19095c33850`；CutCraft `535a1176a48fffcafe4a094b5090ec500306ac41`；Music Video Director `66de7f0dcc8d714c4f6cd9988a4d214387caee36`。以上分数不是经过新成片实测的效果保证。
