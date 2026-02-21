import os
import re
import subprocess
import sys
from urllib.parse import urlparse

import dotenv


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


def run_gitingest(
    url: str,
    token: str = None,
    branch: str = None,
    max_size: int = 10485760,
    include_pattern: str = None,
    exclude_pattern: str = None,
) -> str:
    """Run gitingest on a GitHub URL and return the output file path."""

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

    if max_size:
        cmd.extend(["-s", str(max_size)])

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    result.check_returncode()

    return output_file


def main():
    dotenv.load_dotenv(".env.claude")

    GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    url = "https://github.com/doublewordai/batch-skill/tree/main"

    output_file = run_gitingest(url, GITHUB_TOKEN)
    print(f"Output saved to: {output_file}")


if __name__ == "__main__":
    main()


# # Create multimodal request
# request = {
#     "custom_id": "q4-report-2024",
#     "method": "POST",
#     "url": "/v1/chat/completions",
#     "body": {
#         "model": "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8",
#         "messages": [{
#             "role": "user",
#             "content": [
#                 {"type": "text", "text": "Create Q4 2024 report using ALL provided documents and charts."},
#                 {"type": "text", "text": f"Financials:\\n{doc1}"},
#             ]
#         }],
#         "max_tokens": 2000
#     }
# }