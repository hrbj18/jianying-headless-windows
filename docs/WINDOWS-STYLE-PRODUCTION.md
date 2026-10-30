# Windows 参考风格成片精修

故事粗剪审阅后，需要进一步处理节奏、构图、文字、图形或声音时，使用本分支。
基础 plan/audit 可来自 `story compile`，也可复用 `editing_style.compile_style()` 的既有风格
基础；在私有任务目录另编完整 `jy14-headless-plan/v1`，通过 `build → preview → export` 验收。
首次独立交付使用 `publish/verify`；已有交付位修订使用 `delivery promote` 归档并替换旧版。
`style assemble` 的 treatment 字段与参数没有增加；本页不是新的 CLI 子命令。

参考研究、profile 和基础 treatment 见[风格蒸馏与复用](WINDOWS-EDITING-STYLE.md)。
粤仔风格的节点选择与作品完成边界见
[成片精修规则](../skills/yuezai-editing-style/references/production-refinement.md)；本页只定义执行契约。
运行前按[正常入口](WINDOWS-CLI.md)完成 `doctor`；以下扩展依赖精确 **11.4.7.14462**。

## 1. 保留基础证据，另建生产计划

先精查候选与源 ASR，按[干净粗剪](WINDOWS-STORY-EDITING.md)审阅删减后的故事。使用
`story compile` 时原样保留其 `plan.json/audit.json`；已有风格 profile 可沿用下述 Python API
生成基础。使用 style selection 时仍须通过已有源范围、候选和精查验证。下面仅示范该风格
基础分支，任务脚本从项目根运行：

```python
import copy
import json
from pathlib import Path
import sys

project = Path.cwd()
sys.path.insert(0, str(project / "engine"))
from local_config import configure_environment
configure_environment()
from editing_style import compile_style

job = Path(r"D:\JianyingHeadless\work\my-edit")
base, audit = compile_style(job / "task.json", job / "selection.json",
                            job / "profile.json", job / "treatment.json")
for filename, value in [("base.plan.json", base), ("base-selection-audit.json", audit)]:
    (job / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
production = copy.deepcopy(base)
# 在 production 中显式编排时间、轨道、关键帧和素材，再保存 production.plan.json。
```

基础 plan/audit 保持原样。生产脚本另存 `production.plan.json` 和 `production-audit.json`，记录
基础 plan、完整计划与源文件的哈希、story 或 selection 审计位置、参考证据、插入/重排与声音节点。
基础 profile 的数值约束只验证基础投影；后加的生产层须以独立审计和实际画面验收，不能称为
`style` 自动执行了全部风格规则。生产计划和用户素材留在私有任务目录，不加入源码。

