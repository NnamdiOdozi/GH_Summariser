# GitHub Repository Summariser

A FastAPI-based service that ingests GitHub repositories and optionally generates AI-powered summaries using configurable LLM providers (Doubleword, OpenAI, or any OpenAI-compatible API).

## Features

- **Repository Ingestion**: Clone any GitHub repo and extract its contents as a formatted digest
- **LLM Summarization**: Generate concise summaries using configurable LLM providers (Doubleword, OpenAI, etc.)
- **REST API**: Easy integration with web or mobile frontends
- **Configurable**: Specify branch, word count, file size limits, and more

## Installation

```bash
# Install dependencies
uv sync

# Install gitingest CLI (required on server)
pip install gitingest
```

## Configuration

### LLM Provider (`config.toml`)

The LLM provider is configured in `config.toml`. Switch between providers by changing the `provider` field:

```toml
[llm]
provider = "doubleword"  # or "openai"
frequency_penalty = 0.3

[llm.doubleword]
base_url = "https://api.doubleword.ai/v1"
model = "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"
auth_env = "DOUBLEWORD_AUTH_TOKEN"

[llm.openai]
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
auth_env = "OPENAI_API_KEY"
```

Both providers use the standard OpenAI-compatible `/chat/completions` endpoint. To add a new provider, add a section under `[llm.your_provider]` with `base_url`, `model`, and `auth_env`.

### API Keys (`.env.claude`)

Create a `.env.claude` file with:

```env
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token
DOUBLEWORD_AUTH_TOKEN=your_doubleword_token
OPENAI_API_KEY=your_openai_key
```

Only the key for the active provider (set in `config.toml`) is required.

## Running the API

```bash
uv run python -m api.main
```

The API runs on `http://127.0.0.1:8001` (Swagger UI at `/docs`).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/gitdigest` | Ingest a repo and optionally summarize |
| GET | `/api/v1/gitdigest/{filename}` | Download a digest file |
| GET | `/api/v1/prompt` | View the default summary prompt |
| GET | `/api/v1/health` | Health check |

## Branch Selection

You can specify a branch in two ways:

1. **Embed it in the URL** — e.g., `https://github.com/owner/repo/tree/dev` or `https://github.com/owner/repo/tree/feature/my-branch` (branch names with slashes are supported)
2. **Use the branch parameter** — set `branch` in the API request body or `-b` on the CLI. This overrides any branch in the URL.

If no branch is specified (either way), the repo's default branch is used.

**Note:** Branch names are case-sensitive (e.g., `Tuong` and `tuong` are different branches).

## Default File Exclusions

To keep digests focused on source code and reduce LLM token usage, the following file types are excluded by default:

| Category | Patterns |
|----------|----------|
| **Binary/media** | `*.pdf`, `*.jpg`, `*.jpeg`, `*.png`, `*.gif`, `*.bmp`, `*.svg`, `*.ico`, `*.webp`, `*.avif`, `*.jfif`, `*.tiff`, `*.tif`, `*.heic`, `*.psd`, `*.mp3`, `*.mp4`, `*.wav` |
| **Archives** | `*.zip`, `*.tar`, `*.gz`, `*.rar`, `*.7z` |
| **Executables/libs** | `*.exe`, `*.dll`, `*.so`, `*.bin` |
| **Data files** | `*.csv`, `*.dat`, `*.db`, `*.sqlite`, `*.xls`, `*.xlsx`, `*.parquet` |
| **Documents (binary)** | `*.docx`, `*.doc`, `*.pptx`, `*.ppt`, `*.odt`, `*.odp` |
| **ML model weights** | `*.pickle`, `*.pkl`, `*.h5`, `*.hdf5`, `*.npy`, `*.npz`, `*.pth`, `*.pt`, `*.onnx`, `*.tflite`, `*.weights` |
| **Lockfiles** | `*.lock` (uv.lock, package-lock.json, etc.) |
| **Data directories** | `data/*` |

**Why?** Binary files, model weights, and data directories can add thousands of lines to a digest without providing useful information for code summarization. Lockfiles list pinned dependency versions that add bulk without insight. Excluding these by default typically reduces digest size by 50-80%.

You can override the defaults via the API (`exclude_patterns` field) or CLI (`-e` flag):

```bash
# CLI: exclude only specific patterns (overrides defaults)
gitdigest -u https://github.com/owner/repo -e "*.csv" -e "*.log"
```

## Example Request

```json
{
  "url": "https://github.com/NnamdiOdozi/mlx-digit-app",
  "max_size": 10485760,
  "word_count": 750,
  "call_llm_api": true
}
```

**Optional fields:**
- `token` — GitHub PAT, only needed for private repos
- `branch` — Override branch (case-sensitive). Omit to auto-detect from URL or use repo default
- `exclude_patterns` — Custom glob patterns for files or directories (e.g., `["*.csv", "docs/*", "tests/*"]`). When omitted or `null`, the built-in defaults above are used
- `focus` — Short instruction to steer the summary towards a specific area (e.g., `"Focus on the authentication module"`)

## Example CURL request

```bash
curl -X 'POST' \
  'http://localhost:8001/api/v1/gitdigest' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "url": "https://github.com/NnamdiOdozi/mlx-digit-app",
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
  "url": "https://github.com/owner/repo",
  "token": "ghp_your_token_here",
  "branch": "dev",
  "call_llm_api": true
}'
```

## Output

Every response includes **digest stats** showing the size of the raw repository digest:

```json
"digest_stats": {
  "lines": 1523,
  "words": 5507,
  "estimated_tokens": 7159
}
```

This is useful for estimating LLM costs and checking whether the digest fits within a model's context window. The token estimate uses a `words × 1.3` heuristic.

The rest of the response depends on whether LLM summarization is enabled:

- **`call_llm_api: true`** (default) — Returns a clean, structured summary generated by the configured LLM provider. The raw digest is still saved to disk but only the summary is returned in the response.
- **`call_llm_api: false`** — Returns the full raw repository digest content directly, so you can inspect exactly what gitingest extracted or pipe it into your own processing.

All output files are saved to the `git_summaries/` directory to keep the project root clean:
- `git_summaries/owner-repo.txt` — Raw repository digest
- `git_summaries/owner-repo_llm.json` — JSON with digest + LLM summary (only when LLM is called)

This directory is gitignored since these are generated outputs.

## Focus Prompts

By default, the LLM receives a general-purpose summarization prompt (see [`app/prompt.txt`](app/prompt.txt) or call `GET /api/v1/prompt` to view it). You can steer the summary towards a specific area by providing a `focus` instruction. Examples:

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

## Future Development

### Handling large codebases (map-reduce summarization)

The current approach sends the entire gitingest digest to the LLM in a single request. This works well for small-to-medium repositories, but large codebases can produce digests that exceed the LLM's context window.

A proven approach to handle this is **map-reduce summarization**:

1. **Map phase** — Split the raw digest (`.txt` file) into chunks that fit within the LLM context limit. Send each chunk individually to the LLM for summarization.
2. **Reduce phase** — Aggregate the per-chunk summaries and send them to the LLM with an instruction to produce a single cohesive summary of the entire repository.

This pattern is well-established in LLM pipelines (e.g., LangChain's `MapReduceDocumentsChain`) and would allow the tool to handle repositories of any size without hitting context limits.

Other approaches that could be used include:

- **Vector database** — Embed chunks of the digest into a vector store and use retrieval-augmented generation (RAG) to answer targeted questions
- **Git Nexus**
- **RLM (Recursive Language Model)** 
- **Page index** — Build a searchable index of the digest with page/section references for on-demand lookup
