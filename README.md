# GitHub Repository Summariser

A FastAPI-based service that ingests GitHub repositories and optionally generates AI-powered summaries using configurable LLM providers (Doubleword, OpenAI, Nebius, or any OpenAI-compatible API).

**Effective date:** 2026-02-24

## Features

- **Repository Ingestion**: Clone any GitHub repo and extract its contents as a formatted digest
- **LLM Summarization**: Structured JSON output — summary, technologies list, and repo structure in one call
- **Digest Triage**: Automatically trims large digests to fit within the LLM context window by dropping lowest-signal files first
- **REST API**: Easy integration with web or mobile frontends
- **Configurable**: Branch, word count, file size limits, exclusion patterns, and more via `config.toml`

## Installation

These instructions assume only Python 3.12+ is installed on the machine.

### 1. Install UV (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Restart shell or run:
source $HOME/.cargo/env
```

### 2. Clone the repository

```bash
git clone https://github.com/NnamdiOdozi/GH_Summariser.git ~/projects/nebius_git_summariser
cd ~/projects/nebius_git_summariser
```

### 3. Install Python dependencies

```bash
uv sync
```

This installs all dependencies including `gitingest` (the repo cloning tool), `fastapi`, `uvicorn`, and others declared in `pyproject.toml`.

### 4. Create your secrets file

```bash
cp .env.claude.example .env.claude   # if an example exists, otherwise create manually
```

Add your API keys to `.env.claude`:

```env
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token
DOUBLEWORD_AUTH_TOKEN=your_doubleword_token
# OPENAI_API_KEY=your_openai_key         # only if using openai provider
# NEBIUS_API_KEY=your_nebius_key         # only if using nebius provider
```

Only the key for the active provider (set in `config.toml`) is required.

## Running the API

```bash
uv run python -m api.main
```

The API runs on `http://127.0.0.1:8001` (Swagger UI at `/docs`).

## CLI Usage

A command-line wrapper is available for quick local usage without starting the API server.

### First-time setup

Add the following function to your `~/.bashrc` (adjust `project_dir` to match your clone location):

```bash
# Run from anywhere: gitdigest -u <url> [-t token] [-b branch] [-w word_count] [-c] [-m max_size]
gitdigest() {
    local project_dir="$HOME/projects/nebius_git_summariser"

    if [ -f "$project_dir/.env.claude" ]; then
        set -a
        source "$project_dir/.env.claude"
        set +a
    fi

    export PYTHONPATH="$project_dir:$PYTHONPATH"
    uv run --project "$project_dir" python "$project_dir/app/main.py" "$@"
}
```

Reload your shell:

```bash
source ~/.bashrc
```

### CLI Examples

```bash
# Basic digest without LLM summary
gitdigest -u https://github.com/owner/repo

# With LLM summary (-c flag)
gitdigest -u https://github.com/owner/repo -c

# Specific branch and word count
gitdigest -u https://github.com/owner/repo -b dev -w 1000 -c

# Private repo with token
gitdigest -u https://github.com/owner/private-repo -t ghp_your_token -c
```

## Configuration

### Application Settings (`config.toml`)

All configurable settings live in `config.toml`. No Python code changes needed to adjust defaults.

```toml
[digest]
output_dir = "git_summaries"
max_summaries = 20           # keep only the N most recent digest pairs; older ones are deleted
default_word_count = 750
default_max_size = 10485760  # 10MB

[triage]
enabled = true
token_threshold = 100000     # trim digest if estimated tokens exceed this

[triage.layers]
docs            = true   # READMEs, CONTRIBUTING, CHANGELOG, docs/ folders
skills          = true   # files/folders with "skill" in name (agent instructions)
build_deps      = true   # pyproject.toml, package.json, Dockerfile, requirements.txt
entrypoints     = true   # main.py, app.py, server.ts, index.ts
config_surfaces = true   # files with "config" or "settings" in name, .env.example
domain_model    = true   # models/, schemas/, routes/, services/, controllers/
ci              = true   # .github/workflows/, deploy/
tests           = false  # test files — off by default (verbose, lower signal per token)

[logging]
level = "INFO"
log_dir = "logs"
log_file = "api.log"
max_log_bytes = 150000   # rotate at ~150KB (~1000 lines)
backup_count = 5         # keep api.log + 5 rotated files

[llm]
provider = "doubleword"  # "doubleword", "openai", or "nebius"
frequency_penalty = 0.3
timeout = 300

[llm.doubleword]
base_url = "https://api.doubleword.ai/v1"
model = "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"
auth_env = "DOUBLEWORD_AUTH_TOKEN"

[llm.openai]
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
auth_env = "OPENAI_API_KEY"

[llm.nebius]
base_url = "https://api.tokenfactory.nebius.com/v1/"
model = "MiniMaxAI/MiniMax-M2.1"
auth_env = "NEBIUS_API_KEY"
```

