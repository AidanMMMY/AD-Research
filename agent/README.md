# AD-Research Agent Workers

This directory contains the standalone data-collection agents that run on the
Alibaba ECS host.  They are versioned together with the main platform repo for
visibility, but they run in their own Docker image (`alloyresearch-agent`) and
write into `/data/ad-research/`.

## Layout

- `workers/` — Python source for each Tier-1 data source.
- `scripts/` — `orchestrate_v2.py`, `run_worker.sh`, `setup_cron.sh`, etc.
- `Dockerfile` / `docker-compose.yml` — agent image build files.
- `docs/` — runbooks for IP blocks, cookie warmup, etc.

## Operations

The orchestrator is triggered by `/etc/cron.d/ad-research-orchestrate` on the
ECS host every hour at minute 47:

```bash
/usr/bin/env python3 /root/ad-research/agent/scripts/orchestrate_v2.py \
  --schedule all --output-dir /data/ad-research/aggregate.json
```

Workers should be edited on the ECS host under `/root/ad-research/agent/`, then
committed to the local git repo there and the bundle pushed to GitHub if needed.
