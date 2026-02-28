"""Post-ingest triage: parse digest, classify files by signal tier, trim to token budget."""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SEP = "=" * 48

# Tier order: highest signal first, lowest last
TIER_ORDER = ["docs_contract", "docs_narrative", "skills", "build_deps", "entrypoints",
              "config_surfaces", "domain_model", "ci", "tests", "other"]


def estimate_tokens(text: str) -> int:
    # chars / 3.5 is much more accurate for code than words * 1.3
    # (code has dense punctuation/symbols that inflate token counts vs prose)
    return int(len(text) / 3.5)


def parse_sections(digest: str) -> tuple[str, list[dict]]:
    """Split digest into (header, [{filename, content}, ...]).

    Uses a boundary-aware regex anchored on the double-separator + FILE: header pattern
    so that stray separator lines inside file content don't drift the parser.
    """
    digest = digest.replace("\r\n", "\n")  # normalise Windows line endings before regex match
    boundary = re.compile(r'(?m)^={48}$\nFILE: (.+)\n^={48}$\n?')
    matches = list(boundary.finditer(digest))
    if not matches:
        return digest.strip(), []
    header = digest[:matches[0].start()].strip()
    sections = []
    for i, m in enumerate(matches):
        filename = m.group(1).strip()
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(digest)
        sections.append({"filename": filename, "content": digest[content_start:content_end].strip()})
    return header, sections


def _file_tier(filepath: str, layers: dict) -> str:
    """Return the signal tier for a file path."""
    p = Path(filepath)
    name = p.name.lower()
    path_lower = filepath.lower()
    parts = [x.lower() for x in p.parts]

    def in_path(fragment: str) -> bool:
        # substring match — fine for most tiers but NOT for docs (would match "docker" → "doc")
        return any(fragment in part for part in parts)

    def in_path_exact(segment: str) -> bool:
        return segment in parts

    # Tier 1a: Contract docs — specs, schemas, ADRs, PRDs, OpenAPI (higher signal than narrative)
    if layers.get("docs_contract", True):
        if (in_path_exact("adr") or in_path_exact("adrs") or in_path_exact("specs") or
                any(x in name for x in ("openapi", "swagger", "asyncapi")) or
                any(name.startswith(x) for x in ("spec", "prd", "requirements", "schema"))):
            return "docs_contract"

    # Tier 1b: Narrative docs — READMEs, tutorials, CHANGELOG (uses exact segment match)
    if layers.get("docs_narrative", True):
        if (name.startswith("readme") or name.startswith("contributing") or
                name.startswith("changelog") or name.startswith("development") or
                in_path_exact("docs") or in_path_exact("doc")):
            return "docs_narrative"

    # Tier 2: Skills — agent instruction files and AI agent config dirs (high-signal, condensed)
    if layers.get("skills", True):
        if "skill" in path_lower:
            return "skills"
        if in_path(".claude") or in_path(".gemini") or in_path(".codex"):
            return "skills"

    # Tier 3: Build / dependency manifests
    if layers.get("build_deps", True):
        build_exact = {"pyproject.toml", "package.json", "makefile", "procfile",
                       "setup.py", "setup.cfg", "environment.yml", "cargo.toml",
                       "go.mod", "pom.xml", "build.gradle"}
        if name in build_exact:
            return "build_deps"
        if name.startswith("requirements") and name.endswith(".txt"):
            return "build_deps"
        if name.startswith("dockerfile") or name.startswith("docker-compose"):
            return "build_deps"

    # Tier 4: Entrypoints — where execution begins
    if layers.get("entrypoints", True):
        entrypoint_exact = {"main.py", "app.py", "server.py", "index.ts", "server.ts",
                            "wsgi.py", "asgi.py", "manage.py", "__main__.py",
                            "main.ts", "index.js", "app.ts", "main.js"}
        if name in entrypoint_exact:
            return "entrypoints"
        stem = p.stem.lower()
        if stem in ("main", "bootstrap", "factory", "entry", "app", "server"):
            if name.endswith((".py", ".ts", ".js")):
                return "entrypoints"

    # Tier 5: Config surfaces — anything with "config" or "settings" in name
    if layers.get("config_surfaces", True):
        if ("config" in name or "settings" in name or ".env." in name or
                name in (".env.example", ".env.sample", "application.yml",
                         "application.yaml", "appsettings.json")):
            return "config_surfaces"

    # Tier 6: Domain model — core business logic layers
    if layers.get("domain_model", True):
        domain_dirs = {"models", "schemas", "domain", "entities", "routes", "routers",
                       "services", "controllers", "handlers", "use_cases", "api"}
        if any(part in domain_dirs for part in parts[:-1]):
            return "domain_model"
        stem = p.stem.lower()
        if any(x in stem for x in ("model", "schema", "route", "router",
                                    "service", "controller", "handler")):
            if name.endswith((".py", ".ts", ".js")):
                return "domain_model"

    # Tier 7: CI / deploy
    if layers.get("ci", True):
        if in_path("workflows") or in_path(".github") or in_path("deploy"):
            return "ci"
        if name in ("procfile", "procfile.windows"):
            return "ci"

    # Tier 8: Tests (disabled by default — verbose, lower signal per token)
    if layers.get("tests", False):
        if (name.startswith("test_") or name.endswith("_test.py") or
                ".test." in name or ".spec." in name or
                in_path("tests") or in_path("__tests__")):
            return "tests"

    return "other"


