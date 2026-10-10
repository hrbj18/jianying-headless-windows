# 官方 lyra-cli 封装

`lyra-cli.exe` 是剪映官方提供给 Agent 的命令行接口，随剪映安装（本机为
`…\JianyingPro\Apps\11.5.0.14471\lyra-cli.exe`）。它不对外暴露 HTTP 接口，
只能作为可信宿主进程的子进程调用，因此本项目统一走
`engine/draftediting_runtime.py` 的 VMSDK 沙箱执行，再由 `engine/lyra_cli.py`
把参数与返回值规整成可测的 Python 接口。

## 命令域

| 域 | 作用 |
| --- | --- |
| `auth` | 登录、账号、凭据状态 |
| `draft` | 草稿的创建、编辑、算法、模板、导出（最庞大的一域） |
| `material` | 从剪映/CapCut 平台检索与下载素材 |
| `media` | 本地媒体处理与 AIGC 任务 |
| `lint` | 校验命令契约与验收证据 |

`draft` 下的子域（括号内为子命令数）：

```
project cover extract template(5) algo(21) history deform
edit video(28) sticker text(8) text-template audio(5) segment timeline
compound-clip filter effect(3) adjust subtitle(4) lyrics(4) keyframe(4)
config blueprint
```

完整清单与实测状态见 `docs/LYRA-CLI-MATRIX.md`。

## 清单驱动的 typed 封装

`engine/lyra_commands.json` 由 `tools/enumerate_all_commands.py` 通过剪映官方 VMSDK
真实调用每层 `<path> --help`、递归发现叶命令后生成。官方 `draft --help` 不公开
`video/text/subtitle` 等对象快捷域，因此工具保留一份文档化的**域级最低种子**，并把上一版
清单路径作为回归种子逐条实测；每个域下面有哪些新动作仍以实时官方 help 为准，不再硬编码
152 条动作树。`engine/lyra_commands.py`
再把清单里的每条命令装成同名 typed 函数：

```python
import lyra_cli

lyra_cli.video_speed(draft_root, ref, seg_id="v1", speed=2.0)
lyra_cli.algo_tts(draft_root, ref, text="你好", speaker="BV700_streaming")
```

四条约束（由 `tests/test_lyra_commands.py`、`tests/test_lyra_command_index.py` 与
`tests/test_lyra_command_enumerator.py` 守护）：

- **参数白名单来自实测参数表**：只要 `help_state == "ok"` 就严格校验，即使过滤全局开关后
  业务白名单为空也代表“该命令不接受业务参数”；只有 help 超时或为空时才允许未知业务参数
  原样透传，避免把官方新参数挡在门外。
- **全局开关始终禁止**：`--help` / `--version` / `--jq` 会改变命令行为（`--help` 会让
  命令挂住），无论 help 是否解析成功，都不能经 kwargs 或 `options` 传入；`options` 与
  kwargs 同样逐个校验 flag，重复指定 `--ref` 会直接报错。
- **索引只登记真正安装的名字**：手写封装优先，被顶掉的名字记入
  `COMMAND_MANUAL_OVERRIDES`；`COMMAND_INDEX` 里每个名字都能用清单签名
  `(cwd, timeout, ref, options, workspace)` 调用。
- **枚举失败不破坏权威清单**：探测结果先原子写入 `work/lyra-capabilities.json`；只有本次
  没有任何 help 失败、旧命令未消失、已成功参数表未退化、已知域齐全且成功率达标时，才
  原子替换 `engine/lyra_commands.json`。可用 `--evidence-only` 明确只取证；只有人工复核后
  才应使用 `--force` 接受退化结果。

参数名支持尾部下划线写法（`from_` → `--from`、`in_` → `--in`），因为 Python 里
`from` / `in` 不能直接作参数名。

## 前置条件

1. **剪映主进程在运行**：`lyra-cli` 会校验父进程，非可信宿主直接返回
   `unauthorized host process`。
2. **官方 VMSDK 与 `bun-packaged-server.exe` 就位**：
   `draftediting_runtime` 的 `doctor` 会检查并补齐。
