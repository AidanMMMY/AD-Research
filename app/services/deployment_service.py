"""Deployment dashboard service.

Provides GitHub Actions workflow history, Docker container health stats,
and log streaming via Redis pub/sub — used by the Vercel-style admin page.
"""

import http.client
import json
import logging
import os
import re
import socket as socket_module
import threading
from datetime import datetime, timezone

import redis

from app.config import get_settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_SENSITIVE_PATTERNS = [
    (re.compile(r"(?:password|passwd)[=:]\s*(\S+)", re.IGNORECASE), "password=***"),
    (re.compile(r"(?:token|api_key|apikey|secret|key)[=:]\s*(\S+)", re.IGNORECASE), r"\1=***"),
    (re.compile(r'(?:AUTH_SECRET_KEY|AUTH_ADMIN_PASSWORD|POSTGRES_PASSWORD)=\S+'), r"\1=***"),
    (re.compile(r'ghp_\w{36}'), "ghp_***"),
]


def _sanitize(line: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line


# ---------------------------------------------------------------------------
# GitHub Actions helpers
# ---------------------------------------------------------------------------

def _gh_api(path: str, params: dict | None = None) -> dict | list | None:
    """Call the GitHub REST API with the configured token and repo."""
    import urllib.request

    settings = get_settings()
    if not settings.github_token or not settings.github_repo:
        return None

    base = f"https://api.github.com/repos/{settings.github_repo}/actions"
    url = f"{base}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {settings.github_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "alloy-research-deploy-dashboard")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]
    except Exception:
        logger.exception("GitHub API call failed: %s", path)
        return None


def list_workflow_runs(per_page: int = 20) -> list[dict]:
    """Return recent workflow runs for the deploy workflow."""
    data = _gh_api("/runs", params={"per_page": str(per_page), "event": "push"})
    if not data or "workflow_runs" not in data:  # type: ignore[operator]
        return []
    runs: list[dict] = []
    for run in data["workflow_runs"]:  # type: ignore[index]
        created = run.get("created_at", "")
        updated = run.get("updated_at", "")
        duration = 0
        if created and updated:
            try:
                start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                duration = max(0, int((end - start).total_seconds()))
            except ValueError:
                pass

        runs.append(
            {
                "id": run["id"],
                "run_number": run["run_number"],
                "status": run.get("status", "unknown"),
                "conclusion": run.get("conclusion"),
                "head_branch": run.get("head_branch", ""),
                "head_sha": (run.get("head_sha", "") or "")[:7],
                "display_title": run.get("display_title", "") or (
                    (run.get("head_commit", {}) or {}).get("message", "")
                ),
                "actor_login": (run.get("actor", {}) or {}).get("login", ""),
                "created_at": created,
                "updated_at": updated,
                "duration_seconds": duration,
                "html_url": run.get("html_url", ""),
            }
        )
    return runs


def get_run_logs(run_id: int) -> str:
    """Return logs for a specific workflow run as plain text."""
    data = _gh_api(f"/runs/{run_id}/logs", params={})
    # GitHub redirects to a log download URL; urllib doesn't follow for auth'd
    # redirects.  We call the same URL with a redirect handler.
    if data is None:
        return ""

    settings = get_settings()
    url = f"https://api.github.com/repos/{settings.github_repo}/actions/runs/{run_id}/logs"

    import urllib.request

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {settings.github_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "alloy-research-deploy-dashboard")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # The response is a zip of log files — return a summary
            return f"Log zip available at: {resp.url}\n(Download from GitHub Actions UI for full logs)"
    except Exception as exc:
        logger.exception("Failed to fetch run logs: %s", exc)
        return f"Failed to fetch logs: {exc}"


def trigger_workflow_dispatch() -> dict:
    """Manually trigger the deploy workflow via workflow_dispatch."""
    settings = get_settings()
    if not settings.github_token or not settings.github_repo:
        return {"ok": False, "error": "GitHub token or repo not configured"}

    import urllib.request

    url = (
        f"https://api.github.com/repos/{settings.github_repo}/actions/workflows/"
        f"deploy.yml/dispatches"
    )
    body = json.dumps({"ref": "main"}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {settings.github_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "alloy-research-deploy-dashboard")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status == 204, "status": resp.status}
    except Exception as exc:
        logger.exception("Trigger workflow dispatch failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Docker helpers (direct Unix socket, no Docker CLI needed)
# ---------------------------------------------------------------------------

class _DockerUnixConnection(http.client.HTTPConnection):
    """HTTPConnection that routes requests over the Docker Unix socket."""

    def __init__(self, socket_path: str, timeout: int = 15):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        self.sock = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


def _docker_socket_available() -> bool:
    return os.path.exists(get_settings().deploy_docker_socket)


def _docker_api(method: str, path: str, timeout: int = 15) -> tuple[int, object]:
    """Call the Docker Engine API over the Unix socket.

    Returns (status_code, decoded_body).  Body is a ``dict``/``list`` when the
    response is JSON, otherwise a ``str``.
    """
    settings = get_settings()
    try:
        conn = _DockerUnixConnection(settings.deploy_docker_socket, timeout=timeout)
        conn.request(method, path)
        resp = conn.getresponse()
        body_bytes = resp.read()
        status = resp.status

        content_type = resp.getheader("Content-Type", "")
        if "application/json" in content_type:
            return status, json.loads(body_bytes) if body_bytes else {}
        return status, body_bytes.decode("utf-8", errors="replace")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        logger.debug("Docker API call failed: %s %s → %s", method, path, exc)
        return -1, str(exc)


def _docker_stream(path: str, timeout: int = 3600):
    """Yield raw chunks from a Docker API streaming endpoint.

    Used for ``follow=1`` log streams.
    """
    settings = get_settings()
    try:
        conn = _DockerUnixConnection(settings.deploy_docker_socket, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            yield chunk
    except (OSError, http.client.HTTPException) as exc:
        logger.debug("Docker stream failed: %s → %s", path, exc)


def _demux_docker_log(data: bytes) -> bytes:
    """Strip Docker log multiplex headers (8 bytes per frame).

    Frame format: [stream_type:1][padding:3][size:4 big-endian][payload...]
    Returns the concatenated payload bytes.
    """
    out = bytearray()
    buf = data
    while len(buf) >= 8:
        size = int.from_bytes(buf[4:8], "big")
        frame_end = 8 + size
        if len(buf) < frame_end:
            break  # incomplete frame — skip for simplicity
        out.extend(buf[8:frame_end])
        buf = buf[frame_end:]
    return bytes(out)


def _format_bytes(n: int) -> str:
    """Format a byte count into a human-readable string."""
    if n == 0:
        return "0 B"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


# ---------------------------------------------------------------------------
# Public Docker helpers
# ---------------------------------------------------------------------------

def get_container_stats() -> list[dict]:
    """Return resource stats for all containers (Docker API, one-shot stats)."""
    if not _docker_socket_available():
        return []

    status, containers_data = _docker_api("GET", "/v1.43/containers/json?all=true")
    if not isinstance(containers_data, list):
        return []

    result: list[dict] = []
    for c in containers_data:
        name = (c.get("Names", [""])[0] or "").lstrip("/")
        state = c.get("State", "unknown")
        status_text = c.get("Status", "")

        entry = {
            "name": name,
            "status": status_text,
            "state": state,
            "image": c.get("Image", ""),
            "uptime": status_text,
            "cpu_percent": 0.0,
            "memory_usage": "",
            "memory_limit": "",
            "memory_percent": 0.0,
        }

        # Fetch one-shot stats for this container
        cid = c.get("Id", "")
        if cid:
            s, stats = _docker_api("GET", f"/v1.43/containers/{cid}/stats?stream=false")
            if isinstance(stats, dict):
                # CPU %
                cpu_delta = (
                    stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                    - stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                )
                system_delta = (
                    stats.get("cpu_stats", {}).get("system_cpu_usage", 0)
                    - stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
                )
                num_cpus = stats.get("cpu_stats", {}).get("online_cpus", 1)
                if system_delta > 0 and num_cpus > 0:
                    entry["cpu_percent"] = round(
                        (cpu_delta / system_delta) * num_cpus * 100, 1
                    )

                # Memory
                mem = stats.get("memory_stats", {})
                mem_usage = mem.get("usage", 0)
                mem_limit = mem.get("limit", 0)
                entry["memory_usage"] = _format_bytes(mem_usage)
                entry["memory_limit"] = _format_bytes(mem_limit)
                if mem_limit > 0:
                    entry["memory_percent"] = round((mem_usage / mem_limit) * 100, 1)

        result.append(entry)

    return result


def get_container_logs(container: str, tail: int = 200) -> list[dict]:
    """Return recent log lines for a container via Docker API."""
    if not _docker_socket_available():
        return []

    status, body = _docker_api(
        "GET",
        f"/v1.43/containers/{container}/logs?stdout=1&stderr=1&tail={tail}&timestamps=1",
    )
    if status != 200 or not isinstance(body, str):
        return []

    # Docker returns multiplexed binary for normal containers.
    # When the container runs with TTY, it returns raw text.  We handle both.
    raw_log = body.encode("utf-8", errors="replace")
    # Try to demux — if the data starts with a valid multiplex header,
    # _demux_docker_log strips headers; otherwise the raw text stays.
    # Heuristic: if we see 0x01 or 0x02 as the first byte followed by
    # three zero bytes, it's multiplexed.
    if raw_log and raw_log[0] in (1, 2) and raw_log[1:4] == b"\x00\x00\x00":
        raw_log = _demux_docker_log(raw_log)

    text = raw_log.decode("utf-8", errors="replace")

    lines: list[dict] = []
    for line in text.split("\n"):
        line = line.strip("\r")
        if not line:
            continue
        sanitized = _sanitize(line)
        ts = ""
        msg = sanitized
        if " " in sanitized:
            ts, msg = sanitized.split(" ", 1)
        lines.append({"timestamp": ts, "container": container, "message": msg})

    return lines


# ---------------------------------------------------------------------------
# Log streaming via Docker API + Redis pub/sub
# ---------------------------------------------------------------------------

_log_tailer_stops: dict[str, threading.Event] = {}
_tailer_lock = threading.Lock()
_tail_headers_seen: set[int] = set()  # track thread ids that have output headers


def _log_tailer_header(container: str) -> None:
    """Emit a one-time info header for a tailer thread (deduped)."""
    tid = threading.get_ident()
    if tid in _tail_headers_seen:
        return
    _tail_headers_seen.add(tid)
    logger.info("Log tailer started for %s", container)


def start_log_tailer(container: str) -> None:
    """Start a background thread that streams container logs via Docker API
    and publishes each line to Redis pub/sub."""
    with _tailer_lock:
        if container in _log_tailer_stops:
            return  # already running

    stop_event = threading.Event()
    _log_tailer_stops[container] = stop_event

    redis_client: redis.Redis = get_redis_client()
    channel = f"deploy:logs:{container}"

    def _tail() -> None:
        _log_tailer_header(container)
        try:
            for chunk in _docker_stream(
                f"/v1.43/containers/{container}/logs?stdout=1&stderr=1"
                "&follow=1&tail=10&timestamps=1",
                timeout=86400,
            ):
                if stop_event.is_set():
                    break

                # Demux if multiplexed
                if chunk and chunk[0] in (1, 2) and chunk[1:4] == b"\x00\x00\x00":
                    chunk = _demux_docker_log(chunk)

                for raw_line in chunk.decode("utf-8", errors="replace").split("\n"):
                    raw_line = raw_line.strip("\r")
                    if not raw_line:
                        continue
                    line = _sanitize(raw_line)
                    ts, msg = ("", line)
                    if " " in line:
                        ts, msg = line.split(" ", 1)
                    try:
                        redis_client.publish(
                            channel,
                            json.dumps(
                                {
                                    "timestamp": ts,
                                    "container": container,
                                    "message": msg,
                                }
                            ),
                        )
                    except redis.RedisError:
                        pass
        except Exception:
            logger.exception("Log tailer for %s exited", container)
        finally:
            with _tailer_lock:
                _log_tailer_stops.pop(container, None)

    t = threading.Thread(target=_tail, daemon=True, name=f"log-tailer-{container}")
    t.start()


def stop_log_tailer(container: str) -> None:
    """Signal a background log tailer to stop."""
    with _tailer_lock:
        ev = _log_tailer_stops.pop(container, None)
    if ev:
        ev.set()


def get_log_tailer_containers() -> list[str]:
    """Return list of containers currently being tailed."""
    with _tailer_lock:
        return list(_log_tailer_stops.keys())


def get_server_health() -> dict:
    """Return server health summary with containers."""
    containers = get_container_stats()
    return {
        "containers": containers,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
