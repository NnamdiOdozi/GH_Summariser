# GitHub Repository Summariser

A FastAPI-based service that ingests GitHub repositories and optionally generates AI-powered summaries using configurable LLM providers (Doubleword, OpenAI, Nebius, or any OpenAI-compatible API).

**Effective date:** 2026-02-24

## Features

- **Repository Ingestion**: Clone any GitHub repo and extract its contents as a formatted digest using third-party Gitingest tool
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
DOUBLEWORD_AUTH_TOKEN=your_doubleword_token
OPENAI_API_KEY=your_openai_key         # only if using openai provider
NEBIUS_API_KEY=your_nebius_key         # only if using nebius provider
```

Only the key for the active provider (set in `config.toml`) is required.

## Running the API

```bash
uv run python -m api.main
```

The API runs on `http://127.0.0.1:8001` (Swagger UI at `/docs`).

## Configuration

### Application Settings (`config.toml`)

All configurable settings live in `config.toml`. No Python code changes needed to adjust defaults. The sections in the config file are digest, triage, triage.layers, logging, llm and llm.provider

To add a new LLM provider, add a `[llm.your_provider]` section with `base_url`, `model`, and `auth_env`, then set `provider = "your_provider"` in `[llm]`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/summarize` | Ingest a repo and optionally summarize |
| GET | `/api/v1/summarize/{filename}` | Download a digest file |
| GET | `/api/v1/summarize/{filename}/preview` | Preview digest as formatted Markdown |
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

With branch and token (private repo, specific branch):

```bash
curl -X 'POST' \
  'http://localhost:8001/api/v1/summarize' \
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

