#!/usr/bin/env python3
"""
B站视频转写：AI 字幕抓取 → 音频下载 + Whisper 转写
用法: python3 bilibili_transcribe.py BV1xx411c7mD [--output out.txt]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HEADERS = [
    "Referer: https://www.bilibili.com",
    "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def curl_json(url, timeout=15):
    """用 curl 请求并返回解析后的 JSON"""
    cmd = ["curl", "-s", "--connect-timeout", str(timeout)]
    for h in HEADERS:
        cmd += ["-H", h]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"请求失败: {url}")
    data = json.loads(result.stdout)
    if data.get("code") != 0:
        raise RuntimeError(f"API 错误 code={data.get('code')}: {data.get('message', '')}")
    return data["data"]


def expand_b23(short_url):
    """展开 b23.tv 短链接 → 真实 URL"""
    result = subprocess.run(
        ["curl", "-sI", "-L", "-o", "/dev/null", "-w", "%{url_effective}",
         "--connect-timeout", "10", short_url],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip()


def extract_bvid(url_or_bvid):
    """从各种格式提取 BV 号"""
    # 直接是 BV 号
    if re.match(r"^BV[a-zA-Z0-9]+$", url_or_bvid):
        return url_or_bvid

    # b23.tv 短链接 → 展开
    if "b23.tv" in url_or_bvid:
        url_or_bvid = expand_b23(url_or_bvid)
        if not url_or_bvid:
            raise RuntimeError("b23.tv 短链接展开失败")

    # 从 URL 提取 BV 号
    m = re.search(r"(BV[a-zA-Z0-9]+)", url_or_bvid)
    if m:
        return m.group(1)

    raise RuntimeError(f"无法解析 B站视频链接: {url_or_bvid}")


def fetch_subtitle(bvid, cid):
    """检查并获取 AI 字幕。返回字幕文本列表 [(from, to, text)] 或 None"""
    try:
        data = curl_json(f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}")
        subs = data.get("subtitle", {}).get("subtitles", [])
        if not subs:
            return None

        # 优先选中文
        sub_url = None
        for s in subs:
            if "zh" in s.get("lan", "").lower() or "中文" in s.get("lan_doc", ""):
                sub_url = s["subtitle_url"]
                break
        if not sub_url:
            sub_url = subs[0]["subtitle_url"]

        print(f"  ✓ 发现 AI 字幕: {s.get('lan_doc', '')}", file=sys.stderr)

        result = subprocess.run(
            ["curl", "-sL", "--connect-timeout", "10", sub_url],
            capture_output=True, text=True, timeout=15,
        )
        items = json.loads(result.stdout) if isinstance(result.stdout, str) else json.loads(result.stdout.decode())
        return [(it["from"], it["to"], it["content"]) for it in items]
    except Exception as e:
        print(f"  字幕获取失败: {e}", file=sys.stderr)
        return None


def download_audio(bvid, cid, tmpdir):
    """下载音频流并转为 WAV。返回 wav 路径"""
    # 获取 DASH 音频 URL
    data = curl_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnval=16&fnver=0&fourk=1"
    )
    audio_list = data["dash"]["audio"]
    # 选最小码率
    audio = sorted(audio_list, key=lambda a: a.get("bandwidth", 0))[0]
    audio_url = audio["baseUrl"]
    print(f"  音频码率: {audio.get('bandwidth', 0)//1000}kbps", file=sys.stderr)

    m4s_path = os.path.join(tmpdir, "audio.m4s")
    wav_path = os.path.join(tmpdir, "audio.wav")

    # 下载
    print("  下载音频...", file=sys.stderr)
    cmd = ["curl", "-sL", "-o", m4s_path, "--connect-timeout", "30"]
    for h in HEADERS:
        cmd += ["-H", h]
    cmd.append(audio_url)
    subprocess.run(cmd, check=True, timeout=120)
    size_mb = os.path.getsize(m4s_path) / 1024 / 1024
    print(f"  ✓ 下载完成 ({size_mb:.1f} MB)", file=sys.stderr)

    # 转 WAV
    print("  转换 WAV (16kHz mono)...", file=sys.stderr)
    subprocess.run(
        ["ffmpeg", "-i", m4s_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
         wav_path, "-y", "-loglevel", "error"],
        check=True, timeout=60,
    )
    return wav_path


def transcribe_whisper(wav_path, model_name, language):
    """用 openai-whisper 转写。返回 [(start, end, text)] 列表"""
    import whisper

    print(f"  加载 Whisper 模型 '{model_name}'...", file=sys.stderr)
    t0 = time.time()
    model = whisper.load_model(model_name)
    print(f"  模型加载耗时 {time.time()-t0:.0f}秒", file=sys.stderr)

    print("  转写中...", file=sys.stderr)
    t0 = time.time()
    result = model.transcribe(wav_path, language=language)
    elapsed = time.time() - t0
    segments = result["segments"]
    print(f"  ✓ 转写完成 ({elapsed:.0f}秒, {len(segments)}段)", file=sys.stderr)
    return [(s["start"], s["end"], s["text"].strip()) for s in segments]


def format_transcript(segments, file=sys.stdout):
    """格式化输出带时间戳的转写稿"""
    for start, end, text in segments:
        ts = f"[{int(start//60):02d}:{int(start%60):02d}]"
        print(f"{ts} {text}", file=file)


def main():
    parser = argparse.ArgumentParser(description="B站视频转写")
    parser.add_argument("url", help="B站视频链接 (完整URL / b23.tv / BV号)")
    parser.add_argument("--output", "-o", help="输出文件路径 (默认 stdout)")
    parser.add_argument("--model", "-m", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型 (默认 base)")
    parser.add_argument("--language", "-l", default="zh", help="音频语言 (默认 zh)")
    parser.add_argument("--force-whisper", action="store_true",
                        help="跳过字幕检查，强制使用 Whisper")
    args = parser.parse_args()

    # 第 1 步：解析 BV 号
    bvid = extract_bvid(args.url)
    print(f"📺 BV: {bvid}", file=sys.stderr)

    # 获取视频元数据
    print("🔍 获取视频信息...", file=sys.stderr)
    info = curl_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    title = info["title"]
    duration = info["duration"]
    cid = info["cid"]
    owner = info["owner"]["name"]
    print(f"  标题: {title}", file=sys.stderr)
    print(f"  UP主: {owner} | 时长: {duration//60}分{duration%60}秒", file=sys.stderr)

    # 第 2 步：尝试 AI 字幕（除非强制 Whisper）
    segments = None
    if not args.force_whisper:
        print("📝 检查 AI 字幕...", file=sys.stderr)
        segments = fetch_subtitle(bvid, cid)

    # 第 3-4 步：无字幕 → 下载音频 + Whisper
    if segments is None:
        if duration > 3600:
            print(f"⚠ 视频时长 {duration//60} 分钟，Whisper 转写可能很慢", file=sys.stderr)
            print("  建议等 B站生成 AI 字幕后再试，或使用 --force-whisper 强制执行", file=sys.stderr)
            if not args.force_whisper:
                sys.exit(1)

        print("🎵 下载音频 + Whisper 转写...", file=sys.stderr)
        tmpdir = tempfile.mkdtemp(prefix="bili_transcribe_")
        try:
            wav_path = download_audio(bvid, cid, tmpdir)
            segments = transcribe_whisper(wav_path, args.model, args.language)
        finally:
            # 清理临时文件
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # 第 5 步：输出
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"标题: {title}", file=sys.stderr)
    print(f"链接: https://www.bilibili.com/video/{bvid}/", file=sys.stderr)
    print(f"段数: {len(segments)}", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            print(f"# {title}", file=f)
            print(f"# https://www.bilibili.com/video/{bvid}/", file=f)
            print(f"# UP主: {owner} | 时长: {duration//60}分{duration%60}秒", file=f)
            print(file=f)
            format_transcript(segments, file=f)
        print(f"✓ 已写入: {args.output}", file=sys.stderr)
    else:
        # stdout 输出纯转写文本
        format_transcript(segments)
        print(f"✓ 完成", file=sys.stderr)


if __name__ == "__main__":
    main()
