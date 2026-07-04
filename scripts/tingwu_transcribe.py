#!/usr/bin/env python3
"""
通义听悟全自动转写流水线。

链路：yt-dlp 下载视频 → ffmpeg 提取音频 → 上传 OSS → 通义听悟转写 → 获取文本

依赖：
    pip3 install alibabacloud_tingwu20230930 oss2

前置：
    yt-dlp 和 ffmpeg 需在 PATH 中
    阿里云 OSS Bucket 需开通，且允许公共读或使用签名 URL

环境变量：
    ALIBABA_CLOUD_ACCESS_KEY_ID     阿里云 AK
    ALIBABA_CLOUD_ACCESS_KEY_SECRET 阿里云 SK
    ALIBABA_CLOUD_OSS_BUCKET        OSS Bucket 名（不含 oss://）
    ALIBABA_CLOUD_OSS_ENDPOINT      OSS Endpoint，如 oss-cn-beijing.aliyuncs.com
    ALIBABA_CLOUD_OSS_REGION        OSS 区域，如 cn-beijing

用法：
    python3 tingwu_transcribe.py --url "https://v.douyin.com/xxxxx/"
    python3 tingwu_transcribe.py --file "path/to/video.mp4"
    python3 tingwu_transcribe.py --url "https://..." --keep-temp --json
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ── 工具检测 ──────────────────────────────────────────────────

def check_tool(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def check_sdk():
    try:
        import alibabacloud_tingwu20230930.client  # noqa
        import oss2  # noqa
        return True
    except ImportError:
        return False


# ── 步骤 1: yt-dlp 下载视频 ──────────────────────────────────

def download_video(url, output_dir):
    """下载视频，返回文件路径。"""
    print(f"⬇ 下载视频: {url}")
    # 优先用 cookie 文件（更稳定），没有则尝试从 Chrome 直接读
    cookie_file = os.path.join(output_dir, "cookies.txt")
    subprocess.run(
        ["yt-dlp", "--cookies-from-browser", "chrome", "--cookies", cookie_file,
         "https://www.douyin.com/", "-s"],
        capture_output=True, timeout=30, cwd=output_dir
    )
    use_cookie_file = os.path.exists(cookie_file)

    # 先列出已有文件，下载后对比找新文件
    before = set(os.listdir(output_dir))

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "-o", f"{output_dir}/video.%(ext)s",
        "--no-simulate",
    ]
    if use_cookie_file:
        cmd += ["--cookies", cookie_file]
    else:
        cmd += ["--cookies-from-browser", "chrome"]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=output_dir)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "cookies" in stderr.lower() and not use_cookie_file:
            raise RuntimeError(f"下载失败（需要登录态）: {stderr[:200]}")
        raise RuntimeError(f"下载失败: {stderr[:200]}")

    # 找到下载的文件
    after = set(os.listdir(output_dir))
    new_files = after - before
    video_files = [f for f in new_files if not f.endswith(".txt")]
    if not video_files:
        raise RuntimeError(f"未找到下载文件。目录内容: {after}")
    filepath = os.path.join(output_dir, video_files[0])
    size_mb = os.path.getsize(filepath) / 1024 / 1024
    print(f"  ✓ 已下载 ({size_mb:.1f} MB): {filepath}")
    return filepath


# ── 步骤 2: ffmpeg 提取音频 ───────────────────────────────────

def extract_audio(video_path, output_dir):
    """从视频中提取 16kHz 单声道 MP3。"""
    audio_path = os.path.join(output_dir, "audio.mp3")
    print(f"🎵 提取音频 → {audio_path}")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"音频提取失败: {result.stderr.strip()}")
    size_mb = os.path.getsize(audio_path) / 1024 / 1024
    print(f"  ✓ 音频大小: {size_mb:.1f} MB")
    return audio_path


# ── 步骤 3: 上传 OSS ──────────────────────────────────────────

def upload_to_oss(audio_path, oss_bucket, oss_endpoint, ak, sk):
    """上传音频文件到 OSS，返回 OSS URL 用于听悟 API。"""
    import oss2

    object_key = f"tingwu-input/{int(time.time())}-{os.path.basename(audio_path)}"
    print(f"☁ 上传 OSS: {object_key}")

    auth = oss2.Auth(ak, sk)
    bucket = oss2.Bucket(auth, oss_endpoint, oss_bucket)

    bucket.put_object_from_file(object_key, audio_path)

    # 生成 24 小时有效的签名 URL
    file_url = bucket.sign_url("GET", object_key, 86400)
    print(f"  ✓ OSS URL: {file_url[:80]}...")
    return file_url, object_key


# ── 步骤 4: 通义听悟转写 ──────────────────────────────────────

def tingwu_transcribe(file_url, ak, sk, language="cn"):
    """调用通义听悟离线转写 API（HTTP 直接调用，不依赖 SDK 版本）。"""
    import hmac, hashlib, urllib.request, urllib.parse
    from datetime import datetime, timezone

    endpoint = "tingwu.cn-beijing.aliyuncs.com"

    def _sign(method, path, query, body, headers):
        """阿里云 OpenAPI V3 签名。"""
        # 简化：使用 SDK 处理签名
        pass

    def _call_api(action, params=None, body_obj=None):
        """调用通义听悟 OpenAPI。"""
        from alibabacloud_tea_openapi.models import Config
        from alibabacloud_tea_openapi.client import Client as OpenApiClient
        from alibabacloud_tea_util.models import RuntimeOptions

        config = Config(
            access_key_id=ak,
            access_key_secret=sk,
            endpoint=endpoint,
        )
        client = OpenApiClient(config)
        runtime = RuntimeOptions()

        # 构建请求
        query = {}
        if params:
            query.update(params)

        result = client.call_api(
            action, query, None, body_obj, runtime
        )
        return result

    # 创建转写任务
    print("📝 创建转写任务...")
    create_body = {
        "AppKey": "",
        "Input": {
            "SourceLanguage": language,
            "FileUrl": file_url,
        },
        "Parameters": {
            "Transcription": {
                "OutputLevel": 2,
            },
        },
        "Type": "offline",
    }
    create_resp = _call_api("CreateTask", body_obj=create_body)
    data = create_resp.get("Data", {})
    task_id = data.get("TaskId", "")
    task_status = data.get("TaskStatus", "")
    print(f"  task_id: {task_id}, 状态: {task_status}")

    if task_status == "COMPLETED":
        return data.get("Result")

    # 轮询等待
    print("⏳ 等待转写完成...")
    max_retries = 120
    for i in range(max_retries):
        time.sleep(5)
        get_resp = _call_api("GetTaskInfo", params={"TaskId": task_id})
        data = get_resp.get("Data", {})
        status = data.get("TaskStatus", "")
        elapsed = (i + 1) * 5
        if status == "COMPLETED":
            print(f"  ✓ 转写完成 ({elapsed}秒)")
            return data.get("Result")
        elif status == "FAILED":
            raise RuntimeError(f"转写失败: {data.get('Message', '未知错误')}")
        if (i + 1) % 6 == 0:
            print(f"  ... {elapsed}秒, 状态: {status}")

    raise RuntimeError("转写超时（超过 10 分钟）")


# ── 解析结果 ──────────────────────────────────────────────────

def parse_transcript(result):
    """从通义听悟返回结果中提取纯文本。"""
    if result is None:
        return ""

    # result 可能是 dict 或 SDK 对象
    if hasattr(result, "to_map"):
        result = result.to_map()

    paragraphs = []
    # 通义听悟结果结构: result.transcription.paragraphs[].sentences[].text
    if isinstance(result, dict):
        transcription = result.get("transcription", {}) or result.get("Transcription", {})
        para_list = transcription.get("paragraphs", []) or transcription.get("Paragraphs", [])
        for para in para_list:
            if isinstance(para, dict):
                sentences = para.get("sentences", []) or para.get("Sentences", [])
                for s in sentences:
                    text = s.get("text", "") or s.get("Text", "")
                    if text:
                        paragraphs.append(text)

    return "\n".join(paragraphs)


# ── 清理 ──────────────────────────────────────────────────────

def cleanup_oss(object_key, oss_bucket, oss_endpoint, ak, sk):
    """删除 OSS 上的临时文件。"""
    try:
        import oss2
        auth = oss2.Auth(ak, sk)
        bucket = oss2.Bucket(auth, oss_endpoint, oss_bucket)
        bucket.delete_object(object_key)
        print(f"🧹 已清理 OSS: {object_key}")
    except Exception as e:
        print(f"⚠ 清理 OSS 失败（可忽略）: {e}")


# ── 主流程 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="通义听悟全自动转写流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s --url "https://v.douyin.com/xxxxx/"
    %(prog)s --url "https://www.youtube.com/watch?v=xxx" --language en
    %(prog)s --file "path/to/video.mp4"
    %(prog)s --audio "path/to/audio.mp3"  # 跳过下载和提取，直接传已有音频
        """,
    )
    parser.add_argument("--url", help="视频链接（支持抖音/B站/YouTube 等）")
    parser.add_argument("--file", help="本地视频文件路径")
    parser.add_argument("--audio", help="本地音频文件路径（跳过下载+提取步骤）")
    parser.add_argument("--language", default="cn", help="音频语言代码，如 cn/en/ja (默认: cn)")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时文件")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--no-cleanup", action="store_true", help="不清理 OSS 临时文件")

    args = parser.parse_args()

    if not args.url and not args.file and not args.audio:
        parser.error("至少需要 --url、--file 或 --audio 之一")

    # ── 检查依赖 ──
    if not check_sdk():
        print("✗ 缺少 Python SDK")
        print("  请安装: pip3 install alibabacloud_tingwu20230930 oss2")
        sys.exit(1)

    need_download = bool(args.url or args.file)
    if need_download and not check_tool("yt-dlp"):
        print("✗ 缺少 yt-dlp")
        print("  安装: brew install yt-dlp")
        sys.exit(1)
    if need_download and not args.audio and not check_tool("ffmpeg"):
        print("✗ 缺少 ffmpeg")
        print("  安装: brew install ffmpeg")
        sys.exit(1)

    # ── 检查凭证 ──
    ak = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    sk = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    oss_bucket = os.environ.get("ALIBABA_CLOUD_OSS_BUCKET")
    oss_endpoint = os.environ.get("ALIBABA_CLOUD_OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")

    if not ak or not sk:
        print("✗ 缺少阿里云凭证")
        print("  请设置环境变量: ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        sys.exit(1)
    if not oss_bucket:
        print("✗ 缺少 OSS Bucket 配置")
        print("  请设置环境变量: ALIBABA_CLOUD_OSS_BUCKET")
        sys.exit(1)

    temp_dir = None
    oss_object_key = None

    try:
        # ── 获取音频文件 ──
        if args.audio:
            audio_path = args.audio
            print(f"📁 使用已有音频: {audio_path}")
        else:
            temp_dir = tempfile.mkdtemp(prefix="tingwu_")

            if args.file:
                video_path = args.file
            else:
                video_path = download_video(args.url, temp_dir)

            audio_path = extract_audio(video_path, temp_dir)

        # ── 上传 OSS ──
        file_url, oss_object_key = upload_to_oss(audio_path, oss_bucket, oss_endpoint, ak, sk)

        # ── 调用通义听悟 ──
        result = tingwu_transcribe(file_url, ak, sk, args.language)

        # ── 解析输出 ──
        transcript = parse_transcript(result)
        word_count = len(transcript)

        output = {
            "status": "success",
            "transcript": transcript,
            "word_count": word_count,
            "source": args.url or args.file or args.audio,
        }

        if args.json:
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print("\n" + "=" * 60)
            print(transcript or "(空转写结果)")
            print("=" * 60)
            print(f"字数: {word_count}")

    except Exception as e:
        print(f"\n✗ 错误: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        # 清理
        if oss_object_key and not args.no_cleanup:
            cleanup_oss(oss_object_key, oss_bucket, oss_endpoint, ak, sk)
        if temp_dir and not args.keep_temp:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("🧹 已清理临时文件")


if __name__ == "__main__":
    main()