完成条件：每个保留源段可追溯到已审阅选区；每个新增处理都有事件、作用、时间和素材来源。
轨道数量、特效数量与固定片长不作为作品质量门槛。
主题驱动剪辑可使用 `story compile` 的 `theme/contribution/retention_review`，将真实事件、
片段贡献与停顿范围投影到同一源/目标帧表；完整字段及两阶段文件绑定见
[主题与审稿契约](WINDOWS-STORY-EDITING.md#主题与片段贡献契约)。先保留已审粗剪，包装后用
该粗剪作对照并绑定实际生产 plan/MP4。检查视觉层级和文字进退时，优先保住人的表情、
动作和关系；“更紧凑”不等于机械增加切点。
奶奶主题试剪已实际走通两阶段文件绑定：短底板和关系句分层相对粗剪有可见阅读收益，
“耶”的独立闪字则删除，原声保留。复核文件与实际检查边界见
[本机验证](WINDOWS-STORY-EDITING.md#本机验证主题试剪的两阶段绑定)；
具体取舍见[试剪记录](../skills/yuezai-editing-style/references/research/theme-trials-20261020.md)。
多人喜剧的同期反应取景、原词递进与板字入场修正，见
[四姐妹三轮对标](../skills/yuezai-editing-style/references/research/sisters-iterations-20261020.md)；
它沿用本页同一正常入口，具体参数只作为该片已检查的案例。

## 2. 三种时钟与增删处理

| 时钟 | 含义与约束 |
| --- | --- |
| 源时间 | `source_start_us/source_duration_us` 与 ASR 词时钟；保留真实源位置 |
| 成片时间 | `start_us/duration_us`；主视频首轨从零连续，各轨内部有序且不重叠，辅轨不超出主轨结尾 |
| 片段局部时间 | `keyframes.<channel>[].at_us`；首点为零，严格递增且不超出该片段时长 |

所有 plan 时间为整数微秒，统一吸附到所选输出帧率；保存吸附前后差异。正常对白保留原速原音，
字幕沿原整词时钟投影。增删片段后，使用同一时间映射更新所有后续主段、字幕、图形、
SFX 与 BGM 节点；不能只改主视频。若在基础时间 `t_i` 插入时长 `d_i`，后续基础时间 `t` 映射为
`t + sum(d_i for t_i <= t)`。跨过插入点的字幕须回到原词边界重新分段，避免对白字幕停在静音插入上。

删除 `[a,b)` 时，该区间之后的目标时间统一减去 `b-a`。区间内的字幕、图形和声音节点明确
删除；跨区间的段按保留部分裁切或拆分，同步核对源范围、目标时长和局部关键帧。持续 BGM
明确选择裁掉对应音乐区间，或另铺连贯乐句；无论哪种，都重算尾部与内部对白闪避点。
增删结合时先建立统一的保留区间映射，再更新所有轨道，逐处复查切点前后和跨区段。

定格使用可追溯源帧 PNG，记录源文件哈希、精确取帧时间与图片哈希，作为原生 photo 段插入。
例如 0.6 秒定格：`source_start_us:0, source_duration_us:600000, duration_us:600000,
speed:1, volume:0`。取帧只生成源图片，后续叠层与视频编码由剪映完成。

回放的使用先按精修规则判断新增信息价值；已经看清或刚播放的动作顺接反应，不能为了
展示能力重复。四姐妹本轮新增 2 秒回放被用户明确判为多余，这条反馈限于本题材。
确需短回放时另建视频段，满足 `source_duration_us / speed == duration_us`（数值误差不超过 2 微秒）。
例如 1.5 秒源动作以 `speed:0.75` 播放 2 秒，`volume:0`，同步显示独立“0.75×回放”标识；
正文先清楚呈现原速动作。回放无普通口播字幕，新增标签为编辑文字。速度变化段目前保持
静态构图，变速关键帧仍拒绝。定格和回放长度由事件决定，以上是制作范例。

完成条件：总时长、所有平移、插入范围与源区间逐项对得上；关键对白无重复、截尾或错位。

## 3. 原生画面层

主段可按事件使用短推近、回落和小幅位置变化。以下是**视频段内的局部字段示例**：

```json
{
  "speed": 1,
  "keyframes": {
    "scale": [{"at_us":0,"value":1},{"at_us":200000,"value":1.1},{"at_us":800000,"value":1}],
    "x": [{"at_us":0,"value":0},{"at_us":100000,"value":0.01},{"at_us":200000,"value":-0.01},{"at_us":300000,"value":0},{"at_us":800000,"value":0}]
  }
}
```

示例要求片段至少 0.8 秒；实际时间和幅度跟随本次事件。静态同名字段须与首关键帧值一致。
正向 1 倍裁切视频允许非零源入点，编译器将局部 `at_us` 映射到原生
`source_start_us + at_us`，调用方保持局部时间即可。文字支持局部 x/y/scale/rotation 动画；
PNG 视频层还可用 opacity 淡入淡出。精确范围以
[计划入口](../engine/jy14_headless.py)与[关键帧实现](../engine/native_motion.py)为准。

真正的同场反应窗使用另一个 `type:video` 轨，静音并指向相同现场时刻；保留“成片时间→源时间”
对应，不能把别处的笑容冒充同时反应。静态圆蒙版写在该 PIP 段：

```json
{
  "mask": {
    "preset":"mask/circle-soft",
    "config":{"width":0.3,"height":0.1425,"center_x":0.4,"center_y":0.3,"feather":0.02}
  }
}
```

宽高各按画布轴归一化；912×1920 画布中上述宽高近似正圆。蒙版 config 控制素材内部取景，
片段 `scale/x/y` 控制整个小窗的大小和位置，两者分别调节并实际取帧检查。
构建自动复制已审核原包到工程 Resources，并检查协议与完整资源字节；准确参数及其它
视觉效果见[Windows 视觉效果](WINDOWS-VFX.md)。本分支使用 plan 静态蒙版，完整工程保持不可变。

PNG 图形使用 `type:video` 辅轨，`source_start_us:0, speed:1, volume:0`，源时长与目标时长相等。
可使用透明全画幅图形，按主体位置重新布置内容。原生文字分成口播字幕、关键词和编辑评语；
同时出现且需要独立动画的文字分轨。普通句可退回干净画面，强调文字结束后及时退出。
复述口播的大字与口播字幕择一上屏；保留真实提问、回答、追问和有意义的问答回声，
去掉的是重复的编辑呈现，不是现场互动本身。

完成条件：每个动作、反应与文字的进入/退出都有实际预览；人脸、手、狗与字幕可读，蒙版
边缘正确，旁观者不会因裁切或小窗而被赋予源素材没有的反应。

### 漫画气泡底板与可编辑正文

多人回应的使用与身份判定按[精修 P11](../skills/yuezai-editing-style/references/production-refinement.md#p11-多人回应与全片焦点复审)。
生成器只做透明 **912×1920 PNG 底板**与可编辑 SVG 源，不写台词、不混音、不渲染视频。
SVG 保留命名的轮廓、尾巴、阴影与点缀，供后续改图；正常 plan 使用 PNG photo 段，正文另开
`type:text` 轨。这样在剪映仍可改字、改时长与位置，不把文字烘进图片。

```powershell
.venv\Scripts\python.exe tools\make_comic_bubbles.py `
  --out D:\JianyingHeadless\work\my-edit\bubbles `
  --variant dialogue --name reply `
  --rect 80 100 560 330 --tail 505 410 --accent pink
```

`--out` 必填且为绝对路径；示例产出 `reply-dialogue.png/.svg`。`--variant` 可选
`dialogue/concern/praise/all`，`all` 另存三款细节对照图；`--accent` 接受 `pink/blue/yellow`
或 `#RRGGBB`。`--rect X1 Y1 X2 Y2` 是底板正文区外框，`--tail X Y` 为框外尖端，均为
912×1920 源画布像素。默认坐标只是示范，按实帧空处和人物运动重新安排，尾巴保留声画依据。
Python API `render_bubble(out_dir, name, variant, rect=..., tail_tip=..., accent=...)` 返回素材路径。

以下是附加到已有主轨之后的两个**轨道片段示例**，主轨须覆盖该时段；文字内容替换为已核对
回应，具体字号和位置必须看原生帧：

```json
[
  {"type":"video","name":"reply backplate","segments":[
    {"source":"D:/JianyingHeadless/work/my-edit/bubbles/reply-dialogue.png",
     "source_start_us":0,"source_duration_us":1200000,"start_us":0,"duration_us":1200000,
     "speed":1,"volume":0,"scale":1,"x":0,"y":0}
  ]},
  {"type":"text","name":"editable reply","segments":[
    {"text":"此处填写真实回应","start_us":0,"duration_us":1200000,
     "size":8.4,"x":-0.29825,"y":0.77604,"color":"#292535",
     "border_color":"#FFF8E9","border_width":0}
  ]}
]
```

全画幅 PNG 保持 `scale:1,x:0,y:0` 时，正文中心像素 `(cx,cy)` 的原生位置近似为
`x=2*cx/912-1, y=1-2*cy/1920`，示例对应正文中心 `(320,215)`；字体实际框仍以渲染为准。
底板、正文绑定同一回应整词区间，时间吸附后同进同退；该回应不再另出一条底部字幕。
底板改位时同步重算正文中心。若用 x/y 关键帧移动整组，两轨局部时钟一致、各自基准位置
叠加相同位移；不让底板先退出、正文独留。按整段人物移动检查脸、手与尾巴指向，必要时
缩短、分段重排或省略。生成素材冻结后，仍走普通 `build → preview → export → publish/verify`
及不可变哈希验证；本功能未增加 `style assemble` 参数。

## 4. 独立声音与源资源生成器

正式 BGM 保存曲名、作者、原始来源、许可版本/使用范围、音频哈希及署名文本；按许可指定
形式完成署名。选段保留完整乐句与合适的收束，试听音乐起落是否贴合本条事件，再安排对白
闪避。缓存或已下载的文件不自动获得许可；声音素材、授权证据与成片内使用区间一并入审计。

本地生成器是可选图形/声音示范资源，其程序合成伴奏用于演示或占位，不默认选作正式成片
配乐；用户明确选择程序合成音乐时再按该目标验收。生成器使用单独依赖文件，按当前环境需要安装：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-production.txt
.venv\Scripts\python.exe tools\make_editorial_assets.py `
  --out D:\JianyingHeadless\work\my-edit\assets --seconds 90
```

生成器创建原创程序合成 WAV、透明 PNG 与 `assets.json`；它不混入对白、不合成视频。
`--seconds` 决定示范伴奏源长度。脚本中的全画幅图形坐标与装饰圈是示例位置，
复用前按新构图调整。先在新目录生成，完成编排后冻结素材；构建期间不重写它们。

SFX 与 BGM 均使用独立 `type:audio` 轨保留可编辑性；同轨有序不重叠，重叠声音另开音轨。
音量字段是线性增益。以源入点为零的 BGM 做局部 volume 关键帧，可在关键对白前降低音量、
句后恢复并于结尾收束，例如：

```json
{
  "volume":0.15,
  "keyframes":{"volume":[{"at_us":0,"value":0.15},{"at_us":500000,"value":0.08},{"at_us":1500000,"value":0.08},{"at_us":1800000,"value":0.15}]}
}
```

示例要求音频段至少 1.8 秒、`source_start_us:0, speed:1`；实际闪避时间绑定本次对白。
裁切音频关键帧仍需独立验收，当前保持拒绝。音效入点对齐动作落点，长度与音量按导出实际
音轨检查。声音素材来源、源/目标时段、增益和闪避点进入生产审计；参考声效未被听辨确认时，
将其记为本次原创制作选择，不能称为复原参考混音。

完成条件：导出对白清楚，声音标点与动作对应；记录实际检查方法，波形、峰值、相关性与
完整解码分别说明，只有真正试听后才声称试听通过。

短动作声在导出中可测、但起音仍不完整时，分别检查攻击与本体。实际声音三轮案例见
[四姐妹声音精修](../skills/yuezai-editing-style/references/research/sisters-audio-20261020.md)，
包括静音预卷与真实击打时钟的保留；具体机制和修复长度以该次验证为限。

## 5. 正常构建与交付

完整生产计划使用原有命令，不回写已构建快照：

```powershell
.\jianying.ps1 build --plan D:\JianyingHeadless\work\my-edit\production.plan.json `
  --out D:\JianyingHeadless\work\my-edit\build
.\jianying.ps1 preview --build D:\JianyingHeadless\work\my-edit\build `
  --out D:\JianyingHeadless\work\my-edit\preview --at 0.5 1.5 2.5 --width 640
.\jianying.ps1 export --build D:\JianyingHeadless\work\my-edit\build `
  --out D:\JianyingHeadless\work\my-edit\export --bitrate 12000000
```

预览时点改成本条的切点前中后、动画关键点、回放、声音落点与片尾；`--at` 必须在工程结束前。
**竖屏显式使用 `--width 640`**：默认宽度按原画布推算高度，细长竖屏可能超过 CPU 帧输出尺寸
限制而被拒绝。先确认 `native-frames-captured` 与时间戳，再查看 PNG；导出确认
`encoded-and-decoded`、帧数、时长、完整解码和源构建不变，并检查实际成片。

修改生产计划后新建输出目录重新构建；现有 plan、素材、字体和资源哈希由正常不可变构建门禁
约束。此路线的静态蒙版资源已随 build 复制；需要 typed 保存草稿编辑时改走对应文档及其审计，
不能修改 immutable build 后仍把旧验证结果当有效。

上例12Mbps是本机真人竖屏的已验证起点，按源质量和纹理选择，并查看ffprobe视频流实际
bit_rate；容器tag不等于实际码率。偏糊时先做同build不同码率对照，字形问题再独立比较，
见[清晰度案例](../skills/yuezai-editing-style/references/research/sisters-clarity-20261020.md)。

作品和技术验收都完成后，首次独立交付可登记首页工程：

```powershell
.\jianying.ps1 publish --build D:\JianyingHeadless\work\my-edit\build `
  --audit D:\JianyingHeadless\work\my-edit\publish-audit
.\jianying.ps1 verify --build D:\JianyingHeadless\work\my-edit\build
```

已有交付清单的精修按[固定交付](WINDOWS-DELIVERIES.md)使用 `delivery promote` 替换对应
交付位，旧修订进入可恢复归档；内部试剪与技术验证留在工作目录。开始精修时先按
[干净粗剪](WINDOWS-STORY-EDITING.md)检验结构和效果的必要性。
遵守发布时关闭剪映的门禁。交付列出成片、首页工程名、源范围、生产审计、
参考对照与剩余差距。首页索引核验、原生导出和主观作品验收分别陈述，
不以测试数量、轨道数量或自评分代替用户对成片的判断。
