# 从故事判断到干净粗剪

直播切片先确定观看理由，再编译原声粗剪。此流程负责使 Agent 的选段、保留与删除决定可复核；
编译器检查来源和时钟，作品判断仍由实际审阅承担。转场、滤镜和装饰不自动加入粗剪。

## 1. 选择结构

读取已缓存的事件地图、候选前后语境与 ASR，给每个候选写一句观看理由。以真实人物目标、
回应、动作或情绪变化组织段落。每段说明新增信息、观众期待、回报和保留理由；必要的等待、
尴尬或动作恢复也可以是有价值的段落。时长从取舍产生，不能按固定秒数强填事件。

先选一个最清楚的结构。只有另一个开场/顺序确有不同价值时才做对照；同一事件的两版试剪
属于一个交付位，不占用两条不同选题。跨段重排应保真实语义与关系，明确理由。

## 2. 正常编译

```powershell
.\jianying.ps1 story compile --treatment C:\task\rough.treatment.json --out C:\task\rough-compile
.\jianying.ps1 build --plan C:\task\rough-compile\plan.json --out C:\task\rough-build
.\jianying.ps1 preview --build C:\task\rough-build --out C:\task\rough-preview `
  --at 0.5 3.5 8.5 --width 640
.\jianying.ps1 export --build C:\task\rough-build --out C:\task\rough-export
```

`jy-story-treatment/v1` 绑定 `source{path,sha256}`、`transcript{path,sha256}`、`name`、
`canvas`、`promise`、`segments`、`overlay_decisions` 和 `omissions`。源帧区间使用
`source_start_frame`/`source_end_frame`，当前编译器采用 30fps。每段包含 `role`、
`new_information`、`expectation`、`payoff`、`why_kept`；倒序或重复区间须有 `reuse_reason`。
`overlay_decisions` 每项记录 `decision`、`added_information`、`attention_cost` 和 `delete_test`；
可明确决定保持干净。这些是待检验的编辑判断，不是填写完整即自动通过的审美认证。

编译器产出1倍速、原音量视频和一处普通字幕；字幕只来自真实 ASR 整词。
`omissions` 使用真实 `asr_id`、0-based半开 `word_start`/`word_end` 及理由。
它省略不可靠字幕，保留现场声音；不生成虚构台词或角色归属。
`audit.json` 记录全部源/目标时钟、词索引、来源哈希、量化误差及编辑动机。

普通字幕过小或盖住动作时，可在 treatment 顶层设置 `subtitle_style`，由编译器产出可读粗剪：

```json
{
  "subtitle_style": {
    "size": 11.3, "y": 0.68, "color": "#FFFFFF",
    "border_color": "#2B2925", "border_width": 0.068,
    "font_path": "C:/Windows/Fonts/Dengb.ttf"
  }
}
```

这只统一调整原 ASR 字幕的静态样式。允许 `size` 1～100、`x/y` -1～1、
`border_width` 0～1、`color/border_color` 为 `#RRGGBB`，以及可选本地 `font_path`；
字体相对路径以 treatment 目录解析，字体文件哈希进入审计，实际字体解析仍由原生 build 完成。
省略时保持旧的白字、黑边、字号 6 与 y=-0.74。位置与大小按本次原生画面检验，示例并非
通用安全区。文字、词时钟和原声保持原样；关键字动画与图形留给后续包装计划。
粗剪样式应在编译前固定，避免手改 plan 后无法绑定严格一致的粗剪审稿。

### 主题与片段贡献契约

批量选题或主题驱动重剪，在原 treatment 上增加以下可选字段；命令不变，旧输入继续兼容。
主题是一条能被真实动作、关系或答复兑现的观看线索，例如“嘴甜的夸赞得到一对夫妻的温暖
回应”。先找材料能支撑的变化，再写主题；素材不能支撑的宏大上升应明确作为编辑观点，
或放弃。编译器只校验声明的引用与时钟，不判定该解释是否真实、好看或可能传播。

