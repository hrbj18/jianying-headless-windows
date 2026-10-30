# 剪辑审美与跨风格创作能力：40 个开源项目比较

调研日期：2026-10-27。用户本轮范围是“找对标可用于学习优化项目的能力”。本轮只分析本地参考、检索资料和核验源码；未安装候选项目或模型、未上传用户素材、未运行候选项目、未修改剪映草稿或执行复刻剪辑。

## 结论

优先推荐 **OrkasVideoStudio（83）+ Qwen3-VL（83）+ HyperFrames（82）**，分别补充有证据的参考分析/设计审片、图文和时序感知、动态图形实现。推荐是对下一步小范围验证的投入顺序，不是已经测得的成片质量，也不是安装后获得“大师审美”的承诺。

OVS 已依赖 HyperFrames；是上层方法与底层实现的关系，不能计算为两套独立审美模型，不能重复安装抢版本。选中的 Qwen 也不是现成剪辑师。最终草稿、保存、预览和导出继续走本项目已有的 jianying.ps1 原生链路。

“只学一条标杆”不足以覆盖跨风格判断；更有用的资产是 **条件化方法库**：面对什么内容、想让观众理解/感受什么、有哪些可选剪法、各自为何有效、哪些反例表明不适用。一个参考提供一个证据，不能升级为所有题材的强制模板。学习上述项目的方法/代码并不改变基础模型权重；没有本轮训练或质量提升实测。

