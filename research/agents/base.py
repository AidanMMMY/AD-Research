"""Shared helpers for research agents."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("research.agents.base")


def safe_get(url: str, timeout: int = 30, retries: int = 2, **kwargs) -> requests.Response | None:
    """GET with retries and sensible defaults."""
    headers = kwargs.pop("headers", {})
    headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    )
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("GET %s failed (attempt %d): %s", url, attempt + 1, exc)
    logger.error("GET %s ultimately failed: %s", url, last_exc)
    return None


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    return re.sub(r"[^\w\-_.]", "_", name).strip("_")[:100]


def save_raw(
    data_dir: Path,
    agent: str,
    name: str,
    payload: Any,
    ext: str = "json",
    default: Any = None,
) -> Path:
    """Save raw agent output to a timestamped file."""
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    folder = data_dir / agent / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sanitize_filename(name)}_{now}.{ext}"
    if ext == "json":
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=default),
            encoding="utf-8",
        )
    else:
        path.write_text(str(payload), encoding="utf-8")
    logger.info("[%s] Saved raw data: %s", agent, path)
    return path


def save_note(data_dir: Path, agent: str, title: str, body: str) -> Path:
    """Save a synthesized markdown note."""
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    folder = data_dir / agent / "notes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sanitize_filename(title)}_{now}.md"
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    logger.info("[%s] Saved note: %s", agent, path)
    return path


def load_status(data_dir: Path) -> dict:
    path = data_dir / "status.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
