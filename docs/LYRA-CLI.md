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

## 前置条件

1. **剪映主进程在运行**：`lyra-cli` 会校验父进程，非可信宿主直接返回
   `unauthorized host process`。
2. **官方 VMSDK 与 `bun-packaged-server.exe` 就位**：
   `draftediting_runtime` 的 `doctor` 会检查并补齐。
3. **`LYRA_CLI_ALLOW_DEV_JIANYING_APP=1`**：本机剪映的 Authenticode 签名不被官方
   认可（`signature_not_official`）。官方在 `auth login --require-jianying-app` 的
   错误恢复提示里明确给出了这个**开发用开关**，`lyra_cli.run()` 默认通过
   `os.environ.setdefault` 打开它，用于复用本机已有的剪映登录态。
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
