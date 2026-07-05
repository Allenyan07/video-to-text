# video-to-text

---

# 中文

> 多平台视频转写 Skill，适用于 Codex、Hermes、OpenClaw、Claude Code 等 AI Agent

一键从抖音、B站、小红书、YouTube、TikTok、Instagram 等平台提取视频文案。

## 适合谁用

- **自媒体/内容创作者** — 拆解竞品口播脚本、分析爆款文案结构、找选题灵感
- **知识管理重度用户** — 收藏夹视频一键转文字，存入 Obsidian/Notion
- **AI Agent 用户** — 在 Codex、Hermes、Claude Code 等工作流中让 Agent 自动提取视频内容
- **产品经理/运营** — 收集反馈视频、竞品动态，沉淀为可检索文字
- **研究人员/分析师** — 批量收集多平台视频文本，做内容分析和趋势研究

## 使用效果对比

### 以前：手动用转写网站

```
复制链接 → 打开网站 → 粘贴链接 → 等待转写
                               → 复制结果
                               → 打开笔记软件
                               → 粘贴内容
                               → 手动排版
                               → 保存
```

整个过程需要切换多个工具，手动操作 6-8 步，长视频还要干等。

### 现在：AI Agent + 本 Skill

```
复制链接 → 发给 Agent → Agent 自动完成：
                        ├── 调用转写 API 获取文字
                        ├── 纠错错别字和专有名词
                        ├── 整理段落、去掉口癖水词
                        └── 写入笔记软件，结构化排版
```

一句话搞定，全程自动。

| | 手动网站 | AI Agent + video-to-text |
|---|---|---|
| 步骤 | 6-8 步 | 1 步（发链接） |
| 纠错排版 | 手动 | 自动 |
| 写入笔记 | 手动粘贴 | 自动写入 Obsidian/Notion 等 |
| 等待期间 | 干等 | 可以做别的事 |
| 多平台 | 各平台分开处理 | 统一入口，自动识别 |

---

## 完整工作流

### 快速决策树

```
用户贴入视频链接
├── 来自 B站？
│   ├── TranscriptGenerate 可用？ → 路径 A（优先，秒级）
│   │   ├── 返回 401？ → 账号密码错误或 token 过期
│   │   ├── 返回 601？ → 免费额度用完，需充值或等次月重置
│   │   └── WAITING 超时？ → 视频太长或排队，稍后重试
│   └── TranscriptGenerate 挂了/没额度？
│       └── 路径 B（本地 Whisper，免费）
│           └── B站 API 无响应？ → 网络不通，检查 api.bilibili.com
├── 来自抖音/小红书/YouTube/其他？
│   └── 路径 A（TranscriptGenerate，唯一方案）
│       ├── 401？ → 账号密码错误
│       ├── 601？ → 免费额度用完
│       └── WAITING 超时？ → 视频太长，稍后重试
└── 以上全挂？ → 告知用户具体错误码和原因
```

### 路径 A：TranscriptGenerate.com（优先，全平台）