def triage_digest(digest: str, triage_config: dict) -> dict:
    """
    Trim digest to fit within the token budget.

    Returns dict with:
        text              - trimmed (or original) digest text
        triage_applied    - bool
        pre_triage_tokens - token estimate before triage
        post_triage_tokens- token estimate after triage
        files_dropped     - list of dropped filenames (only when triage_applied)
    """
    threshold = triage_config.get("token_threshold", 200000)
    layers = triage_config.get("layers", {})

    pre_tokens = estimate_tokens(digest)

    if pre_tokens <= threshold:
        return {
            "text": digest,
            "triage_applied": False,
            "pre_triage_tokens": pre_tokens,
            "post_triage_tokens": pre_tokens,
            "files_dropped": [],
        }

    logger.info("Triage triggered: %d tokens > %d threshold", pre_tokens, threshold)

    header, sections = parse_sections(digest)
    tier_rank = {t: i for i, t in enumerate(TIER_ORDER)}

    # Classify every section
    scored = []
    for sec in sections:
        tier = _file_tier(sec["filename"], layers)
        scored.append({
            "filename": sec["filename"],
            "content": sec["content"],
            "tier": tier,
            "rank": tier_rank.get(tier, 99),
            "tokens": estimate_tokens(f"\n{SEP}\nFILE: {sec['filename']}\n{SEP}\n{sec['content']}"),
        })

    # Drop order: lowest priority tier first, then largest files first within tier
    drop_order = sorted(scored, key=lambda x: (-x["rank"], -x["tokens"]))

    keep_set = {s["filename"] for s in scored}
    files_dropped = []
    current_tokens = pre_tokens

    # Pass 1: drop everything except docs tiers (both contract and narrative)
    for item in drop_order:
        if current_tokens <= threshold:
            break
        if item["tier"] in {"docs_contract", "docs_narrative"}:
            continue
        keep_set.discard(item["filename"])
        files_dropped.append(item["filename"])
        current_tokens -= item["tokens"]

    # Pass 2: if still over, drop narrative docs first then contract docs (largest-first within each)
    if current_tokens > threshold:
        for doc_tier in ("docs_narrative", "docs_contract"):
            if current_tokens <= threshold:
                break
            logger.info("Triage pass 2: dropping %s to meet threshold", doc_tier)
            for item in sorted(scored, key=lambda x: -x["tokens"]):
                if current_tokens <= threshold:
                    break
                if item["filename"] not in keep_set or item["tier"] != doc_tier:
                    continue
                keep_set.discard(item["filename"])
                files_dropped.append(item["filename"])
                current_tokens -= item["tokens"]

    logger.info("Triage dropped %d files: %s%s",
                len(files_dropped),
                files_dropped[:3],
                " ..." if len(files_dropped) > 3 else "")

    # Rebuild digest preserving original file order
    kept = [s for s in sections if s["filename"] in keep_set]
    parts = [header]
    for sec in kept:
        parts.append(f"\n{SEP}\nFILE: {sec['filename']}\n{SEP}\n{sec['content']}")
    trimmed = "\n".join(parts)

    post_tokens = estimate_tokens(trimmed)
    effective_header = header  # may be replaced by truncated version in pass 3

    # Pass 3: truncate directory tree header if still over threshold
    if post_tokens > threshold:
        logger.info("Triage pass 3: truncating directory tree header to meet threshold")
        file_tokens = sum(s["tokens"] for s in kept)
        available_header_tokens = max(0, threshold - file_tokens)
        if available_header_tokens > 0:
            max_chars = int(available_header_tokens * 3.5)
            trunc = header[:max_chars]
            trunc = trunc[:trunc.rfind('\n')] if '\n' in trunc else trunc
            trunc += "\n[... directory tree truncated to fit context window ...]"
        else:
            trunc = "[directory tree omitted — file sections fill context window]"
        effective_header = trunc
        parts = [effective_header]
        for sec in kept:
            parts.append(f"\n{SEP}\nFILE: {sec['filename']}\n{SEP}\n{sec['content']}")
        trimmed = "\n".join(parts)
        post_tokens = estimate_tokens(trimmed)

    # Pass 4: hard guard — if still over threshold (e.g. tokenizer variance), drop largest remaining files
    if post_tokens > threshold:
        logger.warning("Triage pass 4: still over threshold (%d > %d), force-dropping largest files",
                       post_tokens, threshold)
        kept_scored = sorted(kept, key=lambda s: -estimate_tokens(
            f"\n{SEP}\nFILE: {s['filename']}\n{SEP}\n{s['content']}"))
        for sec in kept_scored:
            if post_tokens <= threshold:
                break
            sec_tokens = estimate_tokens(f"\n{SEP}\nFILE: {sec['filename']}\n{SEP}\n{sec['content']}")
            kept = [k for k in kept if k["filename"] != sec["filename"]]
            files_dropped.append(sec["filename"])
            post_tokens -= sec_tokens
        parts = [effective_header]
        for sec in kept:
            parts.append(f"\n{SEP}\nFILE: {sec['filename']}\n{SEP}\n{sec['content']}")
        trimmed = "\n".join(parts)
        post_tokens = estimate_tokens(trimmed)

    logger.info("Triage: %d → %d tokens", pre_tokens, post_tokens)

    return {
        "text": trimmed,
        "triage_applied": True,
        "pre_triage_tokens": pre_tokens,
        "post_triage_tokens": post_tokens,
        "files_dropped": files_dropped,
    }
