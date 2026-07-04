## video-to-text

Use this skill to transcribe videos from Douyin, Bilibili, TikTok, YouTube, Instagram, Xiaohongshu, and X/Twitter when direct subtitle extraction is unavailable.

### Invocation

Primary (TranscriptGenerate):

```bash
node scripts/transcriptgenerate_transcribe.mjs --url '<VIDEO_URL>' --email "$TG_EMAIL" --password "$TG_PASSWORD"
```

With JSON output:

```bash
node scripts/transcriptgenerate_transcribe.mjs --url '<VIDEO_URL>' --json
```

Bilibili fallback (when TranscriptGenerate is unavailable):

```bash
python3 scripts/bilibili_transcribe.py '<BVID>' -o transcript.txt
```

### Requirements

- Node.js 18+ (uses built-in `fetch`, no npm install)
- TranscriptGenerate account credentials in `TG_EMAIL` / `TG_PASSWORD` env vars
- Never log or store credentials

### Platforms Supported

Douyin, Bilibili, YouTube, TikTok, Instagram, Xiaohongshu/RedNote, X/Twitter

### Pricing

TranscriptGenerate: free 10 min/month, ~¥29/month beyond that (check official site). Bilibili local path: completely free.

> Disclaimer: This skill is not an official TranscriptGenerate product. We're just users who built an automation tool.

### Notes

- Long videos may poll for up to 30 minutes
- Encryption keys are extracted from the site frontend; may need updating if the site changes