> **适用场景**：个人少量使用，一次转一个视频。高并发或批量处理建议直接对接 [TranscriptGenerate 官方 API](https://www.transcriptgenerate.com)。

```
粘贴链接 → 检查环境变量 TG_EMAIL / TG_PASSWORD
         → 第 1 步：AES 加密登录 /prod-api/login 获取 token
         → 第 2 步：AES 加密创建转写任务 /prod-api/transcript/createTask
         → 第 3 步：轮询 /prod-api/transcript/queryTask 查询任务状态
         → 第 4 步：获取转写结果（title + textContent + platform）
         → 第 5 步：后处理（Agent 自动完成）
```

#### 第 1 步：登录获取 Token

加密方式：AES-128-CBC，key `aaDJL2d9DfhLZO0z`，iv `412ADDSSFA342442`，ZeroPadding。

加密前请求体：

```json
{"type": 2, "username": "邮箱", "password": "密码", "appType": "transcript", "appClient": "web"}
```

返回 token，后续请求带 `Authorization: Bearer <token>`。

#### 第 2 步：创建转写任务

加密前请求体：

```json
{"appType": "transcript", "workUrl": "<视频链接>", "type": "text", "targetLanguage": "auto"}
```

返回 `taskId`，用于后续轮询。

#### 第 3 步：轮询任务状态

加密前请求体：

```json
{"appType": "transcript", "taskId": "<taskId>"}
```

- `status: "WAITING"` → 排队中，2 秒后重试
- `status: "SUCCESS"` → 转写完成，进入第 4 步

通常 10-30 秒完成，长视频可能更久。

#### 第 4 步：获取转写结果

返回完整 JSON：

```json
{
  "code": 200,
  "taskId": "2073394982471213056",
  "status": "SUCCESS",
  "title": "视频标题",
  "content": "带话题标签的摘要文本",
  "textContent": "完整口播转写文本...",
  "platform": "xhs",
  "workUrl": "原始链接"
}
```

关键字段：
- `textContent` — 纯文本转写稿，可直接使用
- `title` — 视频标题
- `platform` — `xhs`(小红书) / `douyin`(抖音) / `bilibili`(B站) / `youtube` / `tiktok` / `instagram`

#### 第 5 步：后处理（Agent 自动完成）

拿到 `textContent` 后，Agent 会自动：

**纠错**：
- 修正明显错别字和同音词
- 修正常见专有名词转写偏差（品牌名、人名、工具名）
- 修正中英文混排时的识别错误

**整理段落**：
- 按语义将连续文本拆分为自然段落（通常 3-5 句一段）
- 去掉无意义的口癖和重复（如"就是就是"、"然后然后"）
- 去掉纯水词（如"嗯""那个""怎么说呢"），保留内容表达

**结构化输出**：
- 开头标注：标题、平台、原始链接
- 正文按段落输出，每段之间空一行
- 保留原文中的关键标签/话题（如 `#知识管理`）

### 路径 B：B站直连 + Whisper（仅 B站备用）

```
B站链接（支持 b23.tv / BV号 / 完整URL）
├── 第 1 步：展开 b23.tv → 提取 BV 号
├── 第 2 步：B站 API 获取元数据（title, duration, cid）
├── 第 3 步：B站 API 检查 AI 字幕
│   ├── 有字幕 → 直接抓 JSON（秒级，准确率最高）
│   └── 无字幕 → 继续
├── 第 4 步：B站 API 获取 DASH 音频流 URL
├── 第 5 步：curl 下载 m4s → ffmpeg 转 WAV（16kHz mono）
├── 第 6 步：openai-whisper 本地转写
└── 第 7 步：输出带时间戳文本 [MM:SS]
```

---

## 双路径对比

| | 路径 A: TranscriptGenerate | 路径 B: B站直连 |
|---|---|---|
| 覆盖平台 | 全平台 | 仅 B站 |
| 速度 | 10-30秒 | 秒级(字幕) / 分钟级(Whisper) |
| 费用 | 见下方费用说明 | 完全免费 |
| 依赖 | Node 18+ | Python + ffmpeg + whisper |
| 隐私 | 上传第三方 | 全本地 |

---

## 💰 费用说明

路径 A（TranscriptGenerate）免费额度 10 分钟/月，超出约 ¥29/月，以[官网](https://www.transcriptgenerate.com)为准。路径 B（B站本地转写）完全免费。

> ⚠️ 免责声明：本 Skill 非 TranscriptGenerate 官方产品，我们只是该网站的用户，觉得顺手所以做了这个自动化工具。付费、价格、服务变动等请以官方网站为准。
>
> **技术实现说明**：本工具通过逆向 TranscriptGenerate 网站前端调用的内部 API 接口（登录、创建任务、查询结果）实现自动化，并非其官方公开 API。如果网站修改了接口地址、加密方式或调用规则，本工具可能失效，届时需要更新脚本中的加密密钥（`KEY` / `IV`）或接口路径。所有请求均以用户账号登录身份发起，计费逻辑与网页手动操作一致。

---

## B站 API 参考

| 端点 | 返回关键字段 |
|------|-------------|
| `api.bilibili.com/x/web-interface/view?bvid={BV}` | `data.title`, `data.duration`, `data.cid`, `data.owner.name` |
| `api.bilibili.com/x/player/v2?bvid={BV}&cid={CID}` | `data.subtitle.subtitles[].subtitle_url` |
| `api.bilibili.com/x/player/playurl?bvid={BV}&cid={CID}&qn=80&fnval=16&fnver=0&fourk=1` | `data.dash.audio[].baseUrl` |

所有 API 必须带请求头：

```
Referer: https://www.bilibili.com
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

---

## ⚠️ 已知陷阱

- **yt-dlp 在 B站不可用**：B站返回 HTTP 412。路径 B 只用 B站官方 API。
- **B站 AI 字幕不是立即可用**：长视频上传后可能需 1-2 天才能生成。
- **Whisper 模型首次下载**：约 139MB（base），建议设 `HF_ENDPOINT=https://hf-mirror.com` 加速。
- **TranscriptGenerate 使用内部 API（非官方）**：本工具逆向的是网站前端调用的 `/prod-api` 接口（登录 → createTask → queryTask），非官方公开 API。网站改版可能导致接口失效。
- **加密密钥可能变化**：请求体使用 AES-128-CBC 加密，密钥 `KEY` / `IV` 硬编码在 `transcriptgenerate_transcribe.mjs` 中。网站前端更新后需同步更新。
- **账号登录方式**：使用邮箱密码登录获取 token，所有后续请求携带 Bearer token。凭证安全由用户自行管理（建议通过环境变量传入，不要写死在代码中）。
- **后备方案**：如果内部 API 完全失效，可改用 Playwright 模拟浏览器登录 + 页面操作方式获取转写内容（未实现，作为 v2 后备方案）。

---

## 安装

### Codex

```bash
cp -r video-to-text ~/.codex/skills/
```

使用 `$video-to-text` 或在对话中贴链接。

### Hermes

```bash
cp -r video-to-text ~/.hermes/profiles/<your-profile>/skills/
```

### OpenClaw / Claude Code

复制到项目目录，在 `CLAUDE.md` 中添加引用。各 Agent 目录下已有调用示例。

### 通用（任何能跑 shell 的 Agent）

```bash
git clone https://github.com/<your-username>/video-to-text.git
cd video-to-text
```

---

## 使用

### 路径 A：TranscriptGenerate（推荐）

先注册 [TranscriptGenerate](https://www.transcriptgenerate.com) 账号：

```bash
export TG_EMAIL="your@email.com"
export TG_PASSWORD="yourpassword"

node scripts/transcriptgenerate_transcribe.mjs \
  --url 'https://www.xiaohongshu.com/explore/xxxxx'
```

Python 封装：

```bash
python3 scripts/transcribe.py --url 'VIDEO_URL' --email "$TG_EMAIL" --password "$TG_PASSWORD" --json
```

### 路径 B：B站本地转写（B站专用备用）

```bash
pip install openai-whisper
python3 scripts/bilibili_transcribe.py 'BV1xx411c7mD' -o transcript.txt
```

无需任何第三方服务、无需登录、无需 cookie。

---

## 支持平台

抖音、B站、小红书、YouTube、TikTok、Instagram、X/Twitter

---

## 文件结构

```
video-to-text/
├── README.md
├── SKILL.md                          # Agent 用技能说明书
├── agents/
│   ├── codex/openai.yaml             # Codex UI 配置
│   ├── hermes/SOUL.md                # Hermes 调用说明
│   └── claude-code/CLAUDE.md         # Claude Code 调用说明
└── scripts/
    ├── transcriptgenerate_transcribe.mjs  # 路径 A：TranscriptGenerate 主脚本
    ├── transcribe.py                      # 路径 A：Python 封装
    ├── bilibili_transcribe.py             # 路径 B：B站本地转写
    └── tingwu_transcribe.py               # 已废弃（通义听悟）
```

---

# English

> Multi-platform video transcription skill for Codex, Hermes, OpenClaw, Claude Code, and other AI agents

One-click extract text from Douyin, Bilibili, Xiaohongshu, YouTube, TikTok, Instagram, and more.

## Who is this for

- **Content creators** — Analyze competitor scripts, study viral copy structures, find topic ideas
- **Knowledge workers** — Turn saved videos into searchable text, sync to Obsidian/Notion
- **AI Agent users** — Let your agent extract video content automatically in Codex, Hermes, Claude Code workflows
- **PMs & operators** — Collect feedback videos and competitor updates as searchable text
- **Researchers & analysts** — Batch collect multi-platform video text for content analysis

## Before vs After

### Before: Manual transcription websites

```
Copy link → Open website → Paste link → Wait for transcription
                                     → Copy result
                                     → Open notes app
                                     → Paste content
                                     → Manually format
                                     → Save
```

6-8 steps across multiple tools, stuck waiting for long videos.

### After: AI Agent + this skill

```
Copy link → Send to Agent → Agent auto-completes:
                              ├── Call transcription API
                              ├── Fix typos & proper nouns
                              ├── Format paragraphs, remove filler words
                              └── Save to your notes app
```

One sentence, fully automatic.

| | Manual website | AI Agent + video-to-text |
|---|---|---|
| Steps | 6-8 | 1 (send link) |
| Fix & format | Manual | Automatic |
| Save to notes | Manual copy-paste | Auto-save to Obsidian/Notion etc. |
| Wait time | Stuck waiting | Do other things |
| Multi-platform | Separate per platform | Unified entry, auto-detect |

---

## Complete Workflow

### Quick Decision Tree

```
User pastes video link
├── From Bilibili?
│   ├── TranscriptGenerate available? → Path A (primary, seconds)
│   │   ├── Returns 401? → Wrong credentials or token expired
│   │   ├── Returns 601? → Free quota exhausted, recharge or wait
│   │   └── WAITING timeout? → Video too long or queue busy, retry later
│   └── TranscriptGenerate down / no quota?
│       └── Path B (local Whisper, free)
│           └── Bilibili API no response? → Network issue, check api.bilibili.com
├── From Douyin/Xiaohongshu/YouTube/etc?
│   └── Path A (TranscriptGenerate, only option)
│       ├── 401? → Wrong credentials
│       ├── 601? → Quota exhausted
│       └── WAITING timeout? → Too long, retry
└── Everything fails? → Tell user the specific error code and reason
```

### Path A: TranscriptGenerate.com (Primary, all platforms)

> **Use case**: Personal, low-volume use (one video at a time). For high concurrency or batch processing, use [TranscriptGenerate's official API](https://www.transcriptgenerate.com) directly.

```
Paste link → Check env vars TG_EMAIL / TG_PASSWORD
          → Step 1: AES encrypt → /prod-api/login → get token
          → Step 2: AES encrypt → /prod-api/transcript/createTask → get taskId
          → Step 3: Poll /prod-api/transcript/queryTask
          → Step 4: Return title + textContent + platform
          → Step 5: Post-process (Agent auto)
```

#### Step 1: Login to get Token

Encryption: AES-128-CBC, key `aaDJL2d9DfhLZO0z`, iv `412ADDSSFA342442`, ZeroPadding.

Payload before encryption:

```json
{"type": 2, "username": "email", "password": "password", "appType": "transcript", "appClient": "web"}
```

Returns a token. Subsequent requests carry `Authorization: Bearer <token>`.

#### Step 2: Create transcription task

Payload before encryption:

```json
{"appType": "transcript", "workUrl": "<video link>", "type": "text", "targetLanguage": "auto"}
```

Returns `taskId` for subsequent polling.

#### Step 3: Poll task status

Payload before encryption:

```json
{"appType": "transcript", "taskId": "<taskId>"}
```

- `status: "WAITING"` → queued, retry in 2s
- `status: "SUCCESS"` → done, proceed to step 4

Typically 10-30 seconds. Longer for long videos.

#### Step 4: Get transcription result

Complete JSON returned on success:

```json
{
  "code": 200,
  "taskId": "2073394982471213056",
  "status": "SUCCESS",
  "title": "Video title",
  "content": "Summary with hashtags",
  "textContent": "Full transcript text...",
  "platform": "xhs",
  "workUrl": "Original link"
}
```

Key fields:
- `textContent` — Plain text transcript, ready to use
- `title` — Video title
- `platform` — `xhs`(Xiaohongshu) / `douyin`(Douyin) / `bilibili`(Bilibili) / `youtube` / `tiktok` / `instagram`

#### Step 5: Post-process (Agent auto-completes)

After receiving `textContent`, the Agent automatically:

**Fix errors**:
- Fix obvious typos and homophone errors
- Fix common proper noun transcription errors (brands, names, tool names)
- Fix mixed Chinese-English recognition errors

**Format paragraphs**:
- Split continuous text into natural paragraphs (3-5 sentences each)
- Remove meaningless filler and repetition
- Remove pure filler words, keep content

**Structured output**:
- Header with title, platform, original link
- Body in paragraphs, blank line between each
- Preserve key hashtags/topics from original

### Path B: Bilibili Direct + Whisper (Bilibili-only fallback)

```
Bilibili link (b23.tv / BV号 / full URL)
├── Step 1: Expand b23.tv → extract BV号
├── Step 2: Fetch metadata via Bilibili API (title, duration, cid)
├── Step 3: Check AI subtitles via Bilibili API
│   ├── Has subtitles → Fetch JSON directly (instant, highest accuracy)
│   └── No subtitles → Continue
├── Step 4: Get DASH audio stream URL via Bilibili API
├── Step 5: curl download m4s → ffmpeg → WAV (16kHz mono)
├── Step 6: openai-whisper local transcription
└── Step 7: Output timestamped text [MM:SS]
```

---

## Path Comparison

| | Path A: TranscriptGenerate | Path B: Bilibili Direct |
|---|---|---|
| Platforms | All platforms | Bilibili only |
| Speed | 10-30s | Instant (subtitles) / minutes (Whisper) |
| Cost | See pricing below | Completely free |
| Dependencies | Node 18+ | Python + ffmpeg + whisper |
| Privacy | Uploaded to third-party | Fully local |

---

## 💰 Pricing

Path A (TranscriptGenerate): free 10 minutes/month, paid plans start at ~¥29/month beyond that. See [official site](https://www.transcriptgenerate.com) for current pricing. Path B (Bilibili local) is completely free.

> ⚠️ Disclaimer: This skill is not an official TranscriptGenerate product. We're just users who liked the service and built an automation tool. Pricing and policy changes are subject to the official site.

---

## Bilibili API Reference

| Endpoint | Key Fields |
|----------|------------|
| `api.bilibili.com/x/web-interface/view?bvid={BV}` | `data.title`, `data.duration`, `data.cid`, `data.owner.name` |
| `api.bilibili.com/x/player/v2?bvid={BV}&cid={CID}` | `data.subtitle.subtitles[].subtitle_url` |
| `api.bilibili.com/x/player/playurl?bvid={BV}&cid={CID}&qn=80&fnval=16&fnver=0&fourk=1` | `data.dash.audio[].baseUrl` |

All API calls require headers:

```
Referer: https://www.bilibili.com
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

---

## ⚠️ Known Issues

- **yt-dlp doesn't work on Bilibili**: Bilibili returns HTTP 412. Path B uses only Bilibili's official API.
- **Bilibili AI subtitles not immediately available**: Long videos may take 1-2 days for Bilibili to generate AI subtitles.
- **First Whisper model download**: ~139MB (base model). Set `HF_ENDPOINT=https://hf-mirror.com` for faster download in China.
- **TranscriptGenerate encryption keys may change**: If the site frontend updates, sync `KEY` / `IV` in `transcriptgenerate_transcribe.mjs`.

---

## Installation

### Codex

```bash
cp -r video-to-text ~/.codex/skills/
```

Use `$video-to-text` or paste a link in conversation.

### Hermes

```bash
cp -r video-to-text ~/.hermes/profiles/<your-profile>/skills/
```

### OpenClaw / Claude Code

Copy to project directory, add reference in `CLAUDE.md`. See `agents/` for invocation examples.

### General (any shell-capable Agent)

```bash
git clone https://github.com/<your-username>/video-to-text.git
cd video-to-text
```

---

## Usage

### Path A: TranscriptGenerate (Recommended)

Register at [TranscriptGenerate](https://www.transcriptgenerate.com) first:

```bash
export TG_EMAIL="your@email.com"
export TG_PASSWORD="yourpassword"

node scripts/transcriptgenerate_transcribe.mjs \
  --url 'https://www.xiaohongshu.com/explore/xxxxx'
```

Python wrapper:

```bash
python3 scripts/transcribe.py --url 'VIDEO_URL' --email "$TG_EMAIL" --password "$TG_PASSWORD" --json
```

### Path B: Bilibili Local (Bilibili-only fallback)

```bash
pip install openai-whisper
python3 scripts/bilibili_transcribe.py 'BV1xx411c7mD' -o transcript.txt
```

No third-party service, no login, no cookie needed.

---

## Supported Platforms

Douyin, Bilibili, Xiaohongshu, YouTube, TikTok, Instagram, X/Twitter

---

## File Structure

```
video-to-text/
├── README.md
├── SKILL.md                          # Agent skill spec
├── agents/
│   ├── codex/openai.yaml             # Codex UI config
│   ├── hermes/SOUL.md                # Hermes invocation guide
│   └── claude-code/CLAUDE.md         # Claude Code invocation guide
└── scripts/
    ├── transcriptgenerate_transcribe.mjs  # Path A: TranscriptGenerate main script
    ├── transcribe.py                      # Path A: Python wrapper
    ├── bilibili_transcribe.py             # Path B: Bilibili local transcription
    └── tingwu_transcribe.py               # Deprecated
```

---

## License

MIT
