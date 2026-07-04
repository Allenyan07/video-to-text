#!/usr/bin/env python3
"""
Python wrapper for transcriptgenerate_transcribe.mjs.

Usage:
    python3 transcribe.py --url 'VIDEO_URL'
    python3 transcribe.py --url 'VIDEO_URL' --json

Environment variables TG_EMAIL / TG_PASSWORD are auto-loaded from .env.
Supports task queue: if a previous run was interrupted, resumes polling the
existing task instead of creating a duplicate (no double charge).
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _load_env_file():
    """Load TG_EMAIL / TG_PASSWORD from .env files if not already in environment."""
    if os.environ.get("TG_EMAIL") and os.environ.get("TG_PASSWORD"):
        return

    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    profile = os.environ.get("HERMES_PROFILE", "product-manager")

    candidates = [
        "/home/agentuser/.hermes/.env",
        os.path.join(hermes_home, "profiles", profile, ".env"),
        str(Path(__file__).resolve().parent.parent / ".env"),
    ]

    for env_path in candidates:
        if not os.path.isfile(env_path):
            continue
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        if key in ("TG_EMAIL", "TG_PASSWORD") and key not in os.environ:
                            os.environ[key] = val.strip()
        except OSError:
            continue


_load_env_file()


def find_node_script() -> Path:
    script_dir = Path(__file__).resolve().parent
    mjs_path = script_dir / "transcriptgenerate_transcribe.mjs"
    if not mjs_path.exists():
        raise FileNotFoundError(f"Node.js script not found: {mjs_path}")
    return mjs_path


def find_node() -> str:
    for candidate in ["node", os.path.expanduser("~/.local/share/fnm/node")]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise FileNotFoundError("Node.js is not available.")


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _run_node(args_list: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(args_list, capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe videos via TranscriptGenerate.com"
    )
    parser.add_argument("--url", required=True, help="Video URL to transcribe")
    parser.add_argument("--email", default=os.environ.get("TG_EMAIL"),
                        help="TranscriptGenerate account email")
    parser.add_argument("--password", default=os.environ.get("TG_PASSWORD"),
                        help="TranscriptGenerate account password")
    parser.add_argument("--target-language", default="auto")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache AND task queue, force new API call")

    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error("Missing --email/--password. Set TG_EMAIL/TG_PASSWORD in .env")

    scripts_dir = Path(__file__).resolve().parent
    cache_path = scripts_dir / ".transcribe_cache.json"
    queue_path = scripts_dir / ".task_queue.json"
    node_script = str(find_node_script())
    node_bin = find_node()
    url_hash = _hash_url(args.url)

    # ====== 1. Check completed cache ======
    if not args.no_cache:
        cache = _load_json(cache_path)
        if url_hash in cache:
            entry = cache[url_hash]
            age = time.time() - entry.get("ts", 0)
            sys.stderr.write(
                f"[cache] completed {age:.0f}s ago, returning saved result. "
                f"Use --no-cache to force re-transcription.\n"
            )
            if args.json:
                print(json.dumps(entry["result"], ensure_ascii=False, indent=2))
            else:
                print(entry["result"].get("textContent", ""))
            return

    # ====== 2. Check in-progress task queue ======
    if not args.no_cache:
        queue = _load_json(queue_path)
        pending = queue.get(url_hash)
        if pending:
            task_id = pending.get("taskId")
            sys.stderr.write(
                f"[resume] found in-progress task {task_id}, "
                f"polling without creating new task...\n"
            )
            cmd = [
                node_bin, node_script,
                "--url", args.url,
                "--email", args.email,
                "--password", args.password,
                "--task-id", task_id,
                "--target-language", args.target_language,
            ]
            if args.json:
                cmd.append("--json")

            try:
                result = _run_node(cmd, timeout=1800)
            except subprocess.TimeoutExpired:
                sys.stderr.write(
                    f"[timeout] task {task_id} still in progress. "
                    f"Re-run later to resume polling — no double charge.\n"
                )
                sys.exit(1)

            if result.returncode != 0:
                sys.stderr.write(f"[error] {result.stderr.strip()}\n")
                sys.exit(result.returncode)

            output = result.stdout.strip()
            _handle_result(output, args, url_hash, cache_path, queue_path, args.url, task_id)
            print_output(output, args)
            return

    # ====== 3. Create new task ======
    cmd = [
        node_bin, node_script,
        "--url", args.url,
        "--email", args.email,
        "--password", args.password,
        "--target-language", args.target_language,
    ]
    if args.json:
        cmd.append("--json")

    try:
        result = _run_node(cmd, timeout=1800)
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "[timeout] Transcription timed out (30 min). "
            "If a task was created, re-running will resume it — no double charge.\n"
        )
        sys.exit(1)

    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    output = result.stdout.strip()
    _handle_result(output, args, url_hash, cache_path, queue_path, args.url)
    print_output(output, args)


def _handle_result(output: str, args, url_hash: str,
                   cache_path: Path, queue_path: Path,
                   url: str, expected_task_id: str = None):
    """On success: save to cache, remove from queue. On WAITING: save to queue."""
    if args.no_cache:
        return
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return

    task_id = parsed.get("taskId", "")
    status = parsed.get("status", "")

    if status == "SUCCESS":
        # Save to completed cache
        cache = _load_json(cache_path)
        cache[url_hash] = {"result": parsed, "ts": time.time(), "url": url}
        _save_json(cache_path, cache)
        # Remove from in-progress queue
        queue = _load_json(queue_path)
        queue.pop(url_hash, None)
        _save_json(queue_path, queue)
    elif status == "WAITING" and task_id:
        # Task created but not finished — save so we can resume later
        queue = _load_json(queue_path)
        queue[url_hash] = {"taskId": task_id, "ts": time.time(), "url": url}
        _save_json(queue_path, queue)
        sys.stderr.write(
            f"[queued] task {task_id} still WAITING. "
            f"Re-run anytime to resume — no double charge.\n"
        )
    elif status in ("FAILURE", "FAILED") or (status and status != "WAITING"):
        # Task is done (failed/expired) — clean up queue so next run creates fresh
        queue = _load_json(queue_path)
        queue.pop(url_hash, None)
        _save_json(queue_path, queue)
    # If expected_task_id was provided (resume mode) and status is not SUCCESS,
    # the task might be expired/failed — let the caller decide to re-create


def print_output(output: str, args):
    """Print the final output. JSON mode: raw. Text mode: just textContent."""
    if args.json:
        print(output)
    else:
        try:
            parsed = json.loads(output)
            print(parsed.get("textContent", output))
        except json.JSONDecodeError:
            print(output)


if __name__ == "__main__":
    main()
