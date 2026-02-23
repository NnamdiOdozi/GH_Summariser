# api/routes/gitdigest.py
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.main import run_gitdigest, DEFAULT_WORD_COUNT, DEFAULT_MAX_SIZE, OUTPUT_DIR

router = APIRouter()

class GitdigestRequest(BaseModel):
    url: str = Field("https://github.com/NnamdiOdozi/mlx-digit-app", description="GitHub repository URL. Can include branch info (e.g., /tree/dev). If no branch is in the URL or the branch field, defaults to the repo's default branch.")
    token: Optional[str] = Field(None, description="GitHub Personal Access Token (required only for private repos)", examples=[""])
    branch: Optional[str] = Field(None, description="Branch override (case-sensitive). If set, takes priority over any branch in the URL. Leave empty to auto-detect from URL or use repo default.", examples=[""])
    max_size: int = Field(DEFAULT_MAX_SIZE, description=f"Maximum file size in bytes to process (default: {DEFAULT_MAX_SIZE // 1048576}MB)")
    word_count: int = Field(DEFAULT_WORD_COUNT, description=f"Desired summary word count (default: {DEFAULT_WORD_COUNT})")
    call_llm_api: bool = Field(True, description="Whether to call LLM summarization API (default: True)")
    exclude_patterns: Optional[list[str]] = Field(None, description="Glob patterns to exclude files or directories (e.g., ['*.pdf', '*.csv', 'docs/*', 'tests/*']). Defaults to common binary/data extensions.")
    focus: Optional[str] = Field(None, description="Optional short instruction appended to the default summary prompt to steer the analysis (e.g., 'Focus on the authentication module'). See example prompts below.", examples=[""])


@router.post("/gitdigest", summary="Ingest GitHub repository for LLM summarization")
async def gitdigest_endpoint(request: GitdigestRequest):
    """
    Clone a GitHub repository, extract and summarise its contents for LLM analysis. Below are the request parameters:

    - **url**: GitHub repository URL. Can include branch (e.g., `https://github.com/owner/repo/tree/dev`)
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
    try:
        # Filter out Swagger UI placeholder values
        token = request.token if request.token and request.token != "string" else None
        branch = request.branch if request.branch and request.branch != "string" else None
        exclude_patterns = request.exclude_patterns
        if exclude_patterns and exclude_patterns == ["string"]:
            exclude_patterns = None

        focus = request.focus if request.focus and request.focus != "string" else None

        result = run_gitdigest(
            url=request.url,
            token=token,
            branch=branch,
            max_size=request.max_size if request.max_size else DEFAULT_MAX_SIZE,
            word_count=request.word_count,
            call_llm_api=request.call_llm_api,
            exclude_patterns=exclude_patterns,
            focus=focus,
        )

        response_data = {
            "status": "success",
            "output_file": result["output_file"],
            "branch": result.get("branch"),
            "digest_stats": result["digest_stats"],
            "directory_tree": result.get("directory_tree", ""),
        }

        if request.call_llm_api:
            response_data["summary"] = result.get("summary", "")
        else:
            with open(result["output_file"], "r") as f:
                response_data["content"] = f.read()

        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gitdigest/{filename}", summary="Download digest file")
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


@router.get("/prompt", summary="View the default summary prompt")
async def get_prompt():
    """
    Returns the default summary prompt that is sent to the LLM.
    The `focus` field in the POST request is appended to this prompt.
    """
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "prompt.txt")
    with open(prompt_path, "r") as f:
        return {"prompt": f.read()}
