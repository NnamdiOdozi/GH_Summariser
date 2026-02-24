# api/routes/gitdigest.py
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from app.main import run_gitdigest, DEFAULT_WORD_COUNT, DEFAULT_MAX_SIZE, OUTPUT_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

class GitdigestRequest(BaseModel):
    github_url: str = Field("https://github.com/NnamdiOdozi/mlx-digit-app", description="GitHub repository URL. Can include branch info (e.g., /tree/dev). If no branch is in the URL or the branch field, defaults to the repo's default branch.")
    token: Optional[str] = Field(None, description="GitHub Personal Access Token (required only for private repos)", examples=[""])
    branch: Optional[str] = Field(None, description="Branch override (case-sensitive). If set, takes priority over any branch in the URL. Leave empty to auto-detect from URL or use repo default.", examples=[""])
    max_size: int = Field(DEFAULT_MAX_SIZE, description=f"Maximum file size in bytes to process (default: {DEFAULT_MAX_SIZE // 1048576}MB)")
    word_count: int = Field(DEFAULT_WORD_COUNT, description=f"Desired summary word count (default: {DEFAULT_WORD_COUNT})")
    call_llm_api: bool = Field(True, description="Whether to call LLM summarization API (default: True)")
    exclude_patterns: Optional[list[str]] = Field(None, description="Glob patterns to exclude files or directories (e.g., ['*.pdf', '*.csv', 'docs/*', 'tests/*']). Defaults to common binary/data extensions.")
    focus: Optional[str] = Field(None, description="Optional short instruction appended to the default summary prompt to steer the analysis (e.g., 'Focus on the authentication module'). See example prompts below.", examples=[""])
    triage: bool = Field(True, description="When True (default), automatically trims the digest to fit within the LLM context window by dropping lowest-signal files first. Disable to send the full digest as-is.")


@router.post("/summarize", summary="Ingest GitHub repository for LLM summarization")
async def gitdigest_endpoint(request: GitdigestRequest):
    """
    Clone a GitHub repository, extract and summarise its contents for LLM analysis. Due to the context window limits of the models used (Qwen3 30B and gpt-4.1-mini), it cannot deal with large codebases.  Some ideas for handloing large codebases are provided in the README.md file. Below are the request parameters:

    - **github_url**: GitHub repository URL. Can include branch (e.g., `https://github.com/owner/repo/tree/dev`)
    - **token**: Optional GitHub PAT for private repos
    - **branch**: Optional branch override. If set, takes priority over any branch in the URL
    - **max_size**: Skip files larger than this size in bytes
    - **word_count**: Target word count for the summary (default: 750)
    - **call_llm_api**: Whether to call the LLM summarization API (default: True)
    - **exclude_patterns**: Optional list of glob patterns to exclude files or directories from the digest (e.g., `["*.pdf", "*.jpg", "docs/*", "tests/*"]`). When omitted, sensible defaults are used that exclude binary files, images, data files, ML model weights, lockfiles, etc.
    - **focus**: Optional short instruction appended to the default summary prompt to steer the analysis. The default prompt is defined in `app/prompt.txt` in the project repo.

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
    token = request.token if request.token and request.token != "string" else None
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
            response_data["summary"] = result.get("summary", "")
            response_data["technologies"] = result.get("technologies", [])[:12]
            response_data["structure"] = result.get("structure", "")
        else:
            with open(result["output_file"], "r") as f:
                response_data["content"] = f.read()

        response_data["branch"] = result.get("branch")
        response_data["output_file"] = result["output_file"]
        response_data["digest_stats"] = result["digest_stats"]

        response_data["triage"] = {
            "applied": result.get("triage_applied", False),
            "pre_triage_tokens": result.get("pre_triage_tokens", 0),
            "post_triage_tokens": result.get("post_triage_tokens", 0),
            "files_dropped_count": result.get("files_dropped_count", 0),
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
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "prompt.txt")
    with open(prompt_path, "r") as f:
        return {"prompt": f.read()}
