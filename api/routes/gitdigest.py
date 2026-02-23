# api/routes/gitdigest.py
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.main import run_gitdigest, DEFAULT_WORD_COUNT, OUTPUT_DIR

router = APIRouter()

class GitdigestRequest(BaseModel):
    url: str = Field("https://github.com/NnamdiOdozi/mlx-digit-app", description="GitHub repository URL. Can include branch info (e.g., /tree/dev). If no branch is in the URL or the branch field, defaults to the repo's default branch.")
    token: Optional[str] = Field(None, description="GitHub Personal Access Token (required only for private repos)", examples=[""])
    branch: Optional[str] = Field(None, description="Branch override (case-sensitive). If set, takes priority over any branch in the URL. Leave empty to auto-detect from URL or use repo default.", examples=[""])
    max_size: int = Field(10485760, description="Maximum file size in bytes to process (default: 10MB)")
    word_count: int = Field(DEFAULT_WORD_COUNT, description=f"Desired summary word count (default: {DEFAULT_WORD_COUNT})")
    call_llm_api: bool = Field(True, description="Whether to call LLM summarization API (default: True)")
    exclude_patterns: Optional[list[str]] = Field(None, description="Glob patterns to exclude (e.g., ['*.pdf', '*.csv']). Defaults to common binary/data extensions.")


@router.post("/gitdigest", summary="Ingest GitHub repository for LLM summarization")
async def gitdigest_endpoint(request: GitdigestRequest):
    """
    Clone a GitHub repository, extract and summarise its contents for LLM analysis.

    - **url**: GitHub repository URL. Can include branch (e.g., `https://github.com/owner/repo/tree/dev`)
    - **token**: Optional GitHub PAT for private repos
    - **branch**: Optional branch override. If set, takes priority over any branch in the URL
    - **max_size**: Skip files larger than this size in bytes
    - **word_count**: Target word count for the summary (default: 500)
    - **call_llm_api**: Whether to call the LLM summarization API (default: True)
    - **exclude_patterns**: Optional list of glob patterns to exclude from the digest (e.g., `["*.pdf", "*.jpg", "*.csv"]`). When omitted, sensible defaults are used that exclude binary files, images, data files, ML model weights, lockfiles, etc.
    """
    try:
        # Filter out Swagger UI placeholder values
        token = request.token if request.token and request.token != "string" else None
        branch = request.branch if request.branch and request.branch != "string" else None
        exclude_patterns = request.exclude_patterns
        if exclude_patterns and exclude_patterns == ["string"]:
            exclude_patterns = None

        result = run_gitdigest(
            url=request.url,
            token=token,
            branch=branch,
            max_size=request.max_size if request.max_size else 10485760,
            word_count=request.word_count,
            call_llm_api=request.call_llm_api,
            exclude_patterns=exclude_patterns,
        )

        response_data = {
            "status": "success",
            "output_file": result["output_file"],
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
    """
    # Security: only allow .txt or .json files, no path traversal
    if not (filename.endswith(".txt") or filename.endswith(".json")) or ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, filename=filename)
