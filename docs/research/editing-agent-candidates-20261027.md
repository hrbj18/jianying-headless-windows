# 剪辑 Agent 与参考驱动项目：一手来源核验

调研日期：2026-10-27。范围：仅查资料、阅读公开源码和测试，不安装、不执行这些项目、不上传用户素材、不启动剪辑。主代理观察的对标是约 13 分 54 秒财经口播解释片，含主持人、新闻 B-roll、图表、关系图、箭头、大标题与圆形人像小窗；因此叙事/信息设计与镜头内部动画节奏，比音乐卡点权重更实质。下表分数是对用户任务的主观适配分，不是模型排行榜或本机实测质量。

评分顺序：跨风格判断 30、时序/节奏 25、对标视觉 15、接入现有剪映 15、可运行证据 10、成本 5。分项是加总式评价；没有哪个项目提供经验证的通用“大师审美”。代码存在、CI 通过与艺术效果是不同证据。GitHub 热度不计分。

## 首轮 16 个有效候选

|项目与一手入口|分项→总分|能借鉴什么|实物与接入边界|许可/状态|
|---|---|---|---|---|
|[OrkasVideoStudio](https://github.com/Orkas-AI/Orkas-VideoStudio)|25/21/13/12/8/4 → **83**|跨制作路线的 craft 知识、参考保护/变化轴、旁白驱动图形、逐帧设计审稿、可读 EDL|有 CLI/MCP、真实 TS 模块和 9 秒全链测试；Node22+、FFmpeg、固定 HyperFrames；有 Windows 分支但 CI 仅 Linux。没有剪映直出，接已有原生入口|MIT；近期维护，2026-10-13 CI 成功|
|[Video Editor Agent](https://github.com/krusemediallc/video-editor-agent)|24/22/14/10/7/3 → **80**|参考镜头语法、条件式字体/布局体系、镜内图形 build 节奏、每句 build directive、审稿回执|真实 skills 与 QA 引擎；并非训练后的审美模型。shell/macOS 偏重。CapCut 导出明确未完成现代版本端到端验证|根目录/递归树未发现许可证，API license=null；只能列公开源码研究候选，不能当许可明确可直接集成的开源包|
|[video-use](https://github.com/browser-use/video-use)|23/20/11/11/9/3 → **77**|以对白/语义组织 EDL，随需查看时间线图，渲染后逐切口自查，动画图层协作|实际 helpers、skill、fps/orientation/caption 测试。主干 ElevenLabs Scribe，README 明确 LLM 不连续看视频、audio primary；不是完整视听审美裁判|MIT；热门、2026-10-08 更新|
|[OpenFilm](https://github.com/openfilm/openfilm)|22/19/13/9/8/4 → **75**|网页表达信息图/排版/动态场景，实拍与动画混合，代码/可视编辑同步，look 检查|Node22.2+、FFmpeg、Chromium，官方写支持 Windows；透明视频/图片/轨道导出适合辅助剪映。渲染确定性与溢出检测不等于审美|MIT；2026-10-26 更新|
|[mimic-mcp](https://github.com/pouyashahrdami/mimic-mcp)|19/20/14/10/8/3 → **74**|测量参考镜头长度、转场、镜内运动与图形变化；analyze_creator 比较多作品的分布，review_render 对照|有 TS 工具/测试与 Remotion 输出。Windows 无 Apple Vision OCR、无 macOS say；aubio 在 Windows 缺口会回退能量启发式。测量相似度仍不能判断论述/情绪|MIT；小众、2026-08-31 更新|
|[Diffusion Studio Editor](https://github.com/diffusionstudio/editor)|21/19/12/8/9/3 → **72**|编程与可视时间线双向同步，动态图形、实际预览和修订|完整编辑器/CLI/MCP，Windows build 与 cli-windows 测试源码；是一套新编辑器，不是能直接赋予剪映审美的模块，替换平台成本高|MPL-2.0；2026-10-18 更新|
|[DIRECT-Claw](https://github.com/AK-DREAM/DIRECT-Claw)|22/23/9/7/7/2 → **70**|编剧/导演/编辑分层；镜头序列的运动、显著性、构图连续性与音乐结构联合优化|实际 editor.py beam search，语义/运动/显著性/能量评分；需 U-2-Net 等权重、Qwen3-VL/vLLM 或模型接口，同 FPS 源要求。音乐混剪对解释片图形逻辑贡献有限|README 挂 MIT 标记，但 API license=null、递归树未见 LICENSE；授权文件需补核|
|[CutClaw](https://github.com/GVCLab/CutClaw)|22/23/8/8/7/2 → **70**|长素材分解/缓存、音乐结构分段、shot_plan/shot_point、编辑与复核循环|真实 Python、Streamlit、LiteLLM、Decord；大量 API 调用及 GPU 解码建议。说话人+画面混编与更丰富叙事仍在路线图；对信息图解释片并非最佳|API license=null、树未见 LICENSE；公开源码研究候选|
|[HKUDS VideoAgent](https://github.com/HKUDS/VideoAgent)|21/17/10/8/7/2 → **65**|视频理解、剪辑、解说、改编的工具路由与任务分解|主程序与多个工具真实存在，官方标 Linux/Windows、8GB GPU；依赖/语音/生成模型较重，多种 API 配置，功能展示不能证明高级审美|项目 MIT；嵌套工具各自许可另核|
|[VideoDB Director](https://github.com/video-db/Director)|20/17/8/8/8/1 → **62**|长视频语义检索、素材索引、摘要/片段编排及可扩展 agents|真实 backend/frontend，依赖 VideoDB 云服务及 API；开源框架不代表视频基础设施可免费本地替代。没有剪映出口|MIT；2026-01-23 更新|
|[AIcut](https://github.com/luoluoluo22/AIcut)|13/14/11/7/6/4 → **55**|Python AI 逻辑与 Remotion 时间线 JSON 的双向同步；编程控制契约|实际 Windows setup.ps1、Next/Electron/Python SDK；以工程编排为主，未看到系统化审美学习证据；又引入一套编辑器|API license=null；不能据公开仓库当许可证明确开源|
|[Shotpilot](https://github.com/tskupinski/shotpilot)|14/16/7/5/7/4 → **53**|镜头稳定度、景别/运动挑选、pace-review、可追踪的取舍|有 OpenCV 分析、FFmpeg 拼接和示例；只做无人机/风景更贴题。官方明确 fcntl 导致不支持 Windows；强调 uniform clips/crossfade，不能覆盖财经解释片|MIT；项目自称 early、vibe-coded|
|[MovieAgent](https://github.com/showlab/MovieAgent)|19/13/8/3/6/1 → **50**|编剧、导演、分镜、场景规划的层级推理可以研究|提供推理代码但主目标是剧本/角色库→生成电影；不等于从现有机器人实拍剪辑。多图像视频模型、部分 CUDA12.1/PyTorch2.4、shell 配置|API license=null；未认定可集成开源许可|
|[Clapper](https://github.com/jbilcke-hf/clapper)|16/12/9/4/4/2 → **47**|故事层的角色/场景/风格抽象与迭代式导演交互|Bun/Node 的 AI 故事可视化应用，README 直接说明很早期、部分按钮与工作流失效、没有 tests；更偏生成不是已有片段高级编辑|GPL-3.0；2025-08-01 更新|
|[AI Video Agent](https://github.com/NSK-394/ai-video-agent)|8/16/8/5/5/4 → **46**|参考→blueprint→镜头分配；可借鉴可计算的节奏与去重|源码证实所谓 semantic_classifier 是 OpenCV 阈值，无 ML：边缘密度猜景别，对比度×饱和度等算 cinematic_score。Windows/Resolve18+，未适配剪映，Demo GIF 仍计划中|MIT；小众 5 stars，2026-05-15 更新|
|[AutoCutAI](https://github.com/Kuonirad/AutoCutAI-Autonomous-AI-Video-Editor-that-Understands-Semiotics-Rhythm)|5/13/3/8/6/4 → **39**|帧精确 beat-aligned rough-cut/CSV EDL 与边界测试|README 明确仅 SimpleBeatSyncPolicy 可用；semiotics、affective curve、generative edit grammar 是 DESIGN 愿景，不能当现成功能。Python3.12/3.13，native工具依赖另外复杂|Apache-2.0；早期 scaffold|

## 最值得深入的 OVS：证据与限制

研究时 HEAD 为 `8a2b51af787830e722f2565b3e13d479ffed5c17`，2026-10-13；[对应 CI](https://github.com/Orkas-AI/Orkas-VideoStudio/actions/runs/38343690134) success。这个结果仅为远端 CI 状态，本机未运行。

- **真实判断工作流**：[video-craft](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/video-craft/SKILL.md) 包含解释结构、画面层次、旁白与图形的节拍、字体、焦点、声音与具体修订；[reference-recreation](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/video-craft/references/reference-recreation.md) 要求源帧证据、保护/可改属性、目标分镜对应，并明确换语言/文本应按新旁白和阅读时间重排，不能盲拷参考秒数；[composition-design-review](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/skills/composition-design-review/SKILL.md) 要求看完整快照集、风险帧与实际对照，按 scene/frame 给出具体修复。
- **真实工程模块**：[core EDL](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/ir/edl.ts)、[composition manifest](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/composition/manifest.ts)、[render](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/tools/src/render/render.ts)、[composition QA](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/tools/src/render/composition-qa.ts) 使计划、素材、渲染和检查落地；它不是只有一个宣传 README。
- **图形后端**：[package.json](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/tools/package.json) 固定 `hyperframes: 0.7.60`；[HyperFrames 调用器](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/tools/src/hyperframes/client.ts) 优先用当前 Node 直接执行依赖包 bin，override/npx 为后备。普通本地 compose/edit 需要 Node22+、FFmpeg、浏览器；不需要为了它再部署大视频生成模型，生成/TTS 另付费/另配。
- **Windows 实质分支**：[binaries.ts](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/runtime/binaries.ts) 处理 PATHEXT、USERPROFILE 与环境路径覆盖；[spawn.ts](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/core/src/runtime/spawn.ts) 处理 windowsHide/taskkill 子进程树。仍只能说“有 Windows 适配代码”，不是“已在这台机器验证”。[CI](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/.github/workflows/ci.yml) 只跑 ubuntu-latest。
- **真实输出测试**：[render-e2e.test.ts](https://github.com/Orkas-AI/Orkas-VideoStudio/blob/main/packages/tools/test/render-e2e.test.ts) 在 `OVS_E2E=1` 时要求 FFmpeg/CLI，制作 9 秒三场景，验证整个 MP4 解码、顺序、首帧可见、运动像素、音频和字幕，拒绝错误时长。这个测试支持“管线有工程证据”，不支持“已证明大师审美”。
- **现有剪映接入**：未见 CapCut/Jianying exporter。适合复用 craft、reference analysis、EDL、局部图形资产和审片方式，再由现有 `jianying.ps1` 原生入口完成草稿与交付；不应替换已打通的项目。OVS 和 HyperFrames 是上层/依赖关系，不能把相同渲染能力重复算成两个独立审美提升。
- **审美规则仍需条件化**：如 1–3 秒 hook、固定镜长范围、永不 linear easing 等属于项目启发式，而非电影与解释片普适定律。建议当作候选方法库，允许按照题材和参考证据覆盖。

## 其他关键源码核查

1. [Video Editor Agent 的 reel-style-clone](https://github.com/krusemediallc/video-editor-agent/blob/main/.claude/skills/reel-style-clone/SKILL.md) 值得研究：明确“条件决定不同字体/构图 register”“镜头内部 build 也构成节奏”“overlay 必须解释作用”，比机械复刻一种模板更接近用户所求。它的 [CapCut export](https://github.com/krusemediallc/video-editor-agent/blob/main/.claude/skills/capcut-export/SKILL.md) 则明确 macOS、现代 CapCut schema patch 仍 work-in-progress，不能宣称 Windows 剪映导入已解决。[QA engine](https://github.com/krusemediallc/video-editor-agent/tree/main/tools/video-qa) 有可选 Gemini watch/listen 层，没 key 时跳过，不等于完整审片。许可缺失使其不宜直接进入落地 Top3。
2. [DIRECT editor.py](https://github.com/AK-DREAM/DIRECT-Claw/blob/main/src/agent/editor.py) 确有候选检索、beam search、semantic/motion/saliency/energy 联合评分；它能改进镜头间连续性，但不会自动设计资金关系图、论证结构或高质量字体系统。
3. [CutClaw Reviewer.py](https://github.com/GVCLab/CutClaw/blob/main/src/Reviewer.py) 有实际片段去重与 VLM 审阅路径；源中 `Review_timeline`、`Review_audio_video_alignment` 两个函数本身只是空占位定义，因此不能仅凭函数名证明所有复核已实现。其他真实审阅函数应分别核查。
4. [NSK semantic_classifier.py](https://github.com/NSK-394/ai-video-agent/blob/master/analysis/semantic_classifier.py) 自述 “OpenCV heuristics (no ML model)”；`shot_scale` 由 edge density 阈值给出，`cinematic_score` 由对比度/饱和度/过曝惩罚相乘。将其宣传为已理解电影美学会误导用户。
5. [mimic analyze-creator](https://github.com/pouyashahrdami/mimic-mcp/blob/main/src/tools/analyze-creator.ts) 有多参考统计工具；[README 平台限制](https://github.com/pouyashahrdami/mimic-mcp#readme) 直接承认 Windows 缺 OCR 与 macOS TTS、beat 检测退化。与对标的复杂信息图相比，caption tracking 也不是完整图形语义识别。
6. [video-use 的设计说明](https://github.com/browser-use/video-use#how-it-works) 明确以转写+随需 PNG 理解视频；优点是便宜与剪口可查，限制是连续运动/情绪和听觉判断不能仅由这些材料保证。
7. [Shotpilot requirements](https://github.com/tskupinski/shotpilot#requirements) 明确 fcntl 导致不支持 Windows；不应因 Python 项目就默认能在用户机器原生跑。

## 本分组建议

针对这次参考，首选深入 **OrkasVideoStudio 的知识/设计审查/计划层**，而不是把整套编辑器换掉。若在本组再选两个配套研究对象，可选 **mimic-mcp 的参考测量（Windows缺口需补）** 和 **OpenFilm 的可检查动态图形实现**；它们不是三位“大师”，角色是判断方法、测量工具、实现工具。全组最终 Top3 应与其他分组的视频感知和动态图形项目一起比较。

## 补充核验 5 个项目（合计 21 个有效候选）

|项目|分项→总分|实际价值与边界|许可|
|---|---|---|---|
|[OpenMontage（正确 owner）](https://github.com/calesthio/OpenMontage)|26/22/14/11/8/3 → **84**|跨类型管线、reference analyst、taste profile、explainer 分镜、真实动态图表组件，适合研究多种视觉/叙事语法。Python3.10+/Node18+/FFmpeg，Windows PowerShell 安装说明；依赖多，默认审批/编排较重，未见剪映出口，部分审阅规则有缺陷详见下文|AGPL-3.0；2026-10-24 更新；本轮 72k+ stars，仅热度信息|
|[FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline)|22/19/10/12/8/3 → **74**|真实 media/understand_clips/generate_script/plan_timeline/recommend_effects/render 节点及 few-shot 文案风格/Skill归档；有Windows手动安装，Python3.11+。主要整体创作/效果推荐，复杂关系图不如专门图形框架；更好Demo涉及小红书AI Clip专有素材库，开源默认效果不等价|Apache-2.0；2026-07-31 更新|
|[editstyle（原 CutAI）](https://github.com/mindsurf0176/editstyle)|16/17/10/10/7/4 → **64**|EDITSTYLE.md/多参考style learning、7种preset、CLI/plan/MCP；真实parser/converter与tests。仍为alpha，desktop仅frame scrubbing不是完整播放，MLX/VideoToolbox优势偏Mac；能保存编辑模式不等于学会通用审美|MIT；2026-09-29 更新|
|[Kinocut](https://github.com/KyaniteLabs/kinocut)|12/16/8/12/9/4 → **61**|Python3.11+ FFmpeg typed MCP/CLI、Video Receipts、Windows模块/测试、HyperFrames/Whisper可选；很强执行与可追溯层，但主要采访/播客转竖屏、QA与工作流，现有项目已有相当执行能力，增量审美不足|Apache-2.0；2026-10-27 更新|
|[JAVEdit](https://github.com/RyanChenYN/JAVEdit)|8/7/5/4/6/3 → **33**|联合声画指令编辑、数据质检模式库可研究；实际任务是主体/背景修改、移除/加入、语音修改，约121帧样本；不是原素材的叙事时间线剪辑。模型链接仍标Under Review，不能当现成剪辑大师|MIT 代码；模型/数据许可另核|

### OpenMontage 与 OrkasVideoStudio：怎么选

OpenMontage 对用户“多种剪辑思路”覆盖更宽，OVS 对“现有剪映只补判断与图形生产能力”更容易控制集成范围。二者都有管线、skills、状态、质量检查、HyperFrames/FFmpeg支持，重叠很大，不建议为了显得全面把两套全栈并装。主代理可依据最终范围挑一个知识/导演层，另配感知与图形引擎。

OpenMontage 实际核查的源码：

本轮固定核查提交：`e01dbf433f46eeb91d39bf905e194162921019a3`（2026-10-24）。争议规则可直接定位：[运动→生成错误推断，第72行](https://github.com/calesthio/OpenMontage/blob/e01dbf433f46eeb91d39bf905e194162921019a3/skills/meta/video-reference-analyst.md#L72)、[两轮仍严重问题后放行，第87行](https://github.com/calesthio/OpenMontage/blob/e01dbf433f46eeb91d39bf905e194162921019a3/skills/meta/reviewer.md#L87)、[重复该规则，第124行](https://github.com/calesthio/OpenMontage/blob/e01dbf433f46eeb91d39bf905e194162921019a3/skills/meta/reviewer.md#L124)。短摘分别为 “the reference uses **video generation**” 与 “**Pass with warnings**”。综合榜可因这些方法错误把本分组初评84下调至约80，并明确这是进一步源码审计后的重评。

- [参考分析技能](https://github.com/calesthio/OpenMontage/blob/main/skills/meta/video-reference-analyst.md) 分 subject / subject motion / scene / spatial framing / camera，产生可复用结构化 brief，要求再看 keyframes，并提出保留/变化方案。
- [解释片 scene-director](https://github.com/calesthio/OpenMontage/blob/main/skills/pipelines/explainer/scene-director.md) 从每句概念和情绪节拍选视觉隐喻、渐进图解、景别、信息图；列出 bar/line/pie/KPI/comparison 等图形与时间组织，并映射到真实 [React 图表组件](https://github.com/calesthio/OpenMontage/tree/main/remotion-composer/src/components/charts)。这与本次财经对标比音乐混剪更接近。
- [source_media_review.py](https://github.com/calesthio/OpenMontage/blob/main/lib/source_media_review.py) 实际调用探测、采帧、分镜、转写，配有 [real media tests](https://github.com/calesthio/OpenMontage/blob/main/tests/lib/test_source_media_review_real_media.py)，不是只有 prompt。
- [reviewer](https://github.com/calesthio/OpenMontage/blob/main/skills/meta/reviewer.md) 要求准确、完整、可执行批评，具体字段/画面绑定；但同时规定“两轮仍 critical 后 pass with warnings”。这不应未经调整就用于最终交付。
- **另一个需要剔除的错误规则**：reference analyst 将“多数 motion_clip”直接推成“reference uses video generation”。实拍同样有运动，该推断不成立。应保留运动分类，删除生成来源的无证据推断。
- README 的 post-render self-review 只说 4 个位置抽帧、音频幅度等，不能宣称已全片连续视听验收；参考 analyst 的示范文案 “I've watched the video” 也不能让工具只抽帧后照抄。
- Windows 支持目前来自安装说明和可读源码，不是本机验收；Python、Node、FFmpeg与按需API都要成本，README示例价格只是作者特定生成案例，不是用户后续成本保证。Remotion许可独立于项目AGPL；HyperFrames可作为另一渲染路由。
- 未见 CapCut/Jianying 导出能力，已有原生剪映出口继续保留。可研究/引入概念选择、视觉语法、场景计划、审稿方法；不能把新GUI或整个Backlot平台当必要前提。

## 排除的搜索结果

- 搜索结果曾返回 `Open-Montage/OpenMontage` 和 `sarvob/paperedits`，本轮这两个地址的 GitHub API 为 404。后续已核实 **`calesthio/OpenMontage` 是可访问有效项目**，上文已补入；不能因旧 owner 404 就排除整个项目。`sarvob/paperedits` 本轮未恢复有效地址，不计数。
- 不以“视频编辑”名义将扩散模型的局部视频重绘/人物替换混入现有实拍的时间线叙事剪辑。
- AIcut、CutClaw、DIRECT-Claw、MovieAgent、Video Editor Agent 的许可问题逐项披露；主代理应另补足许可明确项目，确保用户要求的至少 30 个开源项目不靠这些条目凑数。
