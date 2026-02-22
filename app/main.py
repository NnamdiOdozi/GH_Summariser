import os
import re
import subprocess
import sys
import json
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

    # Use provided branch, or fall back to branch from URL, or default to "main"
    target_branch = branch or parsed.get("branch") or "main"

    # Build clean GitHub URL without branch/path
    repo_url = f"https://github.com/{parsed['owner']}/{parsed['repo']}"

    output_file = f"{parsed['owner']}-{parsed['repo']}.txt"

    cmd = [
        "uvx", "gitingest",
        repo_url,
        "-o", output_file,
    ]

    if target_branch:
        cmd.extend(["-b", target_branch])

    if token:
        cmd.extend(["-t", token])

    if max_size:
        cmd.extend(["-s", str(max_size)])

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    result.check_returncode()

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

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()

    result = response.json()
    return result["choices"][0]["message"]["content"]


def main():
    # This is not meant to be a production entry point, just a quick test harness for development. It doesn't call the LLM API by default to avoid unnecessary calls during development, but you can set call_llm_api=True to test the summarization as well.
    dotenv.load_dotenv(".env.claude")

    GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    url = "https://github.com/doublewordai/batch-skill/tree/main"

    result = run_gitdigest(url, GITHUB_TOKEN, word_count=500)
    print(f"Output saved to: {result['output_file']}")

    if "summary" in result:
        print(f"\n=== SUMMARY ===\n{result['summary']}")


if __name__ == "__main__":
    main()