以下是**附加字段示例**，不包含前述必填 source、transcript、canvas 等；数字为说明区间，
不能直接当作本机某条视频的素材证据：

```json
{
  "theme": {
    "statement": "一次尝试得到真实回应",
    "viewer_question": "对方会怎样回应这次尝试？",
    "payoff": "回应中看到关系变化",
    "events": [{
      "id": "E1",
      "source_start_frame": 300,
      "source_end_frame": 600,
      "observation": "记录实际看到或听到的动作与回应",
      "supports_theme": "解释这段事实怎样支持主题"
    }]
  },
  "segments": [{
    "id": "S1",
    "source_start_frame": 300,
    "source_end_frame": 450,
    "role": "尝试与等待",
    "new_information": "对方开始留意动作",
    "expectation": "是否会回应",
    "payoff": "后续回应承接本次尝试",
    "why_kept": "使回应有起因",
    "contribution": {
      "event_id": "E1",
      "theme_link": "保留关系变化之前的尝试",
      "focus": "发起者的动作与对方表情",
      "remove_cost": "回应会变成无来由的孤立镜头"
    }
  }],
  "retention_review": {
    "spans": [
      {"segment_id":"S1","source_start_frame":300,"source_end_frame":420,
       "kind":"action","focus":"动作是否完成","why_kept":"让动作过程可读","delete_cost":"缺少起因"},
      {"segment_id":"S1","source_start_frame":420,"source_end_frame":450,
       "kind":"hold","focus":"等待中的表情变化","why_kept":"让回应有自然准备","delete_cost":"答复显得抢接"}
    ]
  }
}
```

- `theme` 出现后，每个保留片段必须有 `contribution`，且完整落在所引 `event_id` 的源区间内。
  每个声明事件须有保留素材。动作、回应与同场反应沿同一源事件时钟核对；事件边界和观察
  本身仍是 Agent 声画判断，不能凭同一 ID 把别处笑容当成当时反应。
- `retention_review` 可省略，审计会明确标 `not-provided`。填写时，`spans` 按每个片段的
  源入点到出点连续覆盖，不能缺帧、交叠或超界；`kind` 为 `dialogue/action/reaction/hold/bridge`。
  按叙事或动作阶段拆分，段内有明显等待时单列 `hold`，写清视线目标、保留作用与删去损失。
  无需每秒一行，长动作和长停顿均允许；程序不靠 ASR 空白猜测画面是否空转。
- 审计的 `editorial_contract` 保留上述声明、每次片段出现的源/目标帧与微秒范围，以及各 span
  首、中、尾的 `review_target_frames`。重排或重复素材逐次映射，沿用原 `reuse_reason` 规则。
  这些点用于安排审阅，完整的起因、变化与回应仍需结合上下文看。

紧凑来自保留的信息与情绪贡献。快速切换本身不产生贡献；长镜头能持续提供动作、期待、
表情或关系变化时可以保留。片段有主题标签，也仍可能拖沓，审稿须指出具体弱区间。

## 3. 先审故事，再审处理

在实际粗剪中检查：开场是否容易进入，动作与答复是否完整，转折是否有来由，结束是否兑现
期待。对切点密集看前后画面，并结合原声检查句尾、接话、笑声与停顿；记录实际检查方法。
可用离散帧、转写与信号分析定位问题，但不能把这些记录成已经完成连续试听。
审阅者应给出否决理由；结构弱时回到源片取舍，不能以新增图层填满等待。

故事成立后再逐项考虑画面与声音。每项处理回答：新增什么信息、把视线从哪里移到哪里、
删除后损失什么。比较有无处理，保留确有作用的一项；同场原脸清楚且没有新表情信息时，
圆窗的资源可用、跟踪稳定和停留足够都不能单独证明其必要性。
对方回应框可以帮助分清接话；普通字幕足够时也可以保持普通字幕。角色归属规则沿用
粤仔 skill 的多人回应证据要求。