To add a new LLM provider, add a `[llm.your_provider]` section with `base_url`, `model`, and `auth_env`, then set `provider = "your_provider"` in `[llm]`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/gitdigest` | Ingest a repo and optionally summarize |
| GET | `/api/v1/gitdigest/{filename}` | Download a digest file |
| GET | `/api/v1/gitdigest/{filename}/preview` | Preview digest as formatted Markdown |
| GET | `/api/v1/prompt` | View the default summary prompt |
| GET | `/api/v1/health` | Health check |

## Example Request

```json
{
  "github_url": "https://github.com/NnamdiOdozi/mlx-digit-app",
  "max_size": 10485760,
  "word_count": 750,
  "call_llm_api": true
}
```

**Optional fields:**
- `token` — GitHub PAT, only needed for private repos
- `branch` — Override branch (case-sensitive). Omit to auto-detect from URL or use repo default
- `exclude_patterns` — Custom glob patterns (e.g., `["*.csv", "docs/*", "tests/*"]`). Added on top of built-in defaults
- `focus` — Short instruction to steer the summary (e.g., `"Focus on the authentication module"`)
- `triage` — `true` (default) trims digest to fit context window; `false` sends full digest as-is

## Example CURL Request

```bash
curl -X 'POST' \
  'http://localhost:8001/api/v1/gitdigest' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "github_url": "https://github.com/NnamdiOdozi/mlx-digit-app",
  "word_count": 750,
  "call_llm_api": true
}'
```

With branch and token (private repo, specific branch):

```bash
curl -X 'POST' \
  'http://localhost:8001/api/v1/gitdigest' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "github_url": "https://github.com/owner/repo",
  "token": "ghp_your_token_here",
  "branch": "dev",
  "call_llm_api": true
}'
```

## Output

When `call_llm_api: true` (default), the response has summary fields at the top, followed by metadata:

```json
{
  "status": "success",
  "summary": "## mlx-digit-app\n\nA Swift/Python app...",
  "technologies": ["Python", "Swift", "MLX", "FastAPI"],
  "structure": "Standard Python package layout with source in `app/`, Swift frontend in `ios/`.",
  "branch": "main",
  "output_file": "git_summaries/owner-repo.txt",
  "digest_stats": {
    "lines": 1523,
    "words": 5507,
    "estimated_tokens": 7159,
    "file_count": 22,
    "folder_count": 10
  }
}
```

When triage is applied (digest was too large), a `triage` block is included:

```json
{
  "triage": {
    "applied": true,
    "pre_triage_tokens": 285000,
    "post_triage_tokens": 94500,
    "files_dropped_count": 47
  }
}
```

When `call_llm_api: false`, `content` replaces the summary fields and contains the full raw digest text.

**Notes:**
- `estimated_tokens` uses `chars / 3.5` — more accurate for code than a word-count heuristic
- All output files are saved to `git_summaries/` (gitignored). The most recent 20 digest pairs are kept; older ones are deleted automatically
- `git_summaries/owner-repo.txt` — raw digest; `git_summaries/owner-repo_llm.json` — full result JSON

## Error Responses

Errors return a JSON body with `status: "error"` and an appropriate HTTP status code:

| Scenario | HTTP code | Example message |
|----------|-----------|-----------------|
| Invalid URL | 400 | `"Invalid GitHub URL: ..."` |
| Private repo, no token | 401 | `"Repository not accessible: owner/repo. If this is a private repo, provide a GitHub token via the 'token' field."` |
| Digest exceeds context window | 422 | `"Digest exceeds the model's context window. Try adding exclude_patterns or set triage=true."` |
| Unexpected error | 500 | `"gitingest failed: ..."` |

## Digest Triage

The triage system automatically trims digests that would exceed the LLM context window. It classifies files into signal tiers and drops lowest-signal files first, keeping the most useful content.

**Tier order (highest to lowest signal — lowest signal dropped first):**

| Tier | What it covers |
|------|---------------|
| docs | READMEs, CONTRIBUTING, CHANGELOG, docs/ folders |
| skills | Files/folders with "skill" in the path |
| build_deps | pyproject.toml, package.json, Dockerfile, requirements.txt |
| entrypoints | main.py, app.py, server.ts, index.ts, etc. |
| config_surfaces | Files with "config" or "settings" in name, .env.example |
| domain_model | models/, schemas/, routes/, services/, controllers/ |
| ci | .github/workflows/, deploy/ |
| tests | Test files (off by default — verbose, low signal) |
| other | Everything else |

The triage threshold (`token_threshold` in `config.toml`, default 100K) is conservative to work across the smallest provider context windows. Each tier can be toggled on/off in `[triage.layers]`.

## Branch Selection

You can specify a branch in two ways:

1. **Embed it in the URL** — e.g., `https://github.com/owner/repo/tree/dev`
2. **Use the `branch` field** — takes priority over any branch in the URL

