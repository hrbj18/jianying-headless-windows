# Windows 素材理解到剪映剪辑

正常入口为 `jianying.ps1 analyze`。本地工具抽取真实帧、拼图和音频；百炼执行云端 ASR；
当前 Agent 查看图片、结合语音证据提交候选。候选精查与切点选择完成后，同一入口生成可编辑
剪映构建，并调用剪映播放器和 ExportService 预览、导出。全程使用接口和子进程。

## 本机配置

使用项目隔离环境安装可选依赖，并运行只读体检：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-analysis.txt
.\jianying.ps1 analyze doctor
```

需配置 FFmpeg/ffprobe；配置格式见 [local-settings.example.json](../local-settings.example.json)。
`analysis.credential_files` 可引用海客项目现有的 `.env.secrets.local` 和 `.env.local` **绝对路径**。
仅加载 `DASHSCOPE_API_KEY` 与可选 `DASHSCOPE_WORKSPACE_ID`；优先级为进程环境、文件列表顺序，
不插值、不修改进程环境。配置只保存文件位置，密钥不进入版本库、CLI 摘要、Skill 或交付包。
本机配置文件已忽略。换账号会改变缓存身份。

`asr_model` 目前固定 `qwen-audio-3.1-asr-flash-filetrans`；`chunk_seconds` 为 10..600 秒，默认 600。
每块为单声道 16 kHz PCM WAV，600 秒约 19.2 MB，低于本接口的 24 MiB 本地限制。
通过百炼临时 OSS 授权直传音频，再提交异步转写。上传范围是所选素材的音轨，模型返回真实
语句与词时间戳，按音频块起点换算为源视频秒数。`doctor` 校验配置，不发云请求。

有用户云端调用授权后使用 `--asr bailian`；`--asr none` 完全跳过云转写，不生成虚构字幕。
授权可来自同一会话已有指示，无需反复确认。先核对 source 与时长；长片会依次提交所有音频块。
云端实际账单以服务商为准：保存原始 usage、task ID，`cost_cny:null` 表示没有取得实际费用。

## 证据与分层审阅

所有输出目录使用包含 `work` 路径段的绝对 ASCII 路径。

```powershell
.\jianying.ps1 analyze prepare --source D:\media\live.mp4 `
  --out D:\JianyingHeadless\work\live-analysis `
  --goal '找到产品容量与使用方法的完整介绍，保留原声' `
  --model '<实际执行审阅的模型标识，未知时明确标 unknown>' --asr bailian

.\jianying.ps1 analyze read --task D:\JianyingHeadless\work\live-analysis\task.json `
  --chapters CHAPTER-003 --text-budget 6000
```

`read` 返回真实图片绝对路径、格子 ID、源 PTS、对应章节范围、有限文本和审阅模板。
`--query` 为 ASR 文本子串过滤，不执行或冒充语义检索；查看 `matching_units/returned_units`，
按需分章节读取，不能将截断文本当作完整转写。`--model` 记录审阅者身份标签，
不调用该名字对应的云视觉 API，也不代表脚本独立完成了语义判断。

总览预算参考海客分层设计：

| 时长 | 章节 | 抽样预算 | 每页 |
| --- | --- | --- | --- |
| ≤45 秒 | 1 | 18..81 张 | 3×3 |
| ≤10 分钟 | 1 | 81 张 | 3×3 |
| ≤1 小时 | 6 | 96 张 | 4×4 |
| >1 小时 | 每约 10 分钟一章 | 每章 16 张 | 4×4 |

两小时为 12 章、192 张抽样预算。每章隔张保留覆盖锚点，其余均匀样本按感知哈希与颜色去重；
只减少拼图中的重复格，不删除锚点或原始证据。当前没有移植海客的全部场景/运动优先算法。
超过一小时的 `read` 默认只返回章节索引与有限转写，状态为 `chapter-selection-required`，
不会一次附上全部图片；根据目标或 `--query` 选章节，再显式传 `--chapters` 加载相应多宫格。
格子显示实际解码 PTS，生成请求时间与实际时间分别保存；最大偏差 1.1 秒，超限停止。
低帧率片尾没有对应帧时，仅做有界回退并保留真实时间。单视频流、至多 24 小时；
不支持的流或时间偏差应报错，不能填造时间戳。

多宫格节省的是请求数量和重复信息；图片像素仍消耗视觉上下文，不宣称 token 按宫格数等比减少。
总览可漏掉短暂动作、细字和瞬时事件。按目标筛章节、对候选精查，再对重要动作或切点进一步缩小区间。

逐张实际查看目标章节的多宫格；语句是语音证据，格子才是视觉证据。将 `read` 的模板保存为
`review-submission.json`，填入总结、未知项与候选。例子中的 ID 必须替换为本次返回值：

```json
{
  "task_id": "<read 返回的 task_id>",
  "model": "<与任务相同的审阅模型标签>",
  "reviewed_sheet_ids": ["CHAPTER-003-S001"],
  "summary": "实际看见的内容及与任务的关系",
  "unknowns": ["尚未查证的动作或语音陈述"],
  "candidates": [{
    "id": "CLIP-001", "start": 1201, "end": 1216,
    "reason": "该源区间满足目标的具体证据",
    "evidence_cell_ids": ["CHAPTER-003-S001:R1C1"],
    "asr_ids": ["ASR-000123"]
  }]
}
```

```powershell
.\jianying.ps1 analyze submit --task D:\JianyingHeadless\work\live-analysis\task.json `
  --submission D:\JianyingHeadless\work\live-analysis\review-submission.json
.\jianying.ps1 analyze detail --task D:\JianyingHeadless\work\live-analysis\task.json `
  --candidate CLIP-001 --start 1201 --end 1216 --fps 2
