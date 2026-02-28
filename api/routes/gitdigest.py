# api/routes/gitdigest.py
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, SecretStr
from gitdigest_app.main import run_gitdigest, DEFAULT_WORD_COUNT, DEFAULT_MAX_SIZE, OUTPUT_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

class GitdigestRequest(BaseModel):
    github_url: str = Field(
        "https://github.com/NnamdiOdozi/mlx-digit-app",
        description=(
            "GitHub repository URL. Accepts HTTPS URLs, SSH URLs (git@github.com:owner/repo), "
            "and URLs with branch paths (e.g. /tree/dev). Branch in the URL is auto-detected. "
            "If the repo is private and no token is supplied, the request will fail with 401."
        ),
    )
    token: SecretStr | None = Field(
        None,
        description=(
            "GitHub Personal Access Token. Required for private repos; optional for public. "
            "Needs 'repo' scope (classic PAT) or 'Contents: read' (fine-grained PAT). "
            "Never logged or stored — used only for the gitingest clone step, then discarded."
        ),
        examples=[""],
    )
    branch: Optional[str] = Field(
        None,
        description=(
            "Branch name override (case-sensitive). Takes priority over any branch embedded in the URL. "
            "Leave empty to use the branch in the URL, or the repo's default branch if none is specified."
        ),
        examples=[""],
    )
    max_size: int = Field(
        DEFAULT_MAX_SIZE,
        description=(
            f"Maximum file size in bytes. Files larger than this are skipped by gitingest before the digest is built. "
            f"Default: {DEFAULT_MAX_SIZE // 1048576}MB. Reduce to speed up ingestion of repos with large files."
        ),
    )
    word_count: int = Field(
        DEFAULT_WORD_COUNT,
        description=(
            f"Target word count for the LLM summary (default: {DEFAULT_WORD_COUNT}). "
            "The LLM treats this as a guide, not a hard limit. Actual output may vary by ±20%. "
            "Only applies when call_llm_api is true."
        ),
    )
    call_llm_api: bool = Field(
        True,
        description=(
            "When true (default), sends the digest to the configured LLM and returns a structured summary. "
            "When false, skips the LLM call and returns the raw digest text in the 'content' field instead of 'summary'. "
            "Use false to inspect the digest before committing to an LLM call."
        ),
    )
    exclude_patterns: Optional[list[str]] = Field(
        None,
        description=(
            "Additional glob patterns to exclude from the digest, e.g. ['tests/*', 'docs/*', '*.csv']. "
            "These are additive — they extend the built-in defaults (binaries, lockfiles, build output, etc.) "
            "and cannot remove them. Useful for known-noisy directories specific to a given repo."
        ),
    )
    focus: Optional[str] = Field(
        None,
        description=(
            "Short instruction appended to the default summary prompt to steer the LLM analysis. "
            "Examples: 'Focus on the authentication flow', 'What are the main data models?', "
            "'How do I run this locally?'. Only applies when call_llm_api is true."
        ),
        examples=[""],
    )
    triage: bool = Field(
        True,
        description=(
            "When true (default), automatically trims the digest to fit within the LLM context window "
            "by classifying files into signal tiers and dropping the lowest-signal files first. "
            "The response always includes a triage block showing tokens before/after and files dropped. "
            "Set to false to send the full digest as-is — useful for debugging triage behaviour."
        ),
    )


