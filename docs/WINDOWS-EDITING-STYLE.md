# Windows 剪辑风格蒸馏与复用

正常入口为 `jianying.ps1 style`。流程参考女娲的本地语料研究、条件规则提炼、
真实范例、留出验证及新任务检验，将输出接入已有剪映原生构建/播放器/ExportService。
脚本负责证据与时间验证，当前 Agent 实际查看参考画面并提交语义判断。

## 研究并冻结风格

参考片先按[素材分析闭环](WINDOWS-MATERIAL-ANALYSIS.md)完成 `analyze prepare`。
语义与声音判断需要对应证据；截图生成本身不代表视频已审阅。
按题材选不同参考，独立留出部分视频，先提炼训练规则再检查留出；离群作品说明原因后排除。

创建 `references-list.json`：

```json
{
  "name": "我的剪辑风格",
  "tasks": ["D:\\JianyingHeadless\\work\\reference-a\\task.json", "D:\\JianyingHeadless\\work\\reference-b\\task.json", "D:\\JianyingHeadless\\work\\reference-holdout\\task.json"],
  "holdout_task_ids": ["<第三项的真实任务ID>"]
}
```

```powershell
.\jianying.ps1 style prepare --references-list D:\JianyingHeadless\work\references-list.json `
  --out D:\JianyingHeadless\work\style-study
.\jianying.ps1 style read --study D:\JianyingHeadless\work\style-study\study.json
```

`read` 返回提交模板。实际检查各参考多宫格，必要时取密集源帧辨认开头、字幕和片尾；
总结“何时这样剪、为什么、哪些情况不适用”，并给出源时间与真实格子/ASR 范例。
模板要求：

| 字段 | 内容 |
| --- | --- |
| study_id/version/model | 研究身份、正整数版本、实际审阅模型标签或明确未知标签 |
| summary/unknowns | 结论与具体不足，区分观察和推断 |
| reviewed_sheets | `{task_id,sheet_ids}`：实际查看过的整页 |
| examples | `{id,task_id,start,end,cell_ids,asr_ids,observation}`：源秒、实帧和重叠语句 |
| rules | `{id,dimension,when,action,avoid,support,parameters}`：条件、动作、例外及范例 ID |
| holdout_evaluations | `{task_id,observations,rule_ids,cell_ids,asr_ids}`：独立检验，反例如实保留 |

规则维度包括 selection/narrative/pacing/subtitles/framing/audio/graphics。
每条规则至少两个不同训练源支持；留出片不能作为训练范例。例子的图片实际时间须在所述区间，
ASR 须重叠，声明审阅页须确实包含该格子。字幕和音频特征分别核对，字幕文本不是声音效果证据。

`parameters` 可约束已验收原生投影的数值区间：subtitle_max_chars、subtitle_size、subtitle_y、
title_size、title_y、video_scale。文字描述仍需 Agent 判断，程序不会自动认定“好笑”或“温暖”。

```powershell
.\jianying.ps1 style distill --study D:\JianyingHeadless\work\style-study\study.json `
  --submission D:\JianyingHeadless\work\style-submission.json `
  --out D:\JianyingHeadless\work\style-profile-v1
