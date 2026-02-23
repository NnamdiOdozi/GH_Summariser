import os
import re
import shutil
import subprocess
import sys
import json
import argparse
from urllib.parse import urlparse

import dotenv
import requests


# Constants and defaults
DEFAULT_WORD_COUNT = 500
DEFAULT_MAX_SIZE = 10485760  # 10MB
DEFAULT_FREQUENCY_PENALTY = 0.3
OUTPUT_DIR = "git_summaries"
DEFAULT_EXCLUDE_PATTERNS = [
    # Binary/media files
    "*.pdf", "*.csv", "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.svg", "*.ico",
    "*.webp", "*.avif", "*.jfif", "*.tiff", "*.tif", "*.heic", "*.psd",
    "*.mp3", "*.mp4", "*.wav", "*.zip", "*.tar", "*.gz", "*.rar", "*.7z",
    "*.exe", "*.dll", "*.so", "*.bin", "*.dat", "*.db", "*.sqlite",
    "*.xls", "*.xlsx", "*.parquet", "*.pickle", "*.pkl",
    "*.h5", "*.hdf5", "*.npy", "*.npz", "*.pth", "*.pt", "*.onnx", "*.tflite", "*.weights",
    # Documents (binary formats)
    "*.docx", "*.doc", "*.pptx", "*.ppt", "*.odt", "*.odp",
    # Lockfiles
    "*.lock",
    # Data/output directories
    "data/*",
    # Misc binary artifacts
    "*.stackdump",
]


def parse_github_url(url: str) -> dict:
    """Parse any GitHub URL to extract owner, repo, branch, and path."""

    url = url.rstrip('/').replace('.git', '')

    # Handle SSH format (git@github.com:owner/repo...)
    if url.startswith('git@'):
        match = re.match(r'git@github\.com:(.+)', url)
        if match:
            path = match.group(1)
        else:
            raise ValueError(f"Invalid SSH GitHub URL: {url}")
    else:
        # Remove protocol (https://, git://, etc.)
        parsed = urlparse(url if '://' in url else f"https://{url}")
        path = parsed.path.lstrip('/')

    parts = path.split('/')

    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")

    owner = parts[0]
    repo = parts[1]

    result = {"owner": owner, "repo": repo, "branch": "main", "path": ""}

    if len(parts) > 3 and parts[2] in ("tree", "blob"):
        result["branch"] = parts[3]
        result["path"] = "/".join(parts[4:]) if len(parts) > 4 else ""

    return result


def run_gitdigest(
    url: str,
    token: str = None,
    branch: str = None,
    max_size: int = DEFAULT_MAX_SIZE,
    include_pattern: str = None,
    exclude_patterns: list = None,
    word_count: int = DEFAULT_WORD_COUNT,
    call_llm_api: bool = True,
) -> dict:
    """Run gitingest on a GitHub URL and optionally call Doubleword API for summarization."""

    parsed = parse_github_url(url)

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_file = os.path.join(OUTPUT_DIR, f"{parsed['owner']}-{parsed['repo']}.txt")

    # If user specified a branch explicitly, embed it in the URL for gitingest
    # (gitingest handles /tree/branch URLs natively and more reliably than -b flag)
    if branch:
        repo_url = f"https://github.com/{parsed['owner']}/{parsed['repo']}/tree/{branch}"
    else:
        repo_url = url

    # Build gitingest command
    venv_gitingest = os.path.join(os.path.dirname(sys.executable), "gitingest")
    if os.path.isfile(venv_gitingest):
        cmd = [venv_gitingest, repo_url, "-o", output_file]
    elif shutil.which("gitingest"):
        cmd = ["gitingest", repo_url, "-o", output_file]
    else:
        cmd = ["uvx", "gitingest", repo_url, "-o", output_file]

    if token:
        cmd.extend(["-t", token])

    if max_size:
        cmd.extend(["-s", str(max_size)])

    patterns = exclude_patterns if exclude_patterns is not None else DEFAULT_EXCLUDE_PATTERNS
    for pat in patterns:
        cmd.extend(["-e", pat])

    print(f"DEBUG cmd: {cmd}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"DEBUG rc={result.returncode} stderr={result.stderr[:500]}", file=sys.stderr)

    if result.returncode != 0:
        raise RuntimeError(f"gitingest failed: {result.stderr.strip()}")

    result_dict = {
        "output_file": output_file,
    }

    # Optionally call Doubleword API for summarization
    if call_llm_api:
        # Read the digest file
        with open(output_file, "r") as f:
            digest_content = f.read()

        # Read prompt and substitute word_count
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        with open(prompt_path, "r") as f:
            prompt_template = f.read()

        prompt = prompt_template.replace("{word_count}", str(word_count))

        # Call Doubleword API
        max_tokens = int(word_count * 1.5)
        summary = call_doubleword_api(prompt, digest_content, max_tokens=max_tokens)
        result_dict["summary"] = summary

    # Save result to JSON file for debugging/inspection
    output_json = output_file.replace(".txt", "_llm.json")
    with open(output_json, "w") as f:
        json.dump(result_dict, f, indent=2)

    return result_dict


def call_doubleword_api(prompt: str, digest_content: str, max_tokens: int = int(DEFAULT_WORD_COUNT * 1.5)) -> str:
    """Call Doubleword API to get a summary of the repo."""

    dotenv.load_dotenv(".env.claude")

    api_token = os.getenv("DOUBLEWORD_AUTH_TOKEN")
    base_url = os.getenv("DOUBLEWORD_BASE_URL")
    model = os.getenv("DOUBLEWORD_MODEL", "default-model")

    if not api_token or not base_url:
        raise ValueError("DOUBLEWORD_AUTH_TOKEN and DOUBLEWORD_BASE_URL must be set")

    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\n---\n\nRepository Contents:\n{digest_content}"
            }
        ],
        "max_tokens": max_tokens,
        "frequency_penalty": DEFAULT_FREQUENCY_PENALTY,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=300)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a GitHub repository and optionally summarize with LLM"
    )
    parser.add_argument("-u", "--url", required=True, help="GitHub repository URL")
    parser.add_argument("-t", "--token", default=None, help="GitHub Personal Access Token (required for private repos)")
    parser.add_argument("-b", "--branch", default=None, help="Branch name (defaults to main)")
    parser.add_argument("-w", "--word-count", type=int, default=DEFAULT_WORD_COUNT, help=f"Summary word count (default: {DEFAULT_WORD_COUNT})")
    parser.add_argument("-c", "--call-llm-api", action="store_true", help="Call LLM API for summarization")
    parser.add_argument("-m", "--max-size", type=int, default=DEFAULT_MAX_SIZE, help=f"Max file size in bytes (default: {DEFAULT_MAX_SIZE})")
    parser.add_argument("-e", "--exclude-pattern", action="append", default=None, dest="exclude_patterns",
                        help="Glob pattern to exclude (repeatable). Defaults to common binary/data extensions.")

    args = parser.parse_args()

    dotenv.load_dotenv(".env.claude")

    result = run_gitdigest(
        url=args.url,
        token=args.token,
        branch=args.branch,
        word_count=args.word_count,
        call_llm_api=args.call_llm_api,
        max_size=args.max_size,
        exclude_patterns=args.exclude_patterns,
    )

    print(f"Output saved to: {result['output_file']}")

    if "summary" in result:
        print(f"\n=== SUMMARY ===\n{result['summary']}")


if __name__ == "__main__":
    main()
