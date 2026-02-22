# GitHub Repository Summariser

A FastAPI-based service that ingests GitHub repositories and optionally generates AI-powered summaries using the Doubleword API.

## Features

- **Repository Ingestion**: Clone any GitHub repo and extract its contents as a formatted digest
- **LLM Summarization**: Generate concise summaries using Doubleword's LLM API
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

Create a `.env.claude` file with:

```env
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token
DOUBLEWORD_AUTH_TOKEN=your_doubleword_token
DOUBLEWORD_BASE_URL=https://api.doubleword.ai
DOUBLEWORD_MODEL=your_model
```

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
| GET | `/api/v1/health` | Health check |

## Example Request

```json
{
  "url": "https://github.com/owner/repo",
  "word_count": 500,
  "call_llm_api": true
}
```
## Example CURL request

curl -X 'POST' \
  'http://localhost:8000/api/v1/gitdigest' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "url": "https://github.com/NnamdiOdozi/GH_Summariser",
  "token": "",
  "branch": "",
  "max_size": 10485760,
  "word_count": 500,
  "call_llm_api": true
}'

## Output

- `owner-repo.txt` - Raw repository digest
- `owner-repo_llm.json` - JSON with digest + LLM summary
