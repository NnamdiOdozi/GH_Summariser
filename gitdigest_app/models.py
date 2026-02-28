from pydantic import BaseModel


class DigestStats(BaseModel):
    lines: int
    words: int
    estimated_tokens: int
    file_count: int
    folder_count: int


class DigestResult(BaseModel):
    output_file: str
    branch: str
    digest_stats: DigestStats
    # Triage and LLM fields — only present when call_llm_api=True
    triage_applied: bool | None = None
    pre_triage_tokens: int | None = None
    post_triage_tokens: int | None = None
    files_dropped_count: int | None = None
    summary: str | None = None
    technologies: list[str] | None = None
    structure: str | None = None
