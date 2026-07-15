"""Overnight research orchestrator.

Runs on ECS inside a dedicated Docker container.  Spawns multiple
"sub-agents" (processes) that each collect/synthesize one research theme.
Results are written to RESEARCH_DATA_DIR so they survive container restarts.

Usage (inside ECS container):
    PYTHONPATH=/app python3 /app/research/orchestrator.py
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from multiprocessing import Process
from pathlib import Path

from research.agents.macro_policy import run_macro_policy_agent
from research.agents.market_data import run_market_data_agent
from research.agents.academic import run_academic_agent
from research.agents.event_price import run_event_price_agent
from research.agents.guru_opinion import run_guru_opinion_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("research.orchestrator")

DATA_DIR = Path(os.environ.get("RESEARCH_DATA_DIR", "/app/research_data"))
RUNTIME_HOURS = float(os.environ.get("RESEARCH_RUNTIME_HOURS", "20"))

AGENTS = [
    ("macro_policy", run_macro_policy_agent, 3600),
    ("market_data", run_market_data_agent, 1800),
    ("academic", run_academic_agent, 7200),
    ("event_price", run_event_price_agent, 3600),
    ("guru_opinion", run_guru_opinion_agent, 3600),
]


def _spawn_all(data_dir: Path) -> list[Process]:
    """Spawn one child process per research agent."""
    procs = []
    for name, fn, _interval in AGENTS:
        p = Process(target=fn, args=(str(data_dir), name), name=f"agent-{name}")
        p.start()
        procs.append((name, p))
        logger.info("Spawned agent %s (pid=%s)", name, p.pid)
    return procs


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "status.json").write_text(
        json.dumps({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "planned_runtime_hours": RUNTIME_HOURS,
            "agents": [a[0] for a in AGENTS],
        }, ensure_ascii=False, indent=2)
    )

    deadline = time.time() + RUNTIME_HOURS * 3600
    procs = _spawn_all(DATA_DIR)

    try:
        while time.time() < deadline:
            alive = sum(1 for _, p in procs if p.is_alive())
            logger.info("Heartbeat: %d/%d agents alive", alive, len(procs))

            # Respawn any crashed agent so the research keeps going.
            for i, (name, p) in enumerate(procs):
                if not p.is_alive():
                    logger.warning("Agent %s exited with code %s; respawning", name, p.exitcode)
                    new_p = Process(
                        target=AGENTS[i][1],
                        args=(str(DATA_DIR), name),
                        name=f"agent-{name}",
                    )
                    new_p.start()
                    procs[i] = (name, new_p)

            time.sleep(300)
    except KeyboardInterrupt:
        logger.info("Received interrupt, terminating agents...")
    finally:
        for name, p in procs:
            if p.is_alive():
                logger.info("Terminating agent %s", name)
                p.terminate()
                p.join(timeout=10)
                if p.is_alive():
                    p.kill()
        (DATA_DIR / "status.json").write_text(
            json.dumps({
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "agents": [a[0] for a in AGENTS],
            }, ensure_ascii=False, indent=2)
        )
        logger.info("Research session ended. Data in %s", DATA_DIR)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
