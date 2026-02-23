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

### Application Settings (`config.toml`)

All configurable settings live in `config.toml`. No Python code changes needed to adjust defaults.

```toml
[digest]
output_dir = "git_summaries"
default_word_count = 750
default_max_size = 10485760  # 10MB
default_exclude_patterns = [
    "*.pdf", "*.csv", "*.jpg", "*.jpeg", "*.png", "*.gif",
    # ... see config.toml for full list
]

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

[llm.nebius]
base_url = "https://api.tokenfactory.nebius.com/v1/"
model = "MiniMaxAI/MiniMax-M2.1" # fallback; overridden by OPENAI_MODEL env var if set
model_env = "NEBIUS_MODEL"
auth_env = "NEBIUS_API_KEY"
```

The `[digest]` section controls output directory, default word count, max file size, and exclusion patterns. The `[llm]` section controls the LLM provider. Both providers use the standard OpenAI-compatible `/chat/completions` endpoint. To add a new provider, add a section under `[llm.your_provider]` with `base_url`, `model`, and `auth_env`.

### API Keys (`.env.claude`)

Create a `.env.claude` file with:

```env
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token
DOUBLEWORD_AUTH_TOKEN=your_doubleword_token
OPENAI_API_KEY=your_openai_key
NEBIUS_API_KEY=your_nebius_key
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

1. Clone the repository:
   ```bash
   git clone https://github.com/NnamdiOdozi/GH_Summariser.git ~/projects/GH_Summariser
   ```

2. Install dependencies:
   ```bash
   cd ~/projects/nebius_git_summariser
   uv sync
   ```

3. Add the following function to your `~/.bashrc` (adjust `project_dir` to match your clone location):
   ```bash
   # Run from anywhere: gitdigest -u <url> [-t token] [-b branch] [-w word_count] [-c] [-m max_size]
   gitdigest() {
       local project_dir="$HOME/projects/GH_Summariser"

       # Load env vars from project
       if [ -f "$project_dir/.env.claude" ]; then
           set -a
           source "$project_dir/.env.claude"
           set +a
       fi

       # Add project to PYTHONPATH to avoid import warnings
       export PYTHONPATH="$project_dir:$PYTHONPATH"

       # Run CLI from current directory (no cd needed - runs where you call from)
       uv run --project "$project_dir" python "$project_dir/app/main.py" "$@"
   }
   ```

4. Reload your shell:
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

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/gitdigest` | Ingest a repo and optionally summarize |
| GET | `/api/v1/gitdigest/{filename}` | Download a digest file |
| GET | `/api/v1/gitdigest/{filename}/preview` | Preview digest as formatted Markdown |
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
| **Package/venv dirs** | `node_modules/*`, `.venv/*`, `venv/*` |

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

Every response includes the following metadata:

```json
{
  "status": "success",
  "branch": "main",
  "digest_stats": {
    "lines": 1523,
    "words": 5507,
    "estimated_tokens": 7159,
    "file_count": 22,
    "folder_count": 10
  },
  "directory_tree": "Directory structure:\n└── repo-name/\n    ├── README.md\n    ..."
}
```

- **`branch`** — The branch that was ingested
- **`digest_stats`** — Line/word/token counts plus file and folder counts, useful for estimating LLM costs and checking context window fit. The token estimate uses a `words × 1.3` heuristic.
- **`directory_tree`** — The full directory tree extracted from the gitingest output

The rest of the response depends on whether LLM summarization is enabled:

- **`call_llm_api: true`** (default) — Returns a clean, structured summary generated by the configured LLM provider. The summary focuses on what the code does, key features, how to run it, tech stack, quality signals, and unknowns. The directory tree and file counts are provided separately so the LLM doesn't waste tokens reproducing them.
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

## Known Dependencies and Assumptions

### gitingest output format

The directory tree, file count, and folder count in the API response are parsed from the raw text output of [gitingest](https://github.com/cyclotruc/gitingest). Specifically, the parser relies on:

- The directory tree appearing at the top of the output, before a `================================================` separator
- Files and folders being denoted by `├──` and `└──` box-drawing characters
- Folders ending with `/`

If gitingest changes its output format in a future version, the tree extraction and file/folder counting will need to be updated. The core digest and LLM summarization would still work — only the parsed metadata fields (`directory_tree`, `file_count`, `folder_count`) would be affected.

## Context Window Limitations

This tool is designed for **small to medium-sized codebases**. The current implementation sends the entire repository digest to the LLM in a single request, which works well when the digest fits within the model's context window.

**Current provider limits:**
- Doubleword and OpenAI models used by this tool typically have context windows of less than 200,000 tokens
- A repository digest with ~150K words would produce roughly 195K tokens (using the 1.3x multiplier)

The `digest_stats.estimated_tokens` field in the API response tells you whether your digest will fit. If it exceeds your model's context limit, the LLM call will fail or produce truncated results.

### Options for Larger Codebases

If you need to summarize repositories that exceed the context window, consider these approaches:

1. **Use larger context models**
   - Google Gemini models offer up to 1M+ token context windows
   - Claude Opus 4.6 and Sonnet 4.6 (currently in beta) support 1M token contexts
   - Configure via `config.toml` by adding a new provider section with the appropriate base URL and model

2. **Add exclusion patterns**
   - Exclude large directories that aren't essential for understanding the codebase
   - Use the `exclude_patterns` API parameter: `["tests/*", "docs/*", "examples/*", "fixtures/*"]`
   - Excluding test files, documentation, and example directories can significantly reduce digest size

3. **Map-reduce summarization**
   - Split the digest into chunks that fit within the context limit
   - **Map phase**: Send each chunk individually to the LLM for summarization
   - **Reduce phase**: Aggregate the per-chunk summaries and produce a cohesive final summary
   - This pattern is well-established in LLM pipelines (e.g., LangChain's `MapReduceDocumentsChain`)

4. **Recursive Language Models (RLMs)**
   - Give the LLM access to file exploration tools (bash, grep, ripgrep, find)
   - The agent recursively calls sub-LLMs to explore and summarize different parts of the codebase
   - Eg each sub-agent focuses on a specific directory or module, reporting findings back to a parent agent
   - Achieves good accuracy and performance on large codebases without loading everything into context at once

5. **RAG (Retrieval-Augmented Generation)**
   - Embed chunks of the digest into a vector database
   - Query the vector store with specific questions and retrieve relevant context
   - Send only the relevant chunks to the LLM with your question
   - Tools: Chroma, Pinecone, Weaviate, or pgvector

6. **Page index / searchable index**
   - Build a searchable index of the digest with section references
   - Enable on-demand lookup of specific modules or files
   - Useful when you need to answer targeted questions rather than generate a full summary