### 绑定粗剪和包装版的审稿

先编译、预览或导出干净粗剪并实际审阅；决定可以继续的范围与不确定项，然后再设计包装。
视线规则可借鉴 `visual-style-direction`，文字角色、语义分行和进/稳/退可借鉴
`title-kinetic-typography`。两者用于实现此条主题：先确定观众此刻看人、动作还是一句话，
再决定是否需要底板、关键词或动画。现场脸和动作已经清楚时，把阅读区让出来。

可将真实审稿填入 `retention_review.reviews` 后，再以同一 treatment 编译到新目录。每个记录
包含 `stage` 和 `plan/export/report` 三个 `{path,sha256}` 文件绑定：

```json
{
  "stage": "clean_rough_cut",
  "plan": {"path":"rough-compile/plan.json","sha256":"实际文件的64位小写SHA256"},
  "export": {"path":"rough-export/render.mp4","sha256":"实际文件的64位小写SHA256"},
  "report": {"path":"rough-review.json","sha256":"实际文件的64位小写SHA256"}
}
```

路径相对 treatment 所在目录解析；报告内容使用：

```json
{
  "schema": "jy-story-review/v1",
  "stage": "clean_rough_cut",
  "plan_sha256": "所审plan文件的实际SHA256",
  "export_sha256": "所审MP4文件的实际SHA256",
  "decision": "accepted_for_scope",
  "methods": ["sampled_frames", "signal_analysis"],
  "findings": ["记录实际检查的区间、因果和注意力发现；有问题写明位置与影响"],
  "remaining_limits": ["本次未连续播放或主观试听，声音听感尚未确认"]
}
```

`stage` 为 `clean_rough_cut` 或 `packaged_export`；`decision` 为 `revise` 或
`accepted_for_scope`，修订决定必须有具体发现。`methods` 只填写真正完成的
`sampled_frames/continuous_playback/subjective_listening/signal_analysis`，未同时连续播放与
主观试听时，必须写 `remaining_limits`。例如只读了转写，不可填写 `subjective_listening`。
采样画面可支持限定范围的继续制作决定，不能包装成完整视听末审。

编译器核验文件哈希与报告内 plan/export 哈希；粗剪报告的 plan 必须等于本次编译结果。
`packaged_export` 放在已声明 `accepted_for_scope` 的粗剪报告之后，绑定最终生产 plan 和
最终 MP4；其 report 额外填写 `rough_plan_sha256` 指向该粗剪 plan 文件，检查加层相对粗剪
的收益与代价。改了粗剪结构就重新审粗剪；改了生产计划或成片，
旧包装报告不再适用。审计仅返回 `hash-bindings-validated-not-aesthetic-certification`；
报告中的方法和判断仍是审阅者声明，脚本不播放媒体、不认证审美、不要求用户额外审批。

### 本机验证：主题试剪的两阶段绑定

2026-10-20 的私有任务位于 `D:/JianyingHeadless/work/theme-cuts-20261020`。
奶奶案例的 `grandma/themed-readable-v4.treatment.json` 由正常编译器产生与已原生导出的
`rough-compact-v2.plan.json` 字典完全相等的粗剪。静态字幕样式进入 treatment，原编译默认
不变；JSON 排版造成的字节差异不改变计划身份，但审稿仍绑定实际被审文件的 SHA256。
将实际粗剪、包装报告写入新的 `grandma/reviewed.treatment.json` 后，运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B .\jianying.py story compile `
  --treatment D:\JianyingHeadless\work\theme-cuts-20261020\grandma\reviewed.treatment.json `
  --out D:\JianyingHeadless\work\theme-cuts-20261020\grandma\reviewed-compile
