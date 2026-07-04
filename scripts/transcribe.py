#!/usr/bin/env python3
"""
Python wrapper for transcriptgenerate_transcribe.mjs.

Usage:
    python3 transcribe.py --url 'VIDEO_URL' --email "$TG_EMAIL" --password "$TG_PASSWORD"
    python3 transcribe.py --url 'VIDEO_URL' --target-language auto --json

Environment variables TG_EMAIL and TG_PASSWORD are also supported.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def find_node_script() -> Path:
    """Locate the .mjs script relative to this Python file."""
    script_dir = Path(__file__).resolve().parent
    mjs_path = script_dir / "transcriptgenerate_transcribe.mjs"
    if not mjs_path.exists():
        raise FileNotFoundError(
            f"Node.js script not found: {mjs_path}\n"
            "Make sure transcriptgenerate_transcribe.mjs is in the same directory as transcribe.py"
        )
    return mjs_path


def find_node() -> str:
    """Find a usable Node.js binary."""
    # Prefer fnm/node if available (common in Codex)
    for candidate in ["node", os.path.expanduser("~/.local/share/fnm/node")]:
        try:
            subprocess.run(
                [candidate, "--version"],
                capture_output=True, timeout=5
            )
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    raise FileNotFoundError(
        "Node.js is not available.\n"
        "Install Node.js >= 18 or ensure 'node' is on your PATH.\n"
        "This skill requires Node.js for the transcript extraction logic."
    )


def build_args(url, email, password, target_language, json_output):
    """Build argument list for the Node.js script."""
    node_script = str(find_node_script())
    args = [
        find_node(),
        node_script,
        "--url", url,
        "--email", email,
        "--password", password,
    ]
    if target_language:
        args.extend(["--target-language", target_language])
    if json_output:
        args.append("--json")
    return args


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe videos via TranscriptGenerate.com (Python wrapper)"
    )
    parser.add_argument("--url", required=True, help="Video URL to transcribe")
    parser.add_argument("--email", default=os.environ.get("TG_EMAIL"),
                        help="TranscriptGenerate account email (or TG_EMAIL env var)")
    parser.add_argument("--password", default=os.environ.get("TG_PASSWORD"),
                        help="TranscriptGenerate account password (or TG_PASSWORD env var)")
    parser.add_argument("--target-language", default="auto",
                        help="Target language code, e.g. zh, en, ja (default: auto)")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")

    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error(
            "Missing --email/--password.\n"
            "Set them via command line or TG_EMAIL/TG_PASSWORD environment variables."
        )

    cmd = build_args(args.url, args.email, args.password,
                     args.target_language, args.json)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            print(result.stderr.strip(), file=sys.stderr)
            sys.exit(result.returncode)
        print(result.stdout.strip())
    except subprocess.TimeoutExpired:
        print("Transcription timed out (30 min limit). The video may be too long.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
