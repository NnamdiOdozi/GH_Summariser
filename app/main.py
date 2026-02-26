import logging
import os
import re
import shutil
import subprocess
import sys
import json
import time
import argparse
import asyncio
import tomllib
from urllib.parse import urlparse

import dotenv
from openai import OpenAI
from app.triage import triage_digest

logger = logging.getLogger(__name__)


# Load config from config.toml
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.toml")
with open(CONFIG_PATH, "rb") as _f:
    CONFIG = tomllib.load(_f)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.load_dotenv(os.path.join(_PROJECT_ROOT, ".env.claude"))

# Constants and defaults — all read from config.toml.
DEFAULT_WORD_COUNT = CONFIG["digest"]["default_word_count"]
DEFAULT_MAX_SIZE = CONFIG["digest"]["default_max_size"]
DEFAULT_FREQUENCY_PENALTY = CONFIG["llm"].get("frequency_penalty", 0.3)
OUTPUT_DIR = CONFIG["digest"]["output_dir"]
DEFAULT_EXCLUDE_PATTERNS = CONFIG["digest"]["default_exclude_patterns"]
MAX_SUMMARIES = CONFIG["digest"].get("max_summaries", 20)


def cleanup_summaries():
    """Keep only the most recent MAX_SUMMARIES digest pairs in OUTPUT_DIR."""
    txt_files = sorted(
        [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".txt") and not f.startswith(".")],
        key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)),
    )
    excess = txt_files[: max(0, len(txt_files) - MAX_SUMMARIES)]
    for name in excess:
        for ext in (".txt", "_llm.json"):
            path = os.path.join(OUTPUT_DIR, name.replace(".txt", ext))
            if os.path.exists(path):
                os.remove(path)
                logger.info("Cleanup: removed %s", path)


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
    focus: str = None,
    triage: bool = True,
) -> dict:
    """Run gitingest on a GitHub URL and optionally call LLM API for summarization."""

    parsed = parse_github_url(url)

    # Ensure output directory exists and trim old summaries
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_summaries()

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

    patterns = DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or [])
    for pat in patterns:
        cmd.extend(["-e", pat])

    logger.info("Running gitingest for %s/%s", parsed["owner"], parsed["repo"])
    logger.debug("gitingest cmd: %s", cmd)
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    logger.info("gitingest finished in %.1fs (rc=%d)", elapsed, result.returncode)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("gitingest failed: %s", stderr)
        if any(x in stderr.lower() for x in ("401", "403", "not found", "authentication", "private")):
            raise RuntimeError(
                f"Repository not accessible: {parsed['owner']}/{parsed['repo']}. "
                "If this is a private repo, provide a GitHub token via the 'token' field."
            )
        raise RuntimeError(f"gitingest failed: {stderr}")

    # Read the digest file and compute stats
    with open(output_file, "r") as f:
        digest_content = f.read()

    lines = digest_content.count("\n")
    words = len(digest_content.split())
    estimated_tokens = int(len(digest_content) / 3.5)

    # Extract directory tree (everything before first ===== separator)
    tree_separator = "=" * 48
    directory_tree = ""
    file_count = 0
    folder_count = 0
    if tree_separator in digest_content:
        directory_tree = digest_content.split(tree_separator)[0].strip()
        for line in directory_tree.split("\n"):
            stripped = line.strip()
            if "├──" in stripped or "└──" in stripped:
                name = stripped.split("── ", 1)[-1] if "── " in stripped else ""
                if name.endswith("/"):
                    folder_count += 1
                else:
                    file_count += 1

    # Determine branch used
    branch_used = branch if branch else parsed.get("branch", "default")

    result_dict = {
        "output_file": output_file,
        "branch": branch_used,
        "digest_stats": {
            "lines": lines,
            "words": words,
            "estimated_tokens": estimated_tokens,
            "file_count": file_count,
            "folder_count": folder_count,
        },
        # directory_tree omitted from JSON — too verbose for large repos
    }

    # Optionally call Doubleword API for summarization
    if call_llm_api:
        # Read prompt and substitute word_count
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        with open(prompt_path, "r") as f:
            prompt_template = f.read()

        prompt = prompt_template.replace("{word_count}", str(word_count))

        # Append user's focus instruction if provided
        if focus:
            prompt += f"\n\nAdditional user instruction: {focus}"

        # Triage: trim digest to token budget before sending to LLM
        triage_config = CONFIG.get("triage", {})
        if triage and triage_config.get("enabled", True):
            triage_result = triage_digest(digest_content, triage_config)
            digest_content = triage_result["text"]
            result_dict["triage_applied"] = triage_result["triage_applied"]
            result_dict["pre_triage_tokens"] = triage_result["pre_triage_tokens"]
            result_dict["post_triage_tokens"] = triage_result["post_triage_tokens"]
            result_dict["files_dropped_count"] = len(triage_result["files_dropped"])
        else:
            result_dict["triage_applied"] = False
            result_dict["pre_triage_tokens"] = estimated_tokens
            result_dict["post_triage_tokens"] = estimated_tokens
            result_dict["files_dropped_count"] = 0

        # Call LLM API (2x multiplier gives headroom for markdown formatting overhead;
        # reasoning models need a larger budget — override via max_output_tokens in config)
        max_tokens = int(word_count * 2.0)
        logger.info("Calling LLM (provider=%s, max_tokens=%d)", CONFIG["llm"]["provider"], max_tokens)
        t0 = time.time()
        raw = call_llm(prompt, digest_content, max_tokens=max_tokens)
        elapsed = time.time() - t0
        logger.info("LLM response received in %.1fs (%d words)", elapsed, len(raw.split()))

        # Parse structured JSON response from LLM
        try:
            # Strip markdown fences if the model wrapped the JSON anyway
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            result_dict["summary"] = parsed.get("summary", raw)
            result_dict["technologies"] = parsed.get("technologies", [])
            result_dict["structure"] = parsed.get("structure", "")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("LLM did not return valid JSON; storing raw response as summary")
            result_dict["summary"] = raw

    # Save result to JSON file for debugging/inspection
    output_json = output_file.replace(".txt", "_llm.json")
    with open(output_json, "w") as f:
        json.dump(result_dict, f, indent=2)

    return result_dict