```

该目录是本次已经产生的证据；复跑使用新的 `--out`，不要覆盖已验证输出。
`reviewed-compile/audit.json` 的两阶段状态均为文件绑定已验证，粗剪内容与原 native plan
相同；`qa/contract-reviews/grandma-binding-result.json` 保存文件全哈希及前后未改变的检查。
正常命令仍返回 `compiled-for-agent-review`，不把报告的 `accepted_for_scope` 升格成自动
审美通过。生产计划、原生输入和 MP4 不因绑定编译而重写。

奶奶最终审稿实际覆盖 64 个导出采样时点、8 组与粗剪同源对照及 5 个原生关键帧；
关系句按原时钟分层有阅读收益，删除“耶”的短闪字后人物笑容仍提供重点。无独立新增 BGM，
未连续播放和主观试听。

第二条 `companion/theme-v2.treatment.json` 的 753 帧、25.1 秒粗剪也完成双阶段绑定，
入口为 `companion/reviewed.treatment.json`，同一命令输出到 `companion/reviewed-compile`；
结果在 `qa/contract-reviews/companion-binding-result.json`。粗剪精确绑定
`rough-v2-compile/plan.json`，包装绑定 `production-v2.plan.json` 与最终导出。60 个导出样帧、
7 组粗剪对照、6 张原生帧支持上方语义分行与“靓姨／靓姐”的层次，报告仅声明抽帧检查。
BGM 的设计与信号记录不能代替听检，握手准备期的连续观看耐心仍有待复核。

两条共四份报告均验证哈希与先后关系，所有绑定原文件前后未改变。一次旧 752 帧粗剪实际
输出 753 帧被原生门禁拒绝；查看源收尾后另存 753 帧计划并重新验证，没有放宽门禁。
成功与删弃选择的完整边界见
[主题试剪记录](../skills/yuezai-editing-style/references/research/theme-trials-20261020.md)。

## 4. 独立审阅与固定交付

独立审阅同时评价故事和注意力成本，指出仍弱的段落；技术检查另列。轨道数量、帧数正确、
能导出、自评分或“全程有焦点”都不能替代“为什么还想看下一秒”的具体判断。
粗剪和加层版均保留作对照，验证有效后再使用
[固定交付](WINDOWS-DELIVERIES.md) 的 `delivery promote` 替换对应交付位。

## 四姐妹的正反例边界

本例最初的待检验方向是：自然握手目标、一次原速倒地、自起关切和嘴硬、自嘲、真实提问、
好姐妹/发小与接情收束。补回“你们四个是四姐妹吗”的问题，能够让后面的回答有明确起因；
从小发小后是否还需复述、结尾是否还需重复嘴甜，由完整语境和实际成片判断。
开头预告同一次倒地后再长时间铺垫、在翻身动作中重复放大主画面已有的脸，是本次需要
检验的负例。此案例不规定其他题材必须顺叙、必须倒地或必须使用相同问答结构。

本轮 28.6 秒导出从握手自然开场，约 5 秒处保留接触与失衡前的必要动作；删去源
5165.6～5167.1 秒的收手等待，源出点延至 5218.3 秒留住笑容。实际预览发现，成片
9.6 秒顶部首个关切框与下方翻身争抢焦点，删回普通字幕；21.7 秒的长尾会误指进入后景的
路人，改用短尾。后段保留三个有助区分接话的回应框，原声保留，字幕显示压缩重复问句。
这些取舍说明删减和必要动作应一起判断，小窗或对话框的资源可用不能代替注意力判断。

该版已通过编译、原生预览与 858 帧完整解码；主代理实际查看 70 帧三页的整片采样、切点和
气泡进退。8 段音轨的原声相关性为 0.982793～0.998288，信号检查未见削波；尚未实际主观
试听。技术通过与离散画面审阅不代替声音听感、作品末审或用户反馈，也不能据此认证批量
泛化。另一条两小时直播仍需留出验证；本例提供可复核的选择依据，不固定时长、构图或模板。

完成记录应包含被采用与被否决的结构、实际查看范围、仍不确定的声音/角色问题，以及最终
删掉哪些处理及其原因。下一场直播使用新素材验证规则，避免把一条片子的修补方案变成模板。