A `triage` block is always present (see [Approach to Handling Repository Contents](#approach-to-handling-repository-contents) for details).

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

## Approach to Handling Repository Contents

Getting the right content into the LLM is the core challenge of this tool. Too much and you exceed the context window; too little and the summary is shallow. The solution is three sequential layers of content control, each configurable independently.

### Layer 1 — Standard Default Exclusions

Before anything is sent anywhere, gitingest filters out files that have no value for code understanding. These are excluded by default for every request:

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
| **Git internals** | `**/.git/**` |
| **i18n/translations** | `**/locales/**`, `**/translations/**` |

**Why?** Binary files, model weights, and data directories add bulk without providing code understanding. Lockfiles list pinned dependency versions with no architectural signal. Build output and caches duplicate what's already in source. Excluding these typically reduces digest size by 50–80% with no loss of useful information.

Note that `.claude/`, `.gemini/`, and `.codex/` agent config directories are **intentionally not excluded** here. They frequently contain skills files and project instructions that are high-signal content. They are instead classified into the `skills` tier in Layer 3 (triage), keeping them protected until the very last resort.

### Layer 2 — User-Supplied Exclusion Patterns

After the defaults, callers can add their own exclusions via the `exclude_patterns` field. These are **additive** — they extend the defaults, not replace them. This is intentional: there is no way to accidentally remove a sensible default by specifying your own patterns.

```json
{
  "github_url": "https://github.com/owner/large-repo",
  "exclude_patterns": ["tests/*", "docs/*", "examples/*", "fixtures/*"]
}
```

This layer is useful for known-noisy directories specific to a given repo — large test suites, generated documentation, or fixture data that wasn't caught by Layer 1.

### Layer 3 — Automatic Triage

Even after layers 1 and 2, some repos produce digests too large for the LLM context window (large monorepos, repos with many source files). The triage system handles this automatically when `triage: true` (the default).

**How it works:** Files in the digest are classified into signal tiers based on their path and name. When the estimated token count exceeds `token_threshold` (default: 100K), the lowest-signal files are dropped first — largest files in the lowest tier first — until the digest fits. If the digest still exceeds the threshold after dropping all other tiers, even documentation is trimmed (largest files first) as a last resort.

**Tier order (highest to lowest signal — lowest dropped first):**

| Tier | What it covers |
|------|---------------|
| docs_contract | API specs (OpenAPI, AsyncAPI), ADRs, PRDs, requirements, schema files — kept until last resort |
| docs_narrative | READMEs, CONTRIBUTING, CHANGELOG, docs/ folders — dropped before contract docs under pressure |
| skills | Files/folders with "skill" in the path; also `.claude/`, `.gemini/`, `.codex/` agent config dirs |
| build_deps | pyproject.toml, package.json, Dockerfile, requirements.txt |
| entrypoints | main.py, app.py, server.ts, index.ts, etc. |
| config_surfaces | Files with "config" or "settings" in name, .env.example |
| domain_model | models/, schemas/, routes/, services/, controllers/ |
| ci | .github/workflows/, deploy/ |
| tests | Test files — off by default (verbose, lower signal per token) |
| other | Everything else |

Each tier can be toggled on/off in `[triage.layers]` in `config.toml`. The `token_threshold` is set conservatively at 100K to work across the smallest provider context windows. To use more of a larger model's context window, raise `token_threshold` to match — for example, 256000 for Nebius Kimi-K2.5 or 1000000 (but note that prcatical limits may be far lower than context window due to rate limits that depend on service tier) for OpenAI gpt-4.1-mini.

**Token estimation:** Token count is estimated locally using `chars ÷ 3.5`. This is a good approximation for mixed code/prose and, crucially, requires no network call to a remote tokenizer — keeping triage fast and self-contained. Adjust `token_threshold` in `config.toml` to tune how aggressively the digest is trimmed.

The response always includes a `triage` block so you can see what happened:

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

When `applied` is `false`, `pre_triage_tokens` and `post_triage_tokens` will be equal and `files_dropped_count` will be 0.

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

## Tested Scenarios

### Private repositories

Tested with private GitHub repositories using a PAT. Pass a token with `repo` scope via the `token` field (API) or `-t` flag (CLI). Without a valid token the API returns a 401 with a clear error message.

### Codebase scale — observed triage behaviour

Tested across three repo sizes. Token counts estimated via `chars ÷ 3.5`.

| Repo | Size | Pre-triage tokens | Post-triage tokens | Files dropped | Notes |
|------|------|------------------:|-------------------:|--------------:|-------|
| NnamdiOdozi/mlx-digit-app | Small | 12,559 | 12,559 | 0 | Under threshold; triage not triggered |
| Azure-Samples/python-agentframework-demos | Medium | 200,559 | 98,604 | 12 | At 100K threshold |
| babel/babel | Large monorepo | 4,179,344 | 178,007 | 10,000 | At 178K threshold; header truncation (pass 3) also fired |

For Babel, even after dropping all 10,000 non-doc files the directory tree header alone was ~202K tokens (gitingest lists every path). Pass 3 truncated the header to fit. At 100K threshold, Babel trims to ~99K with ~10,000+ files dropped.

- Setting `token_threshold` higher allows significantly more of the codebase through — e.g. 178K for Nebius MiniMax, 240K for Doubleword
- Adding `exclude_patterns` such as `["packages/*/test/**", "packages/*/fixtures/**"]` reduces pre-triage count before triage runs

### Specific branches

The `branch` field has been tested with non-default branches. Pass the exact branch name (case-sensitive). If the branch name appears in the GitHub URL (e.g. `/tree/dev`), it can also be auto-detected from the URL.

## Known Dependencies and Assumptions

### gitingest output format

The file count, folder count, and digest content are parsed from the raw text output of [gitingest](https://github.com/cyclotruc/gitingest). The parser relies on:

- The directory tree appearing at the top of the output, before a `================================================` separator (48 `=` characters)
- Files and folders denoted by `├──` and `└──` box-drawing characters
- Folders ending with `/`

If gitingest changes its output format in a future version, update the tree parser in `app/main.py` (search for `tree_separator`). The core digest and LLM summarization would still work — only `file_count` and `folder_count` would be affected.

**On model selection:** We initially expected the ranking to follow: (1) context window size — more context means fewer files dropped; (2) code understanding capability; (3) cost. In practice, instruction-following, output consistency, and synthesis quality proved more decisive. All five models were tested on identical input (same repo, same 100K token budget, `response_format=json_schema`) on 2026-02-24. Rankings were revised on 2026-02-25 after follow-up tests on three repos spanning small (12K tokens, no triage), medium (4.2M tokens, triaged to 100K), and large (13.5M tokens, triaged to 100K).

1. **OpenAI gpt-4.1-mini** (1M context, but see rate limit caveat below) — 100K comparison: 24s, 13 techs, 850 words, clean. Large repo follow-up: consistently 456–703 words even after heavy triage (8,944–10,000 files dropped). Best synthesis quality from high-signal-but-narrow post-triage content. Best overall choice.
2. **Doubleword Qwen3-30B** (262K context) — 100K comparison: 20s, 17 techs, 884 words, zero non-Latin bleed. Fastest response times and excellent on small/medium repos. On very large repos requiring extreme triage it writes thinner output (139–263 words where OpenAI writes 456–703) — likely a synthesis limitation rather than context pressure. Good second choice, especially for latency-sensitive use.
3. **Nebius MiniMax-M2.1** (196K context) — 38s, 22 techs, 816 words. Good quality at scale with `max_output_tokens=8000`; occasional non-Latin reasoning bleed under higher word count pressure.
4. **Nebius GLM-4.7-FP8** (200K context) — Valid JSON on small repos but thin output at 100K (124 words, 4 techs) and null content above 153K tokens. Degrades sharply with context size.
5. **Nebius Kimi-K2.5** (256K context) — Multiple issues: wildly variable latency (36s–209s on identical input), JSON validity failures with `json_object` mode, tendency to generate 3800+ word summaries ignoring the word count instruction, and non-Latin character bleed. Unreliable for production use.

**On `response_format`:** `json_schema` is significantly better than `json_object` for all Nebius reasoning models. With `json_object`, MiniMax leaked Chinese chain-of-thought into the summary field at higher word counts; `json_schema` largely eliminates this by giving the model an explicit field scaffold. GLM, which produced invalid JSON with `json_object`, produces valid (if thin) JSON with `json_schema` on smaller inputs. All three Nebius models are reasoning models that share their output token budget between chain-of-thought and response — `max_output_tokens = 8000` is required in config to avoid null responses.

### Options for Very Large Codebases

1. **Add exclusion patterns** — exclude `tests/*`, `docs/*`, `examples/*`, `fixtures/*` via `exclude_patterns`
2. **Use larger context models** — Gemini 1M+, Claude Opus/Sonnet 1M context; add as a new provider in `config.toml`
3. **Map-reduce summarization** — chunk the digest, summarize each chunk, aggregate the results (e.g., LangChain `MapReduceDocumentsChain`)
4. **Recursive Language Models (RLMs)** — give the LLM file exploration tools (bash, grep, find); sub-agents explore specific directories and report back to a parent agent
5. **RAG** — embed digest chunks in a vector database (Chroma, Pinecone, pgvector), query by question
6. **Page index** — build a searchable index with section references for targeted lookup rather than full summaries
7. **Agentic search** — using a single or multi-agent system to search through the codebase digest

---

## Appendix: CLI Usage

A command-line wrapper is available for quick local usage without starting the API server. This is peripheral to the main use case (REST API) but useful for one-off local runs.

### Setup

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

Reload your shell: `source ~/.bashrc`

### Examples

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
