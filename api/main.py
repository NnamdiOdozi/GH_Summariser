# api/main.py
import logging
import os
import re
import tomllib
from logging.handlers import RotatingFileHandler

_TOKEN_PATTERNS = [
    re.compile(r'("token"\s*:\s*")[^"]+(")', re.IGNORECASE),
    re.compile(r"(token=)[^&\s]+", re.IGNORECASE),
]

class _RedactTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat in _TOKEN_PATTERNS:
            msg = pat.sub(r"\1[REDACTED]\2", msg)
        record.msg = msg
        record.args = ()
        return True

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# Import the router objects directly
from api.routes.gitdigest import router as gitdigest_router

# --- Logging setup (reads from config.toml) ---
_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.toml")
with open(_config_path, "rb") as _f:
    _config = tomllib.load(_f)

_log_cfg = _config.get("logging", {})
_log_dir = _log_cfg.get("log_dir", "logs")
_log_file = _log_cfg.get("log_file", "api.log")
_log_level = _log_cfg.get("level", "INFO")

os.makedirs(_log_dir, exist_ok=True)

_max_bytes = _log_cfg.get("max_log_bytes", 150_000)   # ~1000 lines at ~150 chars/line
_backup_count = _log_cfg.get("backup_count", 5)        # keep api.log + 5 rotated files

logging.getLogger().addFilter(_RedactTokenFilter())
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)-5s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RotatingFileHandler(
            os.path.join(_log_dir, _log_file),
            maxBytes=_max_bytes,
            backupCount=_backup_count,
        ),
        logging.StreamHandler(),
    ],
)

app = FastAPI(title="GITHUB_SUMMARISER_API", version="1.0.0")

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your routes with the router objects
app.include_router(gitdigest_router, prefix="/api/v1", tags=["GitDigest"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "service": "GITHUB_SUMMARISER_API"}

def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default=None)  # None = auto from APP_ENV
    args = parser.parse_args()

    is_prod = os.getenv("APP_ENV", "dev") == "prod"
    host = args.host or ("0.0.0.0" if is_prod else "127.0.0.1")

    kwargs = {"host": host, "port": args.port, "workers": 2 if is_prod else 1}
    if not is_prod:
        kwargs["reload"] = True

    uvicorn.run("api.main:app", **kwargs)

if __name__ == "__main__":
     main()