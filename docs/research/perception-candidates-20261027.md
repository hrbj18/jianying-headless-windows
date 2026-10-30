# 视频理解、审美与剪辑规律学习项目核验

日期：2026-10-27。研究子任务：为现有剪映项目找可学习的能力，不安装模型，不执行剪辑，不上传用户素材。只读取官方仓库、模型卡、论文与许可证；没有对候选模型做本机推理实测。

## 任务与评分边界

用户要跨风格的审美和编辑判断，不是固定模板。主代理已经抽帧确认本次参考偏财经口播、图表、关系图、金额标题、主持人小窗及新闻 B-roll；本机 RTX 3050 为 6 GB。因此通用图文/OCR/时间定位与声音理解比纯电影摄影分类更优先。这里不把检测到转场、懂摄影术语或模型自评分等同于大师级创作。

分数是针对本需求的主观适配评估，非论文成绩、成功率或实测排名。六项依次为：跨风格判断 30、时序/节奏 25、参考视觉拆解 15、接入现有剪映 15、可运行证据 10、成本 5。工程组件在前几项低分不等于软件质量差。所有输出接剪映都需要薄适配层；本轮没有验证现成的剪映连接器。

许可证在表中区分代码与模型/数据。标“公开研究”者不算已确认可自由商用的完整开源交付。

## 18 项评分总表