def call_llm(prompt: str, digest_content: str, max_tokens: int = int(DEFAULT_WORD_COUNT * 2.0)) -> str:
    """Call the configured LLM provider to get a summary of the repo."""

    
    provider = CONFIG["llm"]["provider"]
    provider_config = CONFIG["llm"][provider]

    api_token = os.getenv(provider_config["auth_env"])
    base_url = provider_config["base_url"]
    model = os.getenv(provider_config.get("model_env", ""), "") or provider_config["model"]
    max_tokens = provider_config.get("max_output_tokens", max_tokens)

    if not api_token:
        raise ValueError(f"{provider_config['auth_env']} must be set in environment")

    logger.debug("LLM provider=%s model=%s base_url=%s", provider, model, base_url)

    kwargs = {
        "model": model,
        "messages": [
            {"role": "user", "content": f"{prompt}\n\n---\n\nRepository Contents:\n{digest_content}"}
        ],
        "max_tokens": max_tokens,
        "frequency_penalty": DEFAULT_FREQUENCY_PENALTY,
    }

    response_format = provider_config.get("response_format")
    if response_format == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "repo_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary":      {"type": "string"},
                        "technologies": {"type": "array", "items": {"type": "string"}},
                        "structure":    {"type": "string"},
                    },
                    "required": ["summary", "technologies", "structure"],
                    "additionalProperties": False,
                },
            },
        }
    elif response_format:
        kwargs["response_format"] = {"type": response_format}

    reasoning_effort = provider_config.get("reasoning_effort")
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    if provider == "doubleword" and provider_config.get("use_autobatcher", False):
        from autobatcher import BatchOpenAI
        completion_window = provider_config.get("completion_window", "1h")
        logger.info("Using Autobatcher (completion_window=%s)", completion_window)
        async def _call():
            client = BatchOpenAI(api_key=api_token, base_url=base_url, completion_window=completion_window)
            return await client.chat.completions.create(**kwargs)
        response = asyncio.run(_call())
    else:
        client = OpenAI(api_key=api_token, base_url=base_url, timeout=CONFIG["llm"].get("timeout", 300))
        response = client.chat.completions.create(**kwargs)

    content = response.choices[0].message.content
    if content is None:
        logger.debug("LLM returned null content. Full response: %s", response.model_dump_json())
        raise RuntimeError("LLM returned null content — reasoning model may have exhausted output tokens")

    return content


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
    parser.add_argument("-f", "--focus", default=None, help="Focus instruction appended to the LLM prompt (e.g. 'authentication flow')")
    parser.add_argument("--no-triage", action="store_true", help="Disable triage (send full digest to LLM, useful for debugging)")

    args = parser.parse_args()

    
    result = run_gitdigest(
        url=args.url,
        token=args.token,
        branch=args.branch,
        word_count=args.word_count,
        call_llm_api=args.call_llm_api,
        max_size=args.max_size,
        exclude_patterns=args.exclude_patterns,
        focus=args.focus,
        triage=not args.no_triage,
    )

    print(f"Output saved to: {result['output_file']}")

    if "summary" in result:
        print(f"\n=== SUMMARY ===\n{result['summary']}")


if __name__ == "__main__":
    main()