@router.post("/summarize", summary="Ingest GitHub repository for LLM summarization")
async def gitdigest_endpoint(request: GitdigestRequest):
    """
    Clone a GitHub repository, extract and summarise its contents for LLM analysis. 
    
    Due to the context window limits of LLMs, it excludes binaries and data files. These are set out in the config.toml file 
    
    Users are also able to add additional files and folder names and patterns to be excluded using the exclude_patterns field. 
    
    As a 3rd layer, there is a triage mechanism that drops lowest-signal files to fit within the LLM context window. 
    
    Below are the request parameters:

    - **github_url**: GitHub repository URL. Can include branch (e.g., `https://github.com/owner/repo/tree/dev`)
    - **token**: Optional GitHub PAT for private repos
    - **branch**: Optional branch override. If set, takes priority over any branch in the URL
    - **max_size**: Skip files larger than this size in bytes
    - **word_count**: Target word count for the summary (default: 750)
    - **call_llm_api**: Whether to call the LLM summarization API (default: True)
    - **exclude_patterns**: Optional additional list of glob patterns to exclude files or directories from the digest (e.g., `["*.pdf", "*.jpg", "docs/*", "tests/*"]`). When omitted, sensible defaults are used that exclude binary files, images, data files, ML model weights, lockfiles, etc.
    - **focus**: Optional short instruction appended to the default summary prompt to steer the analysis. The default prompt is defined in `app/prompt.txt` in the project repo.
    - **triage**: Optional boolean, default `true`. When true, the digest is automatically trimmed to fit within the LLM context window by classifying files into signal tiers and dropping the lowest-signal files first. Set to `false` to send the full digest as-is.

    **Example focus prompts:**
    - "What does this system do at a high level?"
    - "Where does execution start and how does control flow through the system?"
    - "What are the core modules and how are they coupled?"
    - "Where is the business logic vs infrastructure logic?"
    - "What are the most critical and risky parts of this codebase?"
    - "What are the main data models and how does data flow?"
    - "How do I run this locally?"
    - "What external systems does this depend on?"
    - "Where are the extension points for adding new features?"
    - "How healthy is this codebase overall?"
    - "Focus on the authentication and security implementation"
    - "Focus on the test coverage and CI/CD setup"
    """
    # Filter out Swagger UI placeholder values
    token = request.token.get_secret_value() if request.token and request.token.get_secret_value() != "string" else None
    branch = request.branch if request.branch and request.branch != "string" else None
    exclude_patterns = request.exclude_patterns
    if exclude_patterns and exclude_patterns == ["string"]:
        exclude_patterns = None
    focus = request.focus if request.focus and request.focus != "string" else None

    logger.info(
        "POST /gitdigest url=%s branch=%s llm=%s word_count=%d focus=%s",
        request.github_url, branch, request.call_llm_api, request.word_count, focus,
    )
    t0 = time.time()

    try:
        result = run_gitdigest(
            url=request.github_url,
            token=token,
            branch=branch,
            max_size=request.max_size if request.max_size else DEFAULT_MAX_SIZE,
            word_count=request.word_count,
            call_llm_api=request.call_llm_api,
            exclude_patterns=exclude_patterns,
            focus=focus,
            triage=request.triage,
        )

        # Summary fields at top, metadata below
        response_data = {"status": "success"}

        if request.call_llm_api:
            response_data["summary"] = result.summary or ""
            response_data["technologies"] = (result.technologies or [])[:12]
            response_data["structure"] = result.structure or ""
        else:
            with open(result.output_file, "r") as f:
                response_data["content"] = f.read()

        response_data["branch"] = result.branch
        response_data["output_file"] = result.output_file
        response_data["digest_stats"] = result.digest_stats.model_dump()

        response_data["triage"] = {
            "applied": result.triage_applied or False,
            "pre_triage_tokens": result.pre_triage_tokens or 0,
            "post_triage_tokens": result.post_triage_tokens or 0,
            "files_dropped_count": result.files_dropped_count or 0,
        }

        elapsed = time.time() - t0
        logger.info("POST /gitdigest completed in %.1fs (status=success)", elapsed)
        return response_data

    except ValueError as e:
        elapsed = time.time() - t0
        logger.error("POST /gitdigest bad request after %.1fs: %s", elapsed, e)
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})
    except RuntimeError as e:
        elapsed = time.time() - t0
        msg = str(e)
        logger.error("POST /gitdigest failed after %.1fs: %s", elapsed, msg, exc_info=True)
        if "not accessible" in msg or "private repo" in msg.lower():
            return JSONResponse(status_code=401, content={"status": "error", "message": msg})
        if "context window" in msg.lower() or "context length" in msg.lower():
            return JSONResponse(status_code=422, content={"status": "error", "message": msg})
        return JSONResponse(status_code=500, content={"status": "error", "message": msg})
    except Exception as e:
        elapsed = time.time() - t0
        logger.error("POST /gitdigest failed after %.1fs: %s", elapsed, e, exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/summarize/{filename}", summary="Download digest file")
async def download_digest(filename: str):
    """
    Download a previously generated digest file by filename.

    Use just the filename, not the full path (e.g., `NnamdiOdozi-mlx-digit-app_llm.json`, not `git_summaries/NnamdiOdozi-mlx-digit-app_llm.json`).
    """
    # Strip leading directory prefix if user included it
    filename = os.path.basename(filename)

    # Security: only allow .txt or .json files, no path traversal
    if not (filename.endswith(".txt") or filename.endswith(".json")) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename. Use just the filename e.g. owner-repo_llm.json")

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, filename=filename)


@router.get("/summarize/{filename}/preview", summary="Preview digest as formatted Markdown")
async def preview_digest(filename: str):
    """
    Returns a previously generated digest as a formatted Markdown document.

    Use the `_llm.json` filename (e.g., `NnamdiOdozi-mlx-digit-app_llm.json`).
    Can also be used with `.txt` files to preview the raw digest.
    """
    import json as _json

    filename = os.path.basename(filename)

    if not (filename.endswith(".txt") or filename.endswith(".json")) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename. Use e.g. owner-repo_llm.json")

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    # For .txt files, wrap in a code block
    if filename.endswith(".txt"):
        with open(filepath, "r") as f:
            content = f.read()
        md = f"# Raw Digest\n\n```\n{content}\n```"
        return PlainTextResponse(md, media_type="text/markdown")

    # For .json files, format as Markdown
    with open(filepath, "r") as f:
        data = _json.load(f)

    parts = []

    # Header
    output_file = data.get("output_file", filename)
    repo_name = os.path.basename(output_file).replace(".txt", "").replace("_llm", "")
    parts.append(f"# {repo_name}\n")

    # Branch and stats
    branch = data.get("branch")
    if branch:
        parts.append(f"**Branch:** {branch}\n")

    stats = data.get("digest_stats", {})
    if stats:
        parts.append("## Digest Stats\n")
        parts.append("| Metric | Value |")
        parts.append("|--------|-------|")
        parts.append(f"| Lines | {stats.get('lines', 'N/A'):,} |")
        parts.append(f"| Words | {stats.get('words', 'N/A'):,} |")
        parts.append(f"| Estimated tokens | {stats.get('estimated_tokens', 'N/A'):,} |")
        parts.append(f"| Files | {stats.get('file_count', 'N/A')} |")
        parts.append(f"| Folders | {stats.get('folder_count', 'N/A')} |")
        parts.append("")

    # Directory tree
    tree = data.get("directory_tree", "")
    if tree:
        parts.append("## Directory Tree\n")
        parts.append(f"```\n{tree}\n```\n")

    # Summary
    summary = data.get("summary", "")
    if summary:
        parts.append("## Summary\n")
        parts.append(summary)
        parts.append("")

    md = "\n".join(parts)
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/prompt", summary="View the default summary prompt")
async def get_prompt():
    """
    Returns the default summary prompt that is sent to the LLM.
    The `focus` field in the POST request is appended to this prompt.
    """
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "gitdigest_app", "prompt.txt")
    with open(prompt_path, "r") as f:
        return {"prompt": f.read()}