| 项目 | 分数 | 六项拆分 | 最有价值的能力 | 当前关键限制 |
|---|---:|---|---|---|
| [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | 83 | 25/18/14/14/9/3 | 读图表、OCR、布局、事件时间定位，统一拆解不同类型参考视频 | 不听音频；不能据此认定懂完整剪辑节奏；6 GB 需小模型/量化或远端，未实测 |
| [Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni) | 79 | 25/22/11/11/9/1 | 联合分析讲话、音乐与画面，补上单纯抽帧看不到的声音关系 | 官方 BF16 显存远超 6 GB；更适合少量关键片段远端审阅 |
| [InternVideo3 / InternVideo](https://github.com/OpenGVLab/InternVideo/tree/main/InternVideo3) | 77 | 24/22/11/10/8/2 | 长视频证据检索、时间定位、工具调用与反复验证 | 新研究部署，8B 等级且非剪辑器；不能假设 6 GB 本机可用 |
| [VideoChat3](https://github.com/MCG-NJU/VideoChat3) | 75 | 23/23/11/9/6/3 | 动作、长时序、流式视频；4B 模型具有成本吸引力 | 主仓库未检出 LICENSE；模型卡 Apache-2.0，代码许可仍需确认 |
| [VideoLLaMA 3](https://github.com/DAMO-NLP-SG/VideoLLaMA3) | 74 | 22/17/13/11/8/3 | 图表/文档/多图对比与视频时间定位，2B/7B 备选 | 旧依赖 CUDA/FlashAttention；未承诺 Windows 原生一键可用 |
| [ShotBench / ShotVL](https://github.com/Vchitect/ShotBench) | 72 | 25/12/14/10/8/3 | 专业景别、机位、光线、构图、运镜八维语言 | 单镜头摄影理解偏重，非整片剪辑；代码缺许可、训练代码未发布 |
| [LearningToCut](https://github.com/PardoAlejo/LearningToCut) | 68 | 21/21/7/9/7/3 | 从真实电影学习“这里切是否合理”，不只机械卡点 | 旧研究环境；局部切点排序不等于叙事规划 |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 64 | 7/18/10/15/9/5 | 可复核的场景切点与时长，为参考拆解提供时间基准 | 检测边界，不会判断这一剪辑为何优秀 |
| [MovieCuts](https://github.com/PardoAlejo/MovieCuts) | 63 | 22/17/8/7/6/3 | 区分动作切、反应切、J/L-cut 等专业切法 | 分类水平有限，数据需申请，旧模型依赖 |
| [VideoScore2](https://github.com/TIGER-AI-Lab/VideoScore2) | 62 | 18/13/13/9/7/2 | 输出可解释的视频质量、文本对齐、物理一致性意见 | 面向生成视频；不会评判财经讲解的论证与阅读节奏 |
| [Shot2Story](https://github.com/bytedance/Shot2Story) | 61 | 20/16/7/9/7/2 | 逐镜头字幕与跨镜头故事摘要，可学分层记忆结构 | 标注仅非商业研究，旧视觉/语言基座；不是剪辑器 |
| [TransNet V2](https://github.com/soCzech/TransNetV2) | 58 | 6/19/9/12/8/4 | 神经网络镜头边界检测，辅助复杂切换定位 | 无审美判断；旧 TensorFlow 路线需注意环境，另有 PyTorch 推理 |
| [Beat This!](https://github.com/CPJKU/beat_this) | 57 | 6/21/2/14/9/5 | 节拍与强拍时间，CLI/Python 可直接给剪辑计划使用 | 对口播信息节奏帮助有限，不能把所有切换吸到鼓点 |
| [librosa](https://github.com/librosa/librosa) | 55 | 5/20/2/14/9/5 | 节拍、起音、能量等可解释音频特征 | DSP 工具，不理解故事、语义或情绪是否恰当 |
| [Edit3K](https://github.com/GX77/Edit3K) | 54 | 14/8/13/10/6/3 | 学习效果、动画、转场、滤镜、贴纸、文字的视觉表示 | 数据约 1.74 TB 且 gated；不等于会选好效果，不是现成插件 |
| [DOVER](https://github.com/VQAssessment/DOVER) | 51 | 12/8/10/11/7/3 | 分开估计视觉美感与技术质量，辅助筛坏片 | S-Lab 非商业许可；审美分不是剪辑质量认证 |
| [madmom](https://github.com/CPJKU/madmom) | 48 | 5/20/2/11/7/3 | 成熟节拍、强拍与起音跟踪 | 代码 BSD，模型 CC-BY-NC-SA；旧依赖维护成本 |
| [FAST-VQA / FasterVQA](https://github.com/VQAssessment/FAST-VQA-and-FasterVQA) | 45 | 6/8/8/12/8/3 | 快速视频技术质量筛查 | S-Lab 非商业许可；无法判断结构与叙事 |

## 一手证据、实际状态与接入方式

### 1. Qwen3-VL

官方仓库提供模型下载、Transformers 推理和视频 cookbook；支持本地视频、带时间信息的帧序列、采样 fps 与像素预算控制。文档明确包含图文理解、OCR、视频事件时间定位，适合把参考拆成“此时讲什么、出现哪种图表、文字如何分层”。[README](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md)、[video cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/video_understanding.ipynb)。

代码 Apache-2.0，已核验的 8B Instruct 模型卡也标 Apache-2.0；其他大小的具体权重应逐个核对。[8B 模型卡](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)。仓库提供 2B/4B/8B 等版本；6 GB 显存不能把大模型 BF16 当作可直接运行方案。建议未来只对候选关键片段做小模型/量化可行性测试，或者使用独立推理服务，不改剪映的 Python 环境。输出镜头/图层描述 JSON，再交现有计划编译器；不会直接生成可编辑剪映工程，也不处理音频。

### 2. Qwen3-Omni

已发布代码和权重，官方 cookbook 涵盖音乐风格/节奏分析以及音视频同步问答；可补充“音效何时出现、话音与动画是否一致”等信息。[仓库与用例](https://github.com/QwenLM/Qwen3-Omni)。代码与所核验 30B-A3B-Instruct 权重为 Apache-2.0。[模型卡](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct)。

部署限制很实在：README 的 Transformers BF16 测试中，15 秒视频 Instruct 需 78.85 GB，Thinking 需 68.74 GB；不是 6 GB 显卡目标。官方有 Docker/vLLM 和 DashScope API 方案。适合后续按授权使用远端评审少量短片段，不能许诺免费本地连续审整条 14 分钟视频。输出分析意见，仍需时间基准与现有剪映执行器核验。这里推荐它是音画理解能力，不是让它替代剪辑决策。

### 3. InternVideo3

不是只列旧版 InternVideo2.5：主仓库已链接 InternVideo3、论文、8B 权重、训练数据及初期 Vidify agent。它把长视频理解设计为证据获取、工具调用与验证过程，适合作为长素材检索方案的参考。[代码入口](https://github.com/OpenGVLab/InternVideo/tree/main/InternVideo3)、[模型卡](https://huggingface.co/yanziang/InternVideo3-8B-Instruct)。

仓库及所核验模型卡标 Apache-2.0；推理示例使用自定义模型代码、BF16 和 Transformers。没有找到本机 6 GB/Windows 成功证据，不能把论文长视频能力转换成此电脑可常驻。可学习它的逐步检索与复核结构，未来服务输出时间区间；它并非剪辑时间线或审美专家。

### 4. VideoChat3

官方 4B 模型强调细粒度动作、长视频、时间定位与流式理解；仓库已发布推理、评测、训练代码和数据链接，不只是论文页。[README](https://github.com/MCG-NJU/VideoChat3)、[demo](https://github.com/MCG-NJU/VideoChat3/tree/main/demo)。

GitHub licenseInfo 为空，不能由“公开仓库”推断代码 Apache；[4B 模型卡](https://huggingface.co/MCG-NJU/VideoChat3-4B)明确 Apache-2.0。官方安装包含 torch、Transformers、decord、flash-attn，自定义代码；6 GB 的量化/采样实践未验证。相比 Qwen3-VL，此项目的视频时序研究价值强，但本条参考的密集图表/OCR不是其已证明优势。

### 5. VideoLLaMA 3

已发布 2B/7B 权重和推理代码；官方 cookbook 直接覆盖图表、表格、文档、多图比较、长视频和 temporal grounding，可用于多阶段素材说明。[README](https://github.com/DAMO-NLP-SG/VideoLLaMA3)、[推理例子](https://github.com/DAMO-NLP-SG/VideoLLaMA3/blob/main/inference/example_videollama3.py)。

代码和所核验 [7B 权重](https://huggingface.co/DAMO-NLP-SG/VideoLLaMA3-7B)均 Apache-2.0。官方指定 CUDA >=11.8、PyTorch 2.4、Transformers 4.46.3、FlashAttention、decord 等。建议作为备选视频理解后端，不要直接装进现有 `.venv`；无 6 GB Windows 本机实测，也没有证据证明它会自动选出最佳剪辑方案。

### 6. ShotBench / ShotVL

非常贴近“学习电影语言”：ShotBench 有八个摄影维度，ShotQA 提供专业问答，ShotVL 有 3B/7B 权重。仓库发布计划中训练代码仍未勾选，评测代码与模型已发布。[仓库](https://github.com/Vchitect/ShotBench)、[论文](https://arxiv.org/abs/2506.21356)。

GitHub 根许可证 API 返回 404；[ShotVL-3B 模型卡](https://huggingface.co/Vchitect/ShotVL-3B)标 Apache-2.0，并给图像/视频推理例。不能把模型许可外推到整个代码、数据或电影片段。官方评测用 4 GPU 是批评测示例，不等于单次 3B 推理必需 4 卡；也不能由此承诺 6 GB 运行。对机器狗实拍构图诊断有价值，但八维分类准确率不证明能完成财经图形叙事或整片节奏。

### 7. LearningToCut

这是直接研究剪辑决策的冷门项目。官方论文让模型从真实电影剪辑学习细粒度视听切点模式，排序候选切法；发布代码、特征、模型链接和推理脚本。[仓库](https://github.com/PardoAlejo/LearningToCut)、[论文](https://arxiv.org/abs/2108.04294)。代码 MIT；数据、电影素材与外部检查点需分别核验，代码 MIT 不覆盖电影版权。

环境文件锁 Python 3.9、PyTorch 1.9、CUDA 11.1 并含 Linux 构建标记，默认 shell 脚本。Windows 应视为移植/WSL 研究项目，未做本机验证。最值得借鉴的是从多个候选切点中比较，而不是把同一模板铺到所有片段。它只处理局部切点合理性，不规划整片讲述、图表或观众理解。

### 8. PySceneDetect

BSD-3-Clause；现成 Python API、CLI，官方有 Windows MSI/portable ZIP。用 OpenCV 检测场景切换，ffmpeg/mkvmerge 可选用于分片。[仓库](https://github.com/Breakthrough/PySceneDetect)、[官方文档](https://www.scenedetect.com/docs/latest/)。

能低成本得到可复查的切点/时长，给参考片拆解提供客观基础；不需大语言模型/GPU。图形动画内部变换、快速闪白可能误判，阈值和人工校核仍必要。它测量节奏，不解释节奏；应作为配套组件，不能独占“审美升级”前三名。

### 9. MovieCuts

代码 MIT，实际仓库有训练/推理、预训练检查点链接。十类包括动作切、反应切、交叉切、J/L-cut 等，适合让系统建立剪辑语法词汇。[仓库](https://github.com/PardoAlejo/MovieCuts)、[论文](https://arxiv.org/abs/2109.05569)。

必须保留性能边界：README 展示 mean AP 47.91%，Match Cut AP 2.43%，不能说已达到专业剪辑师识别水平。数据访问需表单/邮件授权；环境说明与 YAML 依赖版本还存在差异（README 写旧 PyTorch 1.8，YAML 为 1.10）。对 Windows/6 GB 无即用保证。优先学习分类体系，不建议把分类结果直接当剪辑命令。

### 10. VideoScore2

MIT 代码，有单视频推理和训练入口；目标是解释生成视频的视觉质量、文本对齐与物理一致性。[仓库](https://github.com/TIGER-AI-Lab/VideoScore2)、[推理入口](https://github.com/TIGER-AI-Lab/VideoScore2/blob/main/vs2_inference.py)。权重许可应按实际选择的模型卡另核查，本轮未把代码 MIT 扩展为所有模型许可。

可用于未来生成 B-roll/动画素材筛查；本条参考是口播与信息结构，不能靠物理一致性/提示对齐得分判断讲述是否清晰、图表是否读得完。PyTorch/Transformers 推理依赖，不是 6 GB 已验证插件，更不是通用审美真值。

### 11. Shot2Story

公开多镜头描述、长摘要、检索和视听问答基准及模型实现。代码声明 Apache-2.0，文本标注明确 CC-BY-NC-SA 4.0，仅非商业研究。[仓库许可段](https://github.com/bytedance/Shot2Story#license)、[数据说明](https://github.com/bytedance/Shot2Story/blob/main/DATA.md)。

可学习“镜头级事实—段落摘要—全片结构”的共享记忆组织，改善长视频上下文；不能把研究数据直接放进商用记忆库。旧基座及多个依赖增加部署成本；文本摘要不会替代对成片节奏的试听。

### 12. TransNet V2

MIT；提供已训练镜头边界检测网络，既有 TensorFlow 推理也有 PyTorch 推理目录，不需要重新训练。[仓库](https://github.com/soCzech/TransNetV2)、[PyTorch inference](https://github.com/soCzech/TransNetV2/tree/master/inference-pytorch)。

用于测参考镜头边界，特别是纯阈值不稳定的位置。能向现有素材分析缓存提供镜头区间，不能确定动画内部的信息变化、叙事段落或剪辑动机。Windows 依赖版本要隔离验证；具体显存未见可据以承诺的本机证据。

### 13. Beat This!

代码与发布权重都明确 MIT。提供 CLI 与 `File2Beats`，输出 beats/downbeats；默认 GPU，不可用时可 CPU，主模型约 78 MB，小模型约 8.1 MB。[README](https://github.com/CPJKU/beat_this)、[许可证](https://github.com/CPJKU/beat_this/blob/main/LICENSE)。

本机友好，是音乐主导段落的可靠配套方向。原训练音频版权不等于开放权重许可，仓库有说明。对本次讲解片优先级低于句意/图表阅读时间，不能把“卡点准确”当“节奏高级”。不需改动剪映引擎，只输出时间标记。

### 14. librosa

ISC 许可，成熟 Python 音频分析库，提供节拍、起音、tempo 等函数，可在 CPU 使用。[仓库](https://github.com/librosa/librosa)、[beat tracking](https://librosa.org/doc/latest/generated/librosa.beat.beat_track.html)。

适合统一缓存能量和音乐节拍，并与真实切点比较；没有故事/审美模型。对无明显鼓点、复杂变拍、语音为主的内容不可机械套用。Windows 可通过常规 Python 包安装，但本轮未安装验证。

### 15. Edit3K

准确仓库为 `GX77/Edit3K`，MIT 代码。研究六类编辑组件：效果、动画、转场、滤镜、贴纸、文字；目标是把效果特征与底层素材分开，支持检索和推荐。[仓库](https://github.com/GX77/Edit3K)、[论文](https://arxiv.org/abs/2403.16048)。

数据卡显示 gated 访问、总量约 1.74 TB；需要同意账户信息分享条件，许可证元数据缺失，不能自行推定商用权利。[数据卡](https://huggingface.co/datasets/Gstar666/Edit3K)。代码提供 train/test 与 embedding 入口，本轮没有找到 README 中明确的一键预训练推理交付；不能承诺下载即识别参考效果。可学习效果分类/检索结构，6 GB 本机不宜启动其全量训练。识别某种效果并不判断它是否应该加入。

### 16. DOVER

有代码、权重和推理，分开建模美感与技术质量。[仓库](https://github.com/VQAssessment/DOVER)。但许可证是 S-Lab License 1.0，明确仅允许非商业用途，商用需联系贡献者。[LICENSE](https://github.com/VQAssessment/DOVER/blob/master/LICENSE)。

可研究如何把模糊/压缩损伤与美感区分；不宜直接作为商用生产默认组件。模型训练于特定主观质量数据集，不能裁决叙事、信息图阅读或参考节奏。

### 17. madmom

音频节拍/强拍/起音研究工具，实际代码与预训练模型齐备。代码为 BSD 风格，数据/模型为 CC-BY-NC-SA 4.0。[仓库](https://github.com/CPJKU/madmom)、[LICENSE](https://github.com/CPJKU/madmom/blob/main/LICENSE)。

有历史依赖负担，Beat This README 也指出 PyPI 旧版 Python/NumPy 限制。商业内容生产优先考虑许可更清楚的 Beat This，而不默认复制 madmom 预训练模型。仍只负责音乐分析。

### 18. FAST-VQA / FasterVQA

发布推理、训练与权重，面向高效视频质量评估；与 DOVER 同属研究线。[仓库](https://github.com/VQAssessment/FAST-VQA-and-FasterVQA)。同样采用 S-Lab 非商业许可。[LICENSE](https://github.com/VQAssessment/FAST-VQA-and-FasterVQA/blob/dev/LICENSE)。

适合质量筛查研究，不是审美导演。它的低分源于本次目标是跨风格剪辑与讲述，而不是压缩质量/清晰度监测。

## 本分组最值得保留的三个方向

1. **Qwen3-VL：首选感知层。** 对本条参考的图表、文字、布局和画面语义最合适；模型输出须附具体时间及画面证据，后续在 6 GB 上仅验证小模型或量化方案，不能承诺 8B 直接跑。
2. **LearningToCut：首选剪辑决策研究样本。** 直接研究多个切点的优劣，比堆“高级转场”更接近学习编辑思路。建议借鉴候选切点比较与真实剪辑证据，不建议现在移植整套旧训练栈。
3. **ShotVL：首选电影语言补充。** 用于实拍素材的景别、构图与运镜分析；对本条图形讲解片不是唯一核心。模型许可与代码许可分开，训练代码缺失使其更适合研究/独立推理验证，非立即全面整合。

这不是总体推荐前三；主代理应将它们与时间线执行、信息图/动态图形及编辑 Agent 项目比较。尤其本次参考需要能制作可读信息图的执行层，本分组没有任何项目独立覆盖完整任务。

## 明确未完成的验证

- 没有安装或推理任何候选模型，没有 6 GB 性能/质量实测。
- 没有获取受限数据或提交申请；没有上传参考片、原素材或账号信息。
- 未声称 Windows 原生、API 成本或远端服务当前可用已经验收。
- 没有改现有剪映引擎、草稿、原素材及已交付视频。
