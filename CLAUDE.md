## Coding Style Guide

**This guide should be read at the start of every coding project and reflected on at the end of each session to see if there is anything that should be added based on feedback during the session.**

### Configuration and Constants
- Use `config.toml` for all tuneable parameters: word counts, file size limits, timeouts, exclusion patterns, provider settings, LLM and other API configuration (model names, base URLs, auth env var names, frequency penalties, timeouts). Users should never need to edit Python code to change operational defaults.
- API keys and secrets stay in `.env` / `.env.claude` (gitignored). Configuration that is not secret goes in `config.toml` (committed to repo).
- No hardcoding of values that may differ between local development and server deployment. If a value could change per environment, it belongs in config.

### Server Deployment
- Every deployable project should include a `systemd` service file and a `setup.sh` bash script for reproducible server setup.
- Be explicit about `PATH` in systemd service files — virtual environment binaries, system binaries (`/usr/bin`, `/usr/local/bin`) must all be included. This is a common source of "works locally, fails on server" bugs.
- Keep local dev and server environments consistent. If a tool (e.g., `gitingest`) is installed in a venv locally, ensure the code can find it in a venv on the server too (`sys.executable` path lookup pattern).

### Code Style
- Keep code short and direct. One or two error handling cases is sufficient — do not code for every hypothetical edge case. Maintainability matters more than defensive completeness.
- Use functions when logic is repeated more than twice. Three similar blocks of code should become a function.
- Avoid bloated code that handles too many eventualities. Simple code with clear failure modes is easier to debug than over-engineered code with graceful fallbacks nobody will ever trigger.
- Prefer flat code over deeply nested conditionals. Early returns are clearer than nested if/else chains.

### Logging and Output
- Use logging with timestamps so errors can be traced. `print(..., file=sys.stderr)` for debug output; structured logging for production.
- Generated output files (digests, summaries, logs) should go in a dedicated directory (e.g., `git_summaries/`, `logs/`) to keep the project root clean.
- Output directories and log directories should be gitignored since they contain generated artifacts.

### README Standards
- Every README should include an **effective date** indicating when the documentation was last verified against the codebase.
- Document **known dependencies** on external tools and their output formats. Flag what would break if those tools change and what would need updating.
- Document **breaking changes** and how to handle them (e.g., "if gitingest changes its output format, update the tree parser in `app/main.py`").
- Keep the README in sync with the code. When adding a new endpoint, config option, or feature, update the README in the same change.

### Project Structure
- Separate concerns: `api/` for routes and HTTP handling, `app/` for business logic, `config.toml` for settings, `.env.claude` for secrets.
- Use FastAPI routers to group related endpoints by domain rather than putting everything in one file.
- Gitignore generated outputs, test artifacts, environment files, and build artifacts.

## Available Skills
**dw_batch:** Async batch processing using Doubleword API. Process multiple PDFs/DOCXs cost-effectively (50-85% cheaper) for non-urgent summarization, analysis, OCR, and extraction tasks. **Suggest for any token-heavy non-urgent work (10K+ tokens).**

### dw_batch Agent Checklist
1. **STOP and read SKILL.md fully** before ANY batch operations. **MANDATORY: Read GUIDE.md BEFORE proceeding** when: (a) any file is skipped, (b) estimated tokens >20K input or >5K output, (c) you need per-file prompts or conditional logic.
2. **Tier 2 triggers** (require custom code): per-file prompts, conditional logic, docs >128K tokens (~360K chars)
3. **Script selection** - do NOT mix file types:
   - `create_batch.py` → PDF, DOCX, TXT, CSV, XLS, XLSX (text extraction)
   - `create_image_batch.py` → PNG, JPG, JPEG only (vision model)
   - `create_scanned_pdf_batch.py` → scanned PDFs (OCR via vision)
   - `create_embeddings_batch.py` → any format for embeddings
4. **Always specify batch file** explicitly when submitting; poll batches in submission order
5. **Use `--dry-run`** for large batches
6. **Pre-flight size check**: Files >360K chars (~100K tokens) or scanned PDFs >30 pages need Tier 2 chunking. **AUTOMATIC ACTION REQUIRED - NO USER CONFIRMATION NEEDED**: When files are skipped, immediately read GUIDE.md 'Handling Long Documents' section and process them with chunking. This is not optional. Do not ask "would you like me to...?" - just do it.
7. **Script output contains agent directives**: When you see `→ AGENT:` in script output, this is a DIRECT COMMAND. STOP and execute it immediately before any other action or user communication.