```

候选引用须属于实际声明审阅的章节，格子实际时间须落在候选内（容差 1.1 秒），
ASR ID 须与候选时间重叠。`detail` 只允许候选内区间，
0.5..5 fps、每次最多 24 帧；超预算改为均匀抽样，结果明确标注，不能理解为连续 2 fps 播放。
需要更密的切点证据时对短子区间再次 `detail`。查看全部返回精查图，并核对 ASR 时间或播放原声，
声明实际检查方法；没有听过原声就不能填 `playback`。

## 选择与原生输出

将最终选择存为 `selection.json`；此处的 `review_sha256` 是 `review.json` 的
`submission_sha256`，`detail_index` 是 `detail` 返回的 `path`：

```json
{
  "task_id": "<任务 ID>",
  "review_sha256": "<审阅提交 SHA256>",
  "subtitles": true,
  "clips": [{
    "candidate_id": "CLIP-001", "start": 1201.1, "end": 1215.9,
    "detail_index": "D:\\JianyingHeadless\\work\\live-analysis\\details\\<id>\\evidence.json",
    "reviewed_detail_sheet_ids": ["CLIP-001-S001", "CLIP-001-S002", "CLIP-001-S003"],
    "audio_review": "asr-timing"
  }]
}
```

`audio_review` 可为 `asr-timing`、`playback` 或无音轨源的 `silent-source`。有音轨不能冒充静音；
ASR 检查须有真实重叠语句。选择必须在候选及所引用精查范围内，必须声明看过该次全部精查页。

```powershell
.\jianying.ps1 analyze assemble --task D:\JianyingHeadless\work\live-analysis\task.json `
  --selection D:\JianyingHeadless\work\live-analysis\selection.json `
  --out D:\JianyingHeadless\work\live-edit --render
```

产生 `edit.plan.json`、`selection-audit.json`、不可变 `build/`、`preview/` 和 `export/render.mp4`。
`--render` 调用真实剪映原生播放器读取帧，再调用同一原生 ExportService 导出并完整解码检查。
不传 `--render` 则只构建、验证。沿用[原生预览](WINDOWS-NATIVE-PREVIEW.md)及平台版本限制。
切点向内对齐 30 fps，音视频保留原声 1x 和音量 1；无配音替换或语速压缩。输出画布沿用源尺寸。
文字按真实词时钟换算到新时间线，数字分词先合并以防拆行改变数值。没有词时钟时只接受完全
位于切段内的短整句；不为局部整句编造字词时间，未能安全生成的字幕不会伪造。

查看实际原生帧与成片，对切点前后、字幕数值、口播完整性和声音做验收。自动解码成功不等于
内容正确；`audio_review` 是如实声明，程序无法代替真实审阅。构建可继续走正常 `preview --build`、
`export --build`；用户需要首页可见时按[调用指南](WINDOWS-CLI.md)执行 `publish`，
不要直接拷贝构建中的草稿到首页目录而遗漏媒体路径重定位。

## 缓存、恢复与交付

源文件读取全量 SHA256，构建前再次核对；目标与模型标签属于审阅身份。相同素材跨不同剪辑
目标复用总览缓存；云端缓存还绑定账号指纹、模型、音频块、格式。缓存位于本机配置的
`workspace_root/analysis-cache/`，任务持有证据副本。图片、索引、转写、审阅、精查与选择之间
核对哈希和时间范围，改动停止执行；进程锁与原子 JSON 保存避免同一任务并发提交。

可原样重跑 `prepare`：完成的块读取缓存，已受理任务继续查询原 task ID；提交前先持久化
`submitting`，超时或断线造成受理不明时停在原状态，不自动重复收费提交，也不换服务商。
需人工核对云端记录后有意处理不明任务；不要删除记录来碰运气重发。已失败任务也保留记录。

同一输出目录不接受换素材、目标、模型、选择或改动后的计划；需要修订用新任务或新装配目录。
同一装配可重跑以验证既有构建、预览和输出哈希；失败产物保留供诊断，部分构建需换新装配目录。
重试导出不重复识别。缓存损坏时停止并检查证据，不静默重识别。

私有 provider 状态含临时云地址，留在本地；交付仅收录 MP4、可编辑构建/计划、审阅、选择与
脱敏 usage/验收摘要。不要将 `local-settings.json`、凭据文件、原始 provider task 记录或上传授权
复制进交付包。转写文字及截图也是用户素材，按该任务的交付范围处理。

## 本次验收

2026-10-19 在精确剪映 11.4.7.14462 上，用本机 SAPI 合成中文三段口播和静态示意图，
完成 44.27 秒源片的真实百炼转写、五页总览、候选三页精查、原生字幕剪辑与 14.8 秒/444 帧成片。
另以两小时无音轨合成片实跑 12 章/192 帧/12 页，并对低帧率尾帧与数字字幕断行补充回归检查。
这些是接口、证据流、缓存和原生输出验收；真实两小时直播的语义召回率仍需在用户素材上验证。

实现参考用户本机 `haike-workflow-2/Haike_video` 的 `backlot/bailian_asr.py`、
`lib/bailian_speech.py`、`backlot/material_overview.py`、`backlot/media_index.py` 与分层分析 runbook。
没有把海客整项目、凭据、模型或媒体打包进此仓库。
