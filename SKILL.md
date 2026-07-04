---
name: video-to-text
description: Transcribe videos from Xiaohongshu/RedNote, Douyin, Bilibili, TikTok, YouTube, Instagram, X/Twitter, and similar platforms. Primary path uses TranscriptGenerate.com encrypted API. For Bilibili, falls back to local API + Whisper when TranscriptGenerate is unavailable.
---

# Video to Text

## Preferred Order

1. **TranscriptGenerate.com** — Multi-platform, fastest, zero deps beyond Node 18+ (free 10 min/month)
2. **Bilibili direct + Whisper (Bilibili fallback only)** — Free, local, no third-party service

---

## Path A: TranscriptGenerate.com (Primary)

> **Use case**: Personal, low-volume use (one video at a time). For high concurrency or batch processing, use [TranscriptGenerate's official API](https://www.transcriptgenerate.com) directly — this skill's encryption method can serve as reference.

Use for ALL platforms. Zero external dependencies beyond Node 18+.

**Pricing**: Free 10 minutes/month, paid plans start at ~¥29/month beyond that. See [official site](https://www.transcriptgenerate.com) for current pricing.

> ⚠️ Disclaimer: This skill is not an official TranscriptGenerate product. We're just users who built an automation tool because we liked the service. Pricing and policy changes are subject to the official site.

### Credentials

Do not store passwords in this skill or in notes.

Prefer environment variables:

```bash
TG_EMAIL='user@example.com'
TG_PASSWORD='...'
```

### Script Usage

```bash
node scripts/transcriptgenerate_transcribe.mjs --url 'VIDEO_URL' --email "$TG_EMAIL" --password "$TG_PASSWORD"
```

Optional:

```bash
node scripts/transcriptgenerate_transcribe.mjs --url 'VIDEO_URL' --target-language auto --json
```

Python wrapper:

```bash
python3 scripts/transcribe.py --url 'VIDEO_URL' --email "$TG_EMAIL" --password "$TG_PASSWORD" --json
```

### Dependencies

- **Node.js 18+** (built-in `fetch`, no npm install)
- **Python wrapper**: Python 3.8+, no pip deps (calls Node via `subprocess`)

### Workflow

```
Step 1: AES encrypt → /prod-api/login → get token
Step 2: AES encrypt → /prod-api/transcript/createTask → get taskId
Step 3: Poll /prod-api/transcript/queryTask → WAITING? retry in 2s : SUCCESS? go to step 4
Step 4: Return title + textContent + platform
Step 5: Post-process (Agent auto)
        ├── Fix typos and proper nouns
        ├── Split into paragraphs, remove filler words
        └── Structured output with title + link + formatted text
```

### API Facts

Base URL: `https://www.transcriptgenerate.com/prod-api`

Encryption: AES-128-CBC, key `aaDJL2d9DfhLZO0z`, iv `412ADDSSFA342442`, ZeroPadding

### Failure Modes

- `401`: token expired or wrong credentials
- `601`: quota/VIP limit (free quota exhausted)
- `WAITING`: poll every 2s, up to 30min
- API encryption changes: re-check frontend JS bundle

### Updating Encryption Keys

If TranscriptGenerate updates their frontend:

1. Open https://www.transcriptgenerate.com → DevTools → Sources
2. Search `encrypt` or `aes` in JS bundle
3. Update `KEY` / `IV` in `transcriptgenerate_transcribe.mjs`

---

## Path B: Bilibili Direct + Whisper (Bilibili-only Fallback)

When TranscriptGenerate is unavailable (quota exhausted or service down) AND the video is from Bilibili, use this local fallback. No third-party service, no login, no cookie needed.

```bash
python3 scripts/bilibili_transcribe.py 'BV1xx411c7mD' -o transcript.txt
```

### Workflow

```
Bilibili link → Check AI subtitles → Has subtitles? → Fetch JSON directly (instant, highest accuracy)
                                   → No subtitles? → Download audio → ffmpeg → WAV → Whisper
```

### Dependencies

- Python 3.8+, ffmpeg
- openai-whisper: `pip install openai-whisper` (first run downloads ~139MB base model)

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--output / -o` | Output file path | stdout |
| `--model / -m` | Whisper model: tiny/base/small/medium | `base` |
| `--language / -l` | Audio language | `zh` |
| `--force-whisper` | Skip subtitle check, force Whisper | false |

### Features

- Fully local, zero third-party dependencies
- No yt-dlp needed (Bilibili returns HTTP 412 for yt-dlp)
- Supports b23.tv short links
- Videos >1h: consider waiting for Bilibili AI subtitles

### Bilibili API Reference

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

## Path Comparison

| | Path A: TranscriptGenerate | Path B: Bilibili Direct |
|---|---|---|
| Platforms | All platforms | Bilibili only |
| Speed | 10-30s | Instant (subtitles) / minutes (Whisper) |
| Cost | Free 10 min/month, ~¥29/mo beyond | Completely free |
| Dependencies | Node 18+ | ffmpeg + whisper |
| Privacy | Uploaded to third-party | Fully local |

---

## Using with Different Agents

### Codex

Invoke `$video-to-text`. Agent auto-selects path based on URL and availability.

### Hermes / OpenClaw

```python
import subprocess, os
result = subprocess.run([
    "python3", "scripts/transcribe.py",
    "--url", video_url,
    "--email", os.environ["TG_EMAIL"],
    "--password", os.environ["TG_PASSWORD"],
    "--json",
], capture_output=True, text=True, cwd="path/to/skill")
transcript = json.loads(result.stdout)
```

Bilibili fallback:
```bash
python3 scripts/bilibili_transcribe.py '<BVID>' -o transcript.txt
```

### Claude Code / Any Shell Agent

```
Primary: node scripts/transcriptgenerate_transcribe.mjs --url '<URL>' --email $TG_EMAIL --password $TG_PASSWORD
Bilibili fallback: python3 scripts/bilibili_transcribe.py '<URL>' -o transcript.txt
```

---

## Handling Results

Save: platform, original URL, title, author, duration, transcript text, method used.

For Obsidian vault: raw transcript first → wiki page if useful → update `index.md` / `log.md`.
