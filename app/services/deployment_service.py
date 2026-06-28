"""Deployment dashboard service.

Provides GitHub Actions workflow history, Docker container health stats,
and log streaming via Redis pub/sub — used by the Vercel-style admin page.
"""

import json
import logging
import os
import re
import subprocess
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
    req.add_header("User-Agent", "ad-research-deploy-dashboard")

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
    req.add_header("User-Agent", "ad-research-deploy-dashboard")

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
    req.add_header("User-Agent", "ad-research-deploy-dashboard")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status == 204, "status": resp.status}
    except Exception as exc:
        logger.exception("Trigger workflow dispatch failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _docker_socket_available() -> bool:
    return os.path.exists(get_settings().deploy_docker_socket)


def _docker(args: list[str], timeout: int = 15) -> tuple[int, str]:
    """Run a docker CLI command and return (exit_code, stdout)."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        )
        return result.returncode, result.stdout
    except FileNotFoundError:
        return -1, "docker CLI not available"
    except subprocess.TimeoutExpired:
        return -1, "docker command timed out"
    except Exception as exc:
        return -1, str(exc)


def get_container_stats() -> list[dict]:
    """Return resource stats for all running containers."""
    if not _docker_socket_available():
        return []

    # Get container list with docker ps
    rc, out = _docker(
        [
            "ps",
            "-a",
            "--format",
            "{{.Names}}|{{.Status}}|{{.State}}|{{.Image}}|{{.RunningFor}}",
        ],
        timeout=10,
    )
    if rc != 0:
        return []

    containers: list[dict] = {}
    for line in out.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) < 4:
            continue
        name = parts[0]
        containers[name] = {
            "name": name,
            "status": parts[1],
            "state": parts[2] if len(parts) > 2 else "unknown",
            "image": parts[3],
            "uptime": parts[4] if len(parts) > 4 else "",
            "cpu_percent": 0.0,
            "memory_usage": "",
            "memory_limit": "",
            "memory_percent": 0.0,
        }

    # Get resource usage with docker stats (one-shot)
    rc, stats_out = _docker(
        ["stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}"],
        timeout=10,
    )
    if rc == 0:
        for line in stats_out.strip().split("\n"):
            parts = line.split("|", 3)
            if len(parts) < 3:
                continue
            name = parts[0]
            if name in containers:
                c = containers[name]
                try:
                    c["cpu_percent"] = float(parts[1].replace("%", ""))
                except ValueError:
                    c["cpu_percent"] = 0.0
                mem_usage = parts[2].split("/")
                c["memory_usage"] = mem_usage[0].strip() if len(mem_usage) > 0 else ""
                c["memory_limit"] = mem_usage[1].strip() if len(mem_usage) > 1 else ""
                try:
                    c["memory_percent"] = float(parts[3].replace("%", "")) if len(parts) > 3 else 0.0
                except ValueError:
                    c["memory_percent"] = 0.0

    return list(containers.values())


def get_container_logs(container: str, tail: int = 200) -> list[dict]:
    """Return recent log lines for a container."""
    if not _docker_socket_available():
        return []

    rc, out = _docker(
        ["logs", "--tail", str(tail), "--timestamps", container],
        timeout=15,
    )
    if rc != 0:
        return []

    lines: list[dict] = []
    for line in out.strip().split("\n"):
        if not line:
            continue
        sanitized = _sanitize(line.strip())
        # docker -t format: "2024-01-15T10:23:45.123456789Z message..."
        ts = ""
        msg = sanitized
        if " " in sanitized:
            ts, msg = sanitized.split(" ", 1)
        lines.append({"timestamp": ts, "container": container, "message": msg})

    return lines


# ---------------------------------------------------------------------------
# Log streaming via Redis pub/sub
# ---------------------------------------------------------------------------

_log_tailers: dict[str, subprocess.Popen] = {}
_tailer_lock = threading.Lock()


def start_log_tailer(container: str) -> None:
    """Start a background process that tails container logs and publishes to Redis."""
    with _tailer_lock:
        if container in _log_tailers:
            return  # already running

    redis_client: redis.Redis = get_redis_client()
    channel = f"deploy:logs:{container}"

    def _tail() -> None:
        try:
            proc = subprocess.Popen(
                [
                    "docker", "logs", "-f", "--tail", "10", "--timestamps",
                    container,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
            )
            with _tailer_lock:
                _log_tailers[container] = proc
        except Exception:
            logger.exception("Failed to start log tailer for %s", container)
            return

        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = _sanitize(raw_line.strip())
                if not line:
                    continue
                ts = ""
                msg = line
                if " " in line:
                    ts, msg = line.split(" ", 1)
                payload = json.dumps(
                    {"timestamp": ts, "container": container, "message": msg}
                )
                try:
                    redis_client.publish(channel, payload)
                except redis.RedisError:
                    pass
        except Exception:
            logger.exception("Log tailer for %s exited unexpectedly", container)
        finally:
            with _tailer_lock:
                _log_tailers.pop(container, None)
                try:
                    proc.terminate()
                except Exception:
                    pass

    t = threading.Thread(target=_tail, daemon=True, name=f"log-tailer-{container}")
    t.start()


def stop_log_tailer(container: str) -> None:
    """Stop a background log tailer."""
    with _tailer_lock:
        proc = _log_tailers.pop(container, None)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def get_log_tailer_containers() -> list[str]:
    """Return list of containers currently being tailed."""
    with _tailer_lock:
        return list(_log_tailers.keys())


def get_server_health() -> dict:
    """Return server health summary with containers."""
    containers = get_container_stats()
    return {
        "containers": containers,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