3. **`LYRA_CLI_ALLOW_DEV_JIANYING_APP=1`**：本机剪映的 Authenticode 签名不被官方
   认可（`signature_not_official`）。官方在 `auth login --require-jianying-app` 的
   错误恢复提示里明确给出了这个**开发用开关**，`lyra_cli.run()` 默认把它作为
   `extra_env` 注入官方子进程（不再隐式改写宿主进程的 `os.environ`），用于复用本机
   已有的剪映登录态。
4. **登录**：需要账号权益的命令（歌词识别、素材下载、AI 算法）要求登录态。

### 登录（分步流程）

```python
import lyra_cli

link = lyra_cli.auth_login_link("/tmp")          # 拿到 login_url / device_code / user_code
# 把 link["login_url"] 交给用户打开授权（或渲染 link["qr_image_markdown"]）
lyra_cli.auth_login_complete("/tmp", link["device_code"], link["user_code"],
                             link["session_handoff"])
lyra_cli.auth_status("/tmp")                     # {"authenticated": True, "display_name": ...}
```

授权链接有效期 300 秒，过期重新调用 `auth_login_link` 即可。

## 歌词链路（已闭环）

对应剪映界面里的「字幕 → 歌词识别 → 歌词动效」：

```python
import lyra_cli

# 1. 官方歌词识别，结果写入草稿
recognized = lyra_cli.lyrics_recognize(draft_root, ref, language="zh")
cues = lyra_cli.recognized_cues(recognized)
sentences = lyra_cli.lyrics_recognized_sentences(recognized)

# 2. 套用官方歌词动效（本例为"浪漫氛围"）
lyra_cli.lyrics_animation_update(draft_root, ref, seg_id,
                                 "vimo://7591420714515844395")
```

整条流水线一行命令：

```powershell
python engine\headless_pipeline.py run `
  --draft "<草稿根>\测试 (1)" `
  --jypack "<工程>.jypack" `
  --out "C:\absolute\work\run" `
  --lyrics-engine official `
  --lyric-animation vimo://7591420714515844395 `
  --render
```

### 实测要点

| 观察 | 含义 |
| --- | --- |
| `lyrics recognize` 需要登录 | 未登录返回 `auth credential is missing: not logged in` |
| `--mode draft` 会**按来源重复识别** | 本工程 10 个音视频来源 → 同 10 句被识别 10 遍（返回 100 条）；`recognized_cues()` 按文本去重成 10 句。要精确控制可用 `--mode segment --seg-id <片段>` |
| `animation update` 只接受普通文本段 | 已套过动效的段类型是 `segment_text_template`，会被拒绝并提示 `expected one of: segment_text` |
| `animation add` 不接受 `--seg-id` | 草稿里有多组识别结果时它会报 `multiple lyrics recognize tasks found`，此时应改用 `update` |
| 套用动效会**重建并展开段落** | 原 `seg_id` 随即失效；因此批量处理必须每轮重新 `blueprint_sync` 取 id |
| **一次 `update` 就作用于整组歌词** | 实测套用一句后全片歌词都已带动效（渲染第 21 秒确认），无需逐句循环 |
| 官方命令只写 `Timelines/<id>/draft_content.json` | 渲染读根文件，落地后必须 `sync_draft_mirrors()` |

## 与其他开源方案的关系

| 方案 | 定位 | 渲染 |
| --- | --- | --- |
| pyJianYingDraft / pyCapCut | 生成剪映草稿 | ❌ 依赖剪映导出（剪映 7+ 的导出控件已隐藏） |
| duo-video | 生成剪映草稿（含文本模板） | ❌ "纯 Linux Headless" 仍是其愿景 |
| **本项目** | 官方 CLI 封装 + 原生 ExportService | ✅ 自编译 helper 直接调剪映渲染，支持已有草稿 |

也就是说，本项目在"无头渲染"这一环上比上述项目更进一步；而在"编辑能力"上直接复用
官方 CLI，不重复造轮子。

## 边界

- `draft template render` 是官方唯一的渲染命令，且要求 `--ref` 指向**新草稿工作区**
  （从 `--config` 生成），无法渲染任意已有草稿——这正是自编译 helper 存在的原因。
- GUI 交互（时间轴拖拽、预览播放、素材库可视化浏览）不在 CLI 能力范围内。
- 账号权益外的素材/算法会失败；`lyra_cli` 只转发官方命令，不代做授权。