If no branch is specified, the repo's default branch is used. Branch names are case-sensitive.

## Default File Exclusions

To keep digests focused on source code and reduce LLM token usage, the following are excluded by default. User-supplied `exclude_patterns` are **added on top** of these defaults (not instead of them).

| Category | Patterns |
|----------|----------|
| **Binary/media** | `**/*.pdf`, `**/*.jpg`, `**/*.jpeg`, `**/*.png`, `**/*.gif`, `**/*.bmp`, `**/*.svg`, `**/*.ico`, `**/*.webp`, `**/*.mp3`, `**/*.mp4`, `**/*.wav` |
| **Archives** | `**/*.zip`, `**/*.tar`, `**/*.gz`, `**/*.rar`, `**/*.7z` |
| **Executables/libs** | `**/*.exe`, `**/*.dll`, `**/*.so`, `**/*.bin` |
| **Data files** | `**/*.csv`, `**/*.dat`, `**/*.db`, `**/*.sqlite`, `**/*.xls`, `**/*.xlsx`, `**/*.parquet` |
| **Documents (binary)** | `**/*.docx`, `**/*.doc`, `**/*.pptx`, `**/*.ppt`, `**/*.odt`, `**/*.odp` |
| **ML model weights** | `**/*.pickle`, `**/*.pkl`, `**/*.h5`, `**/*.hdf5`, `**/*.npy`, `**/*.npz`, `**/*.pth`, `**/*.pt`, `**/*.onnx`, `**/*.tflite`, `**/*.weights` |
| **Lockfiles** | `**/*.lock`, `**/*lock.yaml`, `**/package-lock.json` |
| **Styles/minified** | `**/*.css`, `**/*.min.js`, `**/*.min.css`, `**/*.map` |
| **Build/cache output** | `**/dist/**`, `**/build/**`, `**/.next/**`, `**/.turbo/**`, `**/__pycache__/**`, `**/*.pyc` |
| **Data directories** | `**/data*/**` |
| **Package/venv dirs** | `**/node_modules/**`, `**/.venv/**`, `**/venv/**` |
| **Logs** | `**/*.log`, `**/logs/**` |
| **AI agent config** | `**/.claude/**`, `**/.gemini/**`, `**/.codex/**` |
| **Git internals** | `**/.git/**` |
| **i18n/translations** | `**/locales/**`, `**/translations/**` |

## Focus Prompts

By default, the LLM receives a general-purpose summarization prompt (see [`app/prompt.txt`](app/prompt.txt) or call `GET /api/v1/prompt`). Steer the summary with the `focus` field:

- "What does this system do at a high level?"
- "Where does execution start and how does control flow through the system?"
- "What are the core modules and how are they coupled?"
- "What are the most critical and risky parts of this codebase?"
- "What are the main data models and how does data flow?"
- "How do I run this locally?"
- "What external systems does this depend on?"
- "Focus on the authentication and security implementation"
- "Focus on the test coverage and CI/CD setup"

## Known Dependencies and Assumptions

### gitingest output format

The file count, folder count, and digest content are parsed from the raw text output of [gitingest](https://github.com/cyclotruc/gitingest). The parser relies on:

- The directory tree appearing at the top of the output, before a `================================================` separator (48 `=` characters)
- Files and folders denoted by `├──` and `└──` box-drawing characters
- Folders ending with `/`

If gitingest changes its output format in a future version, update the tree parser in `app/main.py` (search for `tree_separator`). The core digest and LLM summarization would still work — only `file_count` and `folder_count` would be affected.

## Context Window Limitations

This tool is designed for **small to medium-sized codebases**. The triage system helps, but extremely large repos may still exceed the context window after triage.

**Current provider context windows:**
- Doubleword (Qwen3 30B): ~262K tokens; triage threshold set to 100K (conservative)
- OpenAI gpt-4.1-mini: 1M tokens
- Nebius MiniMax-M2.1: large context, fast, cheapest option

### Options for Very Large Codebases

1. **Add exclusion patterns** — exclude `tests/*`, `docs/*`, `examples/*`, `fixtures/*` via `exclude_patterns`
2. **Use larger context models** — Gemini 1M+, Claude Opus/Sonnet 1M context; add as a new provider in `config.toml`
3. **Map-reduce summarization** — chunk the digest, summarize each chunk, aggregate the results (e.g., LangChain `MapReduceDocumentsChain`)
4. **Recursive Language Models (RLMs)** — give the LLM file exploration tools (bash, grep, find); sub-agents explore specific directories and report back to a parent agent
5. **RAG** — embed digest chunks in a vector database (Chroma, Pinecone, pgvector), query by question
6. **Page index** — build a searchable index with section references for targeted lookup rather than full summaries