[VEBench 原论文](https://arxiv.org/abs/2605.03276)把剪辑技术识别与多素材选择/时间定位分开，实验仍发现模型与人类编辑认知的显著差距；因此本报告不把模型自评分、特效数量、README措辞或测试数量当成艺术质量证明。

## 这条对标实际需要什么

原片：`7694586117093444890.mp4`（历史本机证据：`%USERPROFILE%/Downloads/douyin-7694586117093444890-20261027-144251-786461/7694586117093444890.mp4`，未随源码分发）。

- ffprobe：833.811995 秒（约13分54秒），1920×1080，30fps，H.264/AAC立体声。
- 实际查看全片36张等间隔抽帧，另看2:33–2:55的12张逐两秒抽帧，总48张。不等于完整连续观看或听审；没有测全片切点、BPM、音效落点。
- 画面是财经讲解：主持人口播、新闻/影视B-roll、公司人物关系、饼/柱图、金额和标题、人物圆形小窗。
- 2:33–2:55可见同一饼图逐步出现6%/94%、类别、投票权与颜色对照。由此推断，此参考的重要能力是“让信息随讲解分阶段显现”，不只是镜头间卡点。
- 对标的声音混合、细微缓动与完整情绪节奏尚未连续核验；不能以抽帧声称已精确复原。
- 素材目录 %USERPROFILE%/Videos/10-23素材 顶层有83条MP4，既有索引写明门店/机器狗/人形机器人/顾客互动。目录盘点和索引阅读已完成，本轮未逐条审看83条原片。
- 因题材不同，未来可迁移“实拍证据→必要图解→视觉重点→回到实拍”的表达逻辑；金融数据、人物关系和原片数字不能冒充目标活动事实。是否需要旁白、图表、哪些真实数据支撑，属于下一轮创作决策。
- 本机 nvidia-smi：RTX3050，6144MiB显存。不能把大模型论文性能等同于本机运行能力。

图像证据：[全片概览1](media/reference-contact-1.jpg)、[全片概览2](media/reference-contact-2.jpg)、[饼图变化局部](media/reference-detail-0233-0255.jpg)。原视频未拷贝进仓库。

## 搜索与评分方法

使用 agent-reach 的 Exa 全网发现、GitHub CLI/API核验一手仓库/代码/许可，补查官方论文、模型卡与文档；用 find-skills 的排行榜及 video editing / cinematography / storytelling video 查询补查技能项目。二手聚合页只作发现线索，不作为关键能力结论依据。

覆盖热门的 HyperFrames、Qwen、Manim、OpenMontage，也覆盖约329 stars的OVS、约129 stars的Animation Principles、约39 stars的MovieCuts、约5 stars的Edit3K等小众项目；热度只用于说明覆盖面，**不参与评分**。星数为查询时快照，不作长期承诺。

六维上限共100：跨风格判断30、时序/节奏25、这条参考的视觉表达15、接入现有Windows剪映15、已发布实现与可运行证据10、运行成本5。维度是对需求的分解，非软件通用质量。无法独立完成整件事的配套组件自然分低；相差1–3分没有统计显著性。本次未给95+，因为没有发现已证明通用“大师级剪辑判断”的即用项目。

证据分三层：官方说明；实际模块/技能/示例/测试代码；本机运行。本轮前两层做了核验，第三层没有做。Top3进一步读到源码中的方法与局限。对分数采用同一尺度综合复核：OpenMontage分组初评84，在错误判断规则与放行逻辑被确认后最终80；其余分组分数及综合新增项目见附表。

## 40 个代码许可明确的项目

下表“代码开源”不意味着附带模型、训练集、第三方服务、素材和依赖全部无限制；这些差异写在同一行。Shot2Story、Edit3K等只能按代码许可计数，不能把限制数据混入生产。没有用根许可证缺失或非商业代码项目来凑这40个。

| # | 项目/一手仓库 | 适配/100 | 许可范围 | 可学习的能力 | 主要限制 |
|---|---|---:|---|---|---|
| 1 | [OrkasVideoStudio](https://github.com/Orkas-AI/Orkas-VideoStudio) | **83** | MIT | 参考拆解、条件化剪辑方法、设计审稿、EDL | 早期；Windows有代码分支但本机未验；没有剪映导出 |
| 2 | [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | **83** | Apache-2.0；所核权重同许可 | 图表/OCR/布局与带时间的视频理解 | 不处理声音；6GB需另测小模型/量化或远端 |
| 3 | [HyperFrames](https://github.com/heygen-com/hyperframes) | **82** | Apache-2.0 | 信息图、动态排版、逐步呈现、声音/动效时序及设计方法 | 框架由Agent作创作判断；不直接导出可编辑剪映图层 |
| 4 | [OpenMontage](https://github.com/calesthio/OpenMontage) | **80** | AGPL-3.0；依赖另核 | 多类型创意路线、解释片导演、实拍混合动态图形 | 参考来源误判和严重问题放行规则需修正；编排较重 |
| 5 | [Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni) | **79** | Apache-2.0；所核权重同许可 | 结合讲话、音乐与画面分析音画关系 | 官方BF16显存远超6GB；适合远端少量关键片段 |
| 6 | [InternVideo3](https://github.com/OpenGVLab/InternVideo) | **77** | Apache-2.0；所核权重同许可 | 长素材检索、时间定位和证据复核 | 研究部署复杂；8B非6GB即用 |
| 7 | [video-use](https://github.com/browser-use/video-use) | **77** | MIT | 对白驱动EDL、逐切口检查、剪辑执行方法 | 主要依靠转写和按需图帧；非连续声画审美 |
| 8 | [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | **77** | MIT | 与旁白同步的矢量信息图、解释动画 | 需要写TS；不自动理解素材或作叙事决策 |
| 9 | [OpenFilm](https://github.com/openfilm/openfilm) | **75** | MIT | 实拍与HTML/SVG/3D图形组合，可视与代码编辑 | 新增编辑器与现有剪映重叠；非审美模型 |
| 10 | [Animation Principles](https://github.com/dylantarre/animation-principles) | **75** | MIT | 注意力引导、预备与回报、节奏变化等可复用判断词汇 | 知识型skills，未有大师质量评测；不应把规则绝对化 |
| 11 | [Manim Community](https://github.com/ManimCommunity/manim) | **74** | MIT | 概念的渐进图解、关系图、数据动画 | 引擎非导演；擅长解释图形，实拍混剪需衔接 |
| 12 | [mimic-mcp](https://github.com/pouyashahrdami/mimic-mcp) | **74** | MIT | 多参考作品统计、镜内变化、style-spec与对照审查 | Windows缺Apple OCR/TTS，节拍功能有回退 |
| 13 | [VideoLLaMA 3](https://github.com/DAMO-NLP-SG/VideoLLaMA3) | **74** | Apache-2.0；所核权重同许可 | 图表、多图与视频时间定位 | CUDA/FlashAttention等依赖；Windows本机未测 |
| 14 | [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | **74** | Apache-2.0 | 理解片段→文案→时间线，few-shot风格与Skill归档 | 复杂信息设计弱于专用图形引擎；增强Demo资源不全开放 |
| 15 | [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | **73** | Apache-2.0；Remotion另许可 | 镜头配方、产品视觉、分镜、动效与声音设计 | 偏产品宣传；剪映出口仅声明macOS11.2验证 |
| 16 | [Diffusion Studio Editor](https://github.com/diffusionstudio/editor) | **72** | MPL-2.0 | 代码与时间线同步、动态图形与预览修订 | 更像替换编辑器，现有项目接入成本高 |
| 17 | [LearningToCut](https://github.com/PardoAlejo/LearningToCut) | **68** | MIT；数据/素材另核 | 学习真实电影切点，比较多个候选剪法 | 旧研究栈；局部切点合理性不是整片叙事 |
| 18 | [HKUDS VideoAgent](https://github.com/HKUDS/VideoAgent) | **65** | MIT；嵌套依赖另核 | 理解、编辑、改编的任务分解与工具路由 | 多模型/API；官方8GB要求高于本机6GB |
| 19 | [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | **64** | BSD-3-Clause | 可复核的镜头边界、时长和节奏基准 | 测量切点，不理解为何该切；可能误判图形变化 |
| 20 | [editstyle / CutAI](https://github.com/mindsurf0176/editstyle) | **64** | MIT | 多参考学习与可移植EDITSTYLE.md | alpha；偏Mac优化；保存模式不等于通用审美 |
| 21 | [MovieCuts](https://github.com/PardoAlejo/MovieCuts) | **63** | MIT；数据需申请 | 动作切、反应切、J/L-cut等剪辑语法 | README平均AP47.91%；Match Cut2.43%；旧栈 |
| 22 | [VideoScore2](https://github.com/TIGER-AI-Lab/VideoScore2) | **62** | MIT代码；权重逐项另核 | 可解释视频质量、文本对齐与物理一致性 | 偏生成视频，不能评判讲解逻辑和信息阅读节奏 |
| 23 | [VideoDB Director](https://github.com/video-db/Director) | **62** | MIT；VideoDB服务另算 | 长素材索引、语义检索、摘要和片段编排 | 依赖云服务；不是完全本地免费能力 |
| 24 | [Kinocut](https://github.com/KyaniteLabs/kinocut) | **61** | Apache-2.0 | MCP剪辑工具、质量回执、可追踪审查 | 执行强，新增审美判断有限；与现有引擎重复 |
| 25 | [Shot2Story](https://github.com/bytedance/Shot2Story) | **61** | Apache-2.0代码；标注CC-BY-NC-SA | 镜头事实→段落→故事的分层记忆 | 标注非商业，不能直接装入商用知识库 |
| 26 | [TransNet V2](https://github.com/soCzech/TransNetV2) | **58** | MIT | 神经镜头边界检测，定位复杂切换 | 没有审美或语义判断；环境需隔离 |
| 27 | [Beat This!](https://github.com/CPJKU/beat_this) | **57** | MIT代码及发布权重 | 音乐节拍/强拍时间，CPU可用 | 口播的语义节奏不应机械吸到音乐鼓点 |
| 28 | [WhisperX](https://github.com/m-bain/whisperX) | **55** | BSD-2-Clause代码；模型另核 | 词级时钟和说话人划分，辅助旁白驱动视觉 | 识别/对齐会错；本机显存与具体模型另测 |
| 29 | [librosa](https://github.com/librosa/librosa) | **55** | ISC | 起音、节拍、能量等声音特征 | 不理解故事和情绪，只输出信号特征 |
| 30 | [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | **55** | Apache-2.0 | 镜头顺序、时长和媒体引用的标准编辑决策格式 | 不渲染、不自动剪辑；没有已验剪映连接器 |
| 31 | [Edit3K](https://github.com/GX77/Edit3K) | **54** | MIT代码；数据许可另核 | 学习效果、动画、转场等六类组件表示 | 数据gated约1.74TB，不适合本机全量训练 |
| 32 | [ShotSeqBench](https://github.com/litchiar/ShotSeqBench) | **54** | Apache-2.0代码；源数据另核 | 镜头顺序对照、电影元数据、顺序评价问题 | 基准/标注为主，不是可直接生产的剪辑Agent |
| 33 | [Shotpilot](https://github.com/tskupinski/shotpilot) | **53** | MIT | 运动稳定度、速度与镜头多样性 | 无人机题材偏重；fcntl导致Windows不支持 |
| 34 | [SAM 2](https://github.com/facebookresearch/sam2) | **52** | Apache-2.0代码及检查点 | 人物/机器狗分割和跟踪，为构图、遮罩让位 | Windows官方建议WSL；不会判断何时该强调主体 |
| 35 | [Auto-Editor](https://github.com/WyattBlue/auto-editor) | **50** | Unlicense | 静音/运动规则粗剪及编辑器格式输出 | 删静音不能替代判断有价值的停顿 |
| 36 | [Editly](https://github.com/mifi/editly) | **48** | MIT | JSON声明多轨、字幕、转场与声音组合 | 是执行框架；Windows依赖适配未验证 |
| 37 | [Clapper](https://github.com/jbilcke-hf/clapper) | **47** | GPL-3.0 | 角色、场景与故事交互 | 很早期，官方承认部分失效且无tests；偏生成 |
| 38 | [AI Video Agent](https://github.com/NSK-394/ai-video-agent) | **46** | MIT | 参考blueprint和镜头分配结构 | 所谓语义/审美实际为OpenCV阈值；目标Resolve |
| 39 | [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | **41** | Apache-2.0 | 剪映草稿轨道与关键帧编排参考 | 增加执行接口不增加审美；10.8支持不能外推本机11.4.7 |
| 40 | [AutoCutAI](https://github.com/Kuonirad/AutoCutAI-Autonomous-AI-Video-Editor-that-Understands-Semiotics-Rhythm) | **39** | Apache-2.0 | 帧精确节拍粗剪和CSV EDL | 现实现仅简单beat policy；符号/情绪理解还是愿景 |

## 明确推荐的三个项目

### 1. OrkasVideoStudio：把剪辑判断变成可执行的工作方法（83）

这是本次最值得先学习/试接的方法层。其 [reference-recreation](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/video-craft/references/reference-recreation.md)要求观察真实画面，拆内容/构图/时序/声音，区分保留与可变化属性，并明确不能盲拷参考秒数；改了文本，应按新旁白和阅读时间安排。这个方向直接回应“跨题材思考而不是固定手法”。

[composition-design-review](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/composition-design-review/SKILL.md)将问题定位到场景/帧、阅读、焦点、重复构图和动效干扰，要求具体修复；[EDL源码](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/ir/edl.ts)和[合成契约](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/composition/manifest.ts)把方法接到实际计划。

Windows存在路径/进程分支，但CI只跑Linux，本机尚未验收；npm发布状态需按安装时核对，当前README建议源码构建。它没有剪映直出，且[video-craft](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/video-craft/SKILL.md)中的hook秒数、镜长、easing规则仍是经验起点，不能奉为所有风格的定律。

**推荐用法：优先引入参考拆解、视觉规划、设计审稿与计划契约，保留现有剪映执行器。** 不需要为此另建群聊平台。

### 2. Qwen3-VL：补充可验证的视觉与时序感知（83）

[官方模型/代码](https://github.com/QwenLM/Qwen3-VL)及[视频cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/video_understanding.ipynb)支持图表/OCR/多帧/视频时间信息。对这条参考，价值是把“高级”拆成可指认的观察：图表何时新增信息，颜色强调哪个对象，小窗是否抢焦点，实拍与图解如何交替。后续可让结果输出时间点、观察与不确定项，供编排和复核使用。

**推荐用法：作为可替换的感知后端，先做少量片段的证据性分析比较。** 现有Codex可读图，不应假定再加模型就必然提升质量；通过固定片段对比才能证明增益。Qwen3-VL不听音频，需结合已有ASR与实际音频检查。6GB卡只能另测小模型/量化/低采样，或按授权使用远端推理；不能承诺8B/长视频本机流畅。对2B、4B或具体量化权重需另核模型卡，本轮不安装不上传。

### 3. HyperFrames：让信息设计真的变成动态画面（82）

[项目](https://github.com/heygen-com/hyperframes)提供HTML/CSS/SVG/媒体和可寻址动画的确定性渲染；[story](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/story.md)写了不同叙事装置与形式的候选，[look](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/look.md)从题材/品牌/参考形成视觉约束，[film](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/film.md)明确图形要随讲述分阶段呈现。可以实现关系图、数字、箭头、图层显隐与文字层级，而不只增加字幕和转场。

[音频节奏源码](https://github.com/heygen-com/hyperframes/blob/main/packages/core/src/audioRhythm.ts)是真实信号处理实现，但不能当故事理解。框架也不会独立拥有审美，创作仍由Agent及审阅决定。Node22+/FFmpeg/浏览器路线对当前6GB机器比大视频模型更现实；性能尚未本机验证。

**推荐用法：制作必要的信息图/动态图形片段，再经现有原生链路进入剪映。** 渲成视频后，图形内部文字/节点不会自动成为剪映原生可编辑图层；应保留图形源码与可重渲版本。透明格式是否被当前剪映构建正确支持要单独验证，不能默认承诺。

**依赖注意：OVS当前固定HyperFrames 0.7.60，不能把最新版README能力直接认作该固定版本已具备。** 现有机器虽有HyperFrames相关技能，版本及运行能力仍需另验；下一轮应选择兼容版本，不同时装两份互相覆盖。

## 为什么不把几个看起来更炫的项目排进前三

- **OpenMontage（80，AGPL）**：知识面广、真实解释片/图表/实拍路线有价值。但固定提交的[参考分析第72行](https://github.com/calesthio/OpenMontage/blob/e01dbf433f46eeb91d39bf905e194162921019a3/skills/meta/video-reference-analyst.md#L72)将大多motion_clip推断为video generation，实拍也会运动；[reviewer第87行](https://github.com/calesthio/OpenMontage/blob/e01dbf433f46eeb91d39bf905e194162921019a3/skills/meta/reviewer.md#L87)允许两轮仍critical后pass with warnings。宜学习其[scene-director](https://github.com/calesthio/OpenMontage/blob/main/skills/pipelines/explainer/scene-director.md)，先修正这些规则再考虑整体接入。与OVS高度重叠，不建议两套导演编排同时承担主线。
- **video-shotcraft（73）**：镜头卡与产品视觉优秀方向，但更偏产品宣传，Remotion另有许可；剪映导出文档只声明macOS11.2验证，不能外推到本机11.4.7。
- **MovieCuts/LearningToCut**：直接研究剪辑语法/切点，冷门且值得学；但数据、旧依赖与局部任务限制明显。它们不能直接完成财经信息图或整片创作。
- **纯节拍检测/静音剪除**：能提供时间事实，却不会知道该让人看懂图表还是保留一个情绪停顿。
- **质量评估模型**：技术质量、图像美感、生成物理一致性不是叙事质量；不能拿一个分数宣布“大师级”。

## 公开源码、模型或素材许可受限的补充候选（不计入上述40个）

这些仍有学习价值，但不包装成完整、可直接投入生产的开源方案。分数同样为主观适配。

| 项目 | 分数 | 能学什么 | 为什么不进正式前三 |
|---|---:|---|---|
| [video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft) | 81 | 字级旁白同步、语义拍、动态图解与分镜审稿，非常贴本次参考 | PolyForm Noncommercial，非商业许可；Remotion另许可，不能当无限制开源生产包 |
| [Video Editor Agent](https://github.com/krusemediallc/video-editor-agent) | 80 | 条件式视觉语法、镜内build、逐句图形与声音QA | 未见根许可证；CapCut现代版本端到端未验、macOS偏重 |
| [VideoChat3](https://github.com/MCG-NJU/VideoChat3) | 75 | 动作与长视频时序 | 代码未检出许可；模型卡Apache，与代码分开 |
| [Remotion](https://github.com/remotion-dev/remotion) | 74 | 成熟React动态图形与视频工程 | 源码公开但特殊商业许可证，不按OSI开源计数；能渲染不等于会导演 |
| [ShotBench / ShotVL](https://github.com/Vchitect/ShotBench) | 72 | 景别、光线、构图、运镜八维摄影语言 | ShotVL-3B模型卡Apache，但代码未检出许可、训练代码未发布；单镜头能力非整片叙事 |
| [3Blue1Brown videos](https://github.com/3b1b/videos) | 72 | 真正解释视频的逐场景源码，概念可视化思路 | 场景代码CC-BY-NC-SA，与MIT Manim引擎不同；不要直接用于商业衍生作品 |
| [DIRECT-Claw](https://github.com/AK-DREAM/DIRECT-Claw) | 70 | 运动/构图连续性与音乐能量联合优化 | README有MIT徽章但未见许可证文件；题材偏音乐混剪 |
| [CutClaw](https://github.com/GVCLab/CutClaw) | 70 | 长素材分解、缓存、shot_plan/shot_point | 未见许可；部分timeline/audio-alignment review函数是空占位 |
| [AIcut](https://github.com/luoluoluo22/AIcut) | 55 | JSON时间线与AI/编辑器同步 | 未见许可，偏执行接口 |
| [DOVER](https://github.com/VQAssessment/DOVER) | 51 | 技术质量与美感分开评估 | S-Lab非商业；不评论证/叙事 |
| [MovieAgent](https://github.com/showlab/MovieAgent) | 50 | 编剧/导演/分镜层级规划 | 未见明确许可；偏生成电影，非现有素材剪辑 |
| [madmom](https://github.com/CPJKU/madmom) | 48 | 音乐节拍/强拍 | 代码BSD但模型CC-BY-NC-SA；Beat This更适合优先试用 |
| [FAST-VQA](https://github.com/VQAssessment/FAST-VQA-and-FasterVQA) | 45 | 快速技术质量筛查 | S-Lab非商业；无完整剪辑判断 |

额外发现但未放进主榜的方向：JAVEdit主要是生成式主体/背景/语音修改，分组报告给33；mengto/skills的video-to-superprompt主要是网页设计录屏→HTML；auteur是网站导演式设计。它们名称里有video/cinematic，也不等于符合当前剪辑任务。搜索中的旧owner Open-Montage/OpenMontage为404，已追到有效calesthio/OpenMontage；没有据旧地址误删该候选。

## 现有项目怎样吸收这些能力（只是建议，不是本轮已实现）

1. 将参考分析输出区分为：画面事实、时间锚点、可迁移原理、题材专属内容、未知音画细节。多参考按“解释/情绪/产品/现场纪实”等条件检索，不混成同一配方。
2. 以真实素材证据提出不同叙事/视觉方案。每项都写观众此时需要知道什么、焦点在哪、为何切或为何不切，避免只列效果名称。
3. 图形用HyperFrames生成独立可重渲素材；主体实拍、原声和字幕继续由现有剪映计划管理。不能把所有内容压成一条MP4后仍称整片可编辑。
4. 审阅同时看连续时序和实际声音；抽帧/信号只能支持各自范围。裁定具体问题而非自评高分。
5. 正式扩展前，用一个从未参与规则提炼的新事件检验：它能否解释不同剪法的取舍、保持真实因果、让信息读得完。成功必须来自实际成片对比，不以安装完成或模型会描述术语代替。
6. 版本、缓存和成果进入项目独立记忆；不改Codex全局记忆，不反复重转写已有素材。

下一步最合理的技术验证范围是“一个20–30秒信息图与实拍混合片段的分析→计划→图形→剪映交接”，不是立即渲染14分钟，也不是训练大模型。此处只是后续验收建议，用户本轮没有授权开始制作。

## 分项评分与证据文件

原始主榜：[JSON](editing-quality-scores-20261027.json)、[CSV](editing-quality-scores-20261027.csv)。
分组证据：[21个剪辑Agent项目](editing-agent-candidates-20261027.md)、[18个感知/评估项目](perception-candidates-20261027.md)。
分组中重复的项目只在主榜计一次；分组文件保留发现过程的初评，主榜为本轮综合结论。

| 项目 | 跨风格30 | 时序25 | 参考视觉15 | 接入15 | 实现10 | 成本5 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| OrkasVideoStudio | 25 | 21 | 13 | 12 | 8 | 4 | 83 |
| Qwen3-VL | 25 | 18 | 14 | 14 | 9 | 3 | 83 |
| HyperFrames | 23 | 20 | 15 | 11 | 9 | 4 | 82 |
| OpenMontage | 26 | 20 | 14 | 8 | 8 | 4 | 80 |
| Qwen3-Omni | 25 | 22 | 11 | 11 | 9 | 1 | 79 |
| InternVideo3 | 24 | 22 | 11 | 10 | 8 | 2 | 77 |
| video-use | 23 | 20 | 11 | 11 | 9 | 3 | 77 |
| Motion Canvas | 20 | 19 | 14 | 11 | 9 | 4 | 77 |
| OpenFilm | 22 | 19 | 13 | 9 | 8 | 4 | 75 |
| Animation Principles | 24 | 18 | 12 | 11 | 5 | 5 | 75 |
| Manim Community | 20 | 17 | 14 | 10 | 9 | 4 | 74 |
| mimic-mcp | 19 | 20 | 14 | 10 | 8 | 3 | 74 |
| VideoLLaMA 3 | 22 | 17 | 13 | 11 | 8 | 3 | 74 |
| FireRed-OpenStoryline | 22 | 19 | 10 | 12 | 8 | 3 | 74 |
| video-shotcraft | 21 | 18 | 14 | 9 | 8 | 3 | 73 |
| Diffusion Studio Editor | 21 | 19 | 12 | 8 | 9 | 3 | 72 |
| LearningToCut | 21 | 21 | 7 | 9 | 7 | 3 | 68 |
| HKUDS VideoAgent | 21 | 17 | 10 | 8 | 7 | 2 | 65 |
| PySceneDetect | 7 | 18 | 10 | 15 | 9 | 5 | 64 |
| editstyle / CutAI | 16 | 17 | 10 | 10 | 7 | 4 | 64 |
| MovieCuts | 22 | 17 | 8 | 7 | 6 | 3 | 63 |
| VideoScore2 | 18 | 13 | 13 | 9 | 7 | 2 | 62 |
| VideoDB Director | 20 | 17 | 8 | 8 | 8 | 1 | 62 |
| Kinocut | 12 | 16 | 8 | 12 | 9 | 4 | 61 |
| Shot2Story | 20 | 16 | 7 | 9 | 7 | 2 | 61 |
| TransNet V2 | 6 | 19 | 9 | 12 | 8 | 4 | 58 |
| Beat This! | 6 | 21 | 2 | 14 | 9 | 5 | 57 |
| WhisperX | 6 | 19 | 3 | 14 | 9 | 4 | 55 |
| librosa | 5 | 20 | 2 | 14 | 9 | 5 | 55 |
| OpenTimelineIO | 8 | 13 | 5 | 15 | 10 | 4 | 55 |
| Edit3K | 14 | 8 | 13 | 10 | 6 | 3 | 54 |
| ShotSeqBench | 18 | 17 | 5 | 6 | 5 | 3 | 54 |
| Shotpilot | 14 | 16 | 7 | 5 | 7 | 4 | 53 |
| SAM 2 | 6 | 10 | 14 | 10 | 9 | 3 | 52 |
| Auto-Editor | 5 | 15 | 3 | 13 | 9 | 5 | 50 |
| Editly | 5 | 12 | 9 | 10 | 8 | 4 | 48 |
| Clapper | 16 | 12 | 9 | 4 | 4 | 2 | 47 |
| AI Video Agent | 8 | 16 | 8 | 5 | 5 | 4 | 46 |
| pyJianYingDraft | 4 | 8 | 7 | 9 | 8 | 5 | 41 |
| AutoCutAI | 5 | 13 | 3 | 8 | 6 | 4 | 39 |

## 主榜新增组件的一手核验入口

- HyperFrames：README、Apache LICENSE、story/look/film方法文件及audioRhythm.ts均已读取；上文逐项链接。
- [Motion Canvas README](https://github.com/motion-canvas/motion-canvas#readme)明确生成器式TS动画与旁白同步；[MIT](https://github.com/motion-canvas/motion-canvas/blob/main/LICENSE)已核。
- [Manim README](https://github.com/ManimCommunity/manim#readme)给实际Scene/CLI，明确与3b1b原版区别；MIT。
- [Animation Principles](https://github.com/dylantarre/animation-principles)：实际读取[rhythm-pacing](https://github.com/dylantarre/animation-principles/blob/main/skills/02-by-thinking-style/rhythm-pacing/SKILL.md)、[attention-direction](https://github.com/dylantarre/animation-principles/blob/main/skills/02-by-thinking-style/attention-direction/SKILL.md)及filmmaker内容。仅知识skills，不能照抄其“变成大师”宣传。
- [OTIO README](https://github.com/AcademySoftwareFoundation/OpenTimelineIO#readme)明确是编辑决策及外部媒体引用，不是媒体容器或自动渲染器。
- [WhisperX](https://github.com/m-bain/whisperX#readme)有词级对齐和说话人分离；代码BSD-2-Clause，外部模型另看。
- [SAM2](https://github.com/facebookresearch/sam2#readme)有实际视频分割推理，Windows建议WSL，不能默认原生无依赖。
- [Auto-Editor](https://github.com/WyattBlue/auto-editor#readme)是音量/运动驱动粗剪，仓库Unlicense，网站应用独有资产另许可。
- [Editly](https://github.com/mifi/editly#readme)是Node/FFmpeg声明式NLE，有CLI和JS API；MIT。
- [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft#readme)功能表按剪映版本列范围，不能外推本机运行时；Apache。
- [ShotSeqBench](https://github.com/litchiar/ShotSeqBench#readme)主要给顺序标注、分割/数据入口；Apache代码不覆盖外部电影/ActivityNet源媒体。
- [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft#readme)的124卡/150镜头等是官方当前目录数而非质量成绩；macOS剪映声明与Windows分开。
- [Remotion许可](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)、[video-talkcraft许可](https://github.com/Vincentwei1021/video-talkcraft/blob/main/LICENSE)、[3b1b videos许可说明](https://github.com/3b1b/videos#readme)用于解释为何另列，不把许可证标签空白直接当“禁止使用”或“无限制”。

Agent Reach检查发现本机v1.5.0、可更新v1.6.0；本轮未更新。用户后续可用：“帮我更新Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md”。这与剪辑能力推荐无关，不作为实施前提。