.\jianying.ps1 style inspect --profile D:\JianyingHeadless\work\style-profile-v1\profile.json
```

profile 冻结规则、范例、相关图格与 ASR 时钟摘要、独立源哈希及研究清单；外层身份是这些内容
的哈希。普通 `inspect` 离线复核规则语义、独立源、留出隔离与数值约束，无需重开全部参考。
`--verify-references` 会回读原研究任务及图片/转写哈希，适合来源仍在时的完整复核。
profile 或提交修改须新版本、新输出目录；不能覆盖旧版或只改表层 ID 绕开验证。

## 用于新素材

**成片精修**：基础片显得单薄，或用户要求调整节奏、动态构图、反应窗、图形与声音时，先读
[参考风格成片精修](WINDOWS-STYLE-PRODUCTION.md)。该分支保留 `compile_style()` 的基础
plan/audit，在私有任务目录另编完整 native plan，再走正常 `build/preview/export/publish`；
下面的 `style assemble` 字段与参数保持现有契约。粤仔的作品决策使用该页指向的精修规则。

新素材先完成 `analyze read/submit/detail`，形成真实候选与精查选择；selection 格式沿用素材分析
文档。可以在同一故事内部先取高光再回到语境，所有选区都必须有候选、精查和真实源时钟支持。

treatment 显式说明执行哪个版本、哪些规则，以及具体的原生文字参数：

```json
{
  "profile_id": "<inspect返回的id>",
  "name": "粤仔风格01-完整故事",
  "rule_ids": ["R01", "R03", "R04", "R05", "R06", "R08"],
  "notes": "本条为何这样选、哪些地方符合规则，以及有意的变化",
  "subtitle": {"max_chars":10, "size":10.5, "y":-0.56, "color":"#FFC33D", "border_color":"#000000", "border_width":0.06},
  "titles": [{"text":"实际有证据的编辑标题", "start":0, "end":2, "size":16, "y":0.55, "color":"#FFF0A0", "border_color":"#000000", "border_width":0.06}],
  "video_scale": 1,
  "font_path": "C:/Windows/Fonts/Dengb.ttf",
  "subtitle_replacements": [],
  "subtitle_omissions": []
}
```

`name/font_path/subtitle_replacements/subtitle_omissions` 可选。标题时间为最终成片秒，
当前单独文字轨上的标题须按顺序不重叠、位于成片内；底部口播字幕单独一轨。
名称须是 Windows 安全单目录组件，使用独立名称避免覆盖首页旧工程。
字体必须是本机可解析的独立 TTF，随构建复制和校验；省略则沿用默认字体。

纠错格式 `{from,to,asr_ids,reason}`，限同长度、数字不变、真实入选 ASR 单位且精确匹配一次，
沿用覆盖的原整词时钟。不要把未知句重写成看似精确口播。歌词/方言不能确认时可用
`subtitle_omissions:[{asr_ids:[...],reason:"具体原因"}]` 整句省字幕，保留原音并逐句审计。
同一句不能同时修写与省略。编辑标题为独立文字，不伪装成主播说过的话。

```powershell
.\jianying.ps1 style assemble --task D:\JianyingHeadless\work\live-analysis\task.json `
  --selection D:\JianyingHeadless\work\selection.json `
  --profile D:\JianyingHeadless\work\style-profile-v1\profile.json `
  --treatment D:\JianyingHeadless\work\treatment.json `
  --out D:\JianyingHeadless\work\styled-edit-01 --render
```

复用真实源选区、原声 1x/volume 1、词时钟字幕和原生缩放/普通文字，保存计划、selection-audit
与风格/profile/treatment 身份，再调用同一原生预览与导出。未传 `--render` 只构建。
未知字段、参数越界、变更证据或缺失精查会停止；不能用静默省略资源掩盖未支持效果。
贴纸、第三方影片表情和复杂模板没有在此接口新增支持，参照[视觉效果边界](WINDOWS-VFX.md)。

实际检查切点、字幕、脸与狗的位置、动作与原声，验收成片后如用户要求首页可见：

```powershell
.\jianying.ps1 publish --build D:\JianyingHeadless\work\styled-edit-01\build `
  --audit D:\JianyingHeadless\work\styled-publish-01
.\jianying.ps1 verify --build D:\JianyingHeadless\work\styled-edit-01\build
```

沿用[正常调用指南](WINDOWS-CLI.md)的精确版本和关闭剪映门禁；不直接拷贝 draft 绕过素材路径重定位。
登记后的工程与 MP4 是不同产物，交付同时列出名称、时长和路径。

## 安装粤仔风格 skill

```powershell
.venv\Scripts\python.exe tools\install_codex_skill.py --name yuezai-editing-style `
  --profile D:\JianyingHeadless\work\style-profile-v1\profile.json
```

安装主文、研究摘要、规则范例与冻结 profile 到本机技能目录，绑定当前项目。
profile 直接保存在安装副本中；日常复用不重新收费识别参考。源码技能只含规则/研究摘要，
不携带原视频或凭据；原始任务追溯保留在用户私有工作目录。

本次真实参考库及四条直播验收结果见[风格验证记录](WINDOWS-STYLE-VALIDATION.md)。参考分析覆盖范围在
[粤仔实证观察](../skills/yuezai-editing-style/references/research/observations.md)中明确说明。
