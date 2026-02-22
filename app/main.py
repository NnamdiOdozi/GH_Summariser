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
    exclude_pattern: str = None,
    word_count: int = DEFAULT_WORD_COUNT,
    call_llm_api: bool = True,
) -> dict:
    """Run gitingest on a GitHub URL and optionally call Doubleword API for summarization."""

    parsed = parse_github_url(url)

    # Determine branch: try user-specified, then URL branch, then fallbacks
    initial_branch = branch or parsed.get("branch")
    branch_fallbacks = []
    if initial_branch:
        branch_fallbacks = [initial_branch]
    branch_fallbacks.extend(["main", "master"])

    # Try each branch until one works
    output_file = None
    for target_branch in branch_fallbacks:
        # Build clean GitHub URL without branch/path
        repo_url = f"https://github.com/{parsed['owner']}/{parsed['repo']}"

        output_file = f"{parsed['owner']}-{parsed['repo']}.txt"

        # Try gitingest directly (pip-installed), fall back to uvx gitingest
        if shutil.which("gitingest"):
            cmd = ["gitingest", repo_url, "-o", output_file]
        else:
            cmd = ["uvx", "gitingest", repo_url, "-o", output_file]

        cmd.extend(["-b", target_branch])

        if token:
            cmd.extend(["-t", token])

        if max_size:
            cmd.extend(["-s", str(max_size)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Successfully cloned branch: {target_branch}")
            break
        else:
            print(f"Branch '{target_branch}' not found or empty, trying next...", file=sys.stderr)
            continue

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
        summary = call_doubleword_api(prompt, digest_content)
        result_dict["summary"] = summary

    # Save result to JSON file for debugging/inspection
    output_json = output_file.replace(".txt", "_llm.json")
    with open(output_json, "w") as f:
        json.dump(result_dict, f, indent=2)

    return result_dict


def call_doubleword_api(prompt: str, digest_content: str) -> str:
    """Call Doubleword API to get a summary of the repo."""

    dotenv.load_dotenv(".env.claude")

    api_token = os.getenv("DOUBLEWORD_AUTH_TOKEN")
    base_url = os.getenv("DOUBLEWORD_BASE_URL")
    model = os.getenv("DOUBLEWORD_MODEL", "default-model")

    if not api_token or not base_url:
        raise ValueError("DOUBLEWORD_AUTH_TOKEN and DOUBLEWORD_BASE_URL must be set")

    url = f"{base_url}/v1/chat/completions"

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

    args = parser.parse_args()

    dotenv.load_dotenv(".env.claude")

    result = run_gitdigest(
        url=args.url,
        token=args.token,
        branch=args.branch,
        word_count=args.word_count,
        call_llm_api=args.call_llm_api,
        max_size=args.max_size,
    )

    print(f"Output saved to: {result['output_file']}")

    if "summary" in result:
        print(f"\n=== SUMMARY ===\n{result['summary']}")


if __name__ == "__main__":
    main()
