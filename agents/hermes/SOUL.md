## video-to-text

当需要从视频链接提取转写文案时调用此 skill。

### 调用方式

```python
import subprocess, json, os

result = subprocess.run([
    "python3", "scripts/transcribe.py",
    "--url", video_url,
    "--email", os.environ["TG_EMAIL"],
    "--password", os.environ["TG_PASSWORD"],
    "--json",
], capture_output=True, text=True, cwd="path/to/skill")
data = json.loads(result.stdout)
transcript = data["textContent"]
```

B站备用（TranscriptGenerate 不可用时）：

```bash
python3 scripts/bilibili_transcribe.py 'BV号' -o transcript.txt
```

### 凭据

环境变量 `TG_EMAIL` / `TG_PASSWORD`，不要记录在对话或日志中。

### 前置条件

- Node.js 18+（脚本内部依赖）
- TranscriptGenerate 注册账号

### 支持平台

抖音、B站、小红书、YouTube、TikTok、Instagram、X/Twitter

### 费用

TranscriptGenerate 免费额度 10 分钟/月，超出约 ¥29/月，以官网为准。B站本地转写完全免费。

> 本 Skill 非 TranscriptGenerate 官方产品，只是用户做的自动化工具。

### 限制

- 长视频可能轮询 30 分钟
- 网站更新后加密密钥可能变化
