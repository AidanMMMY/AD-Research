# FRED Macro Pipeline — Deploy Checklist (2026-07-02)

> 最后核实更新：2026-07-21

Phase 3 introduced the FRED macro-indicator pipeline (US GDP/CPI/yields/etc.).
This runbook captures the deploy-time steps and operational notes.

## 1. Set FRED_API_KEY on the server

A free API key can be obtained at
<https://fred.stlouisfed.org/docs/api/api_key.html> (~30s, no credit card).

> ⚠️ **安全修正（2026-07-21）**：本文早年版本把真实 `FRED_API_KEY` 明文写在了
> 这里——这违反仓库自己的 secret 管理规则（见
> `20260704-secret-rotate-runbook.md`）。明文已从文档中移除；**当时那把 key
> 必须视为已泄露，请到 FRED 后台重新生成后再按下面步骤配置**。

Set the key in the backend env file. The production compose stack
(`deploy/aliyun-ecs/docker-compose.yml`) injects env vars via `${VAR:-}`
interpolation, so the source of truth is `deploy/aliyun-ecs/.env` on the
server (not `/opt/ad-research/.env`):

```bash
ssh ad-research "grep -q '^FRED_API_KEY=' /opt/ad-research/deploy/aliyun-ecs/.env && echo exists || echo 'FRED_API_KEY=<your_fred_key_here>' >> /opt/ad-research/deploy/aliyun-ecs/.env"
```

Then **recreate** the backend container so the new env is picked up
(`docker compose restart` does NOT re-read the env file):

```bash
ssh ad-research "cd /opt/ad-research/deploy/aliyun-ecs && docker compose up -d --force-recreate --no-deps backend"
```

## 2. Apply the new Alembic migration

```bash
ssh ad-research "cd /opt/ad-research/deploy/aliyun-ecs && docker compose exec backend alembic upgrade head"
```

This creates the `macro_indicator` table.

## 3. Trigger an initial backfill

The FRED scheduler job runs at 03:00 Beijing time (Asia/Shanghai) on weekdays.
To seed the table immediately:

```bash
ssh ad-research "cd /opt/ad-research/deploy/aliyun-ecs && docker compose exec backend python -c 'from app.services.macro.fred_service import FredService; from app.core.database import SessionLocal; db = SessionLocal(); s = FredService(db=db); print(s.refresh(lookback_days=730))'"
```

This pulls the last 2 years for every registered series. Note the registry
has grown since Phase 3: it is now 25 US + 4 EU + 7 global = 36 series
(`app/services/macro/fred_service.py`), so expect ~9.5k rows rather than the
original 24-series estimate. The default `lookback_days` is 180.

## 4. Verify

- Backend health: `curl http://47.239.13.111:8000/api/v1/macro/indicators?region=us | head`
- Scheduler job registered: `GET /api/v1/etl/scheduler/jobs` (the
  `/api/v1/admin/scheduler/jobs` path no longer exists — scheduler
  introspection lives under the ETL router) should list
  `fred_macro_daily` (id) / `FRED 美国宏观日刷` (name).
- Frontend: open <https://www.alloyresearch.net/macro> and confirm
  KPI strip + table render.

## 5. Failure modes

| Symptom                              | Cause                                          | Fix                                              |
|--------------------------------------|------------------------------------------------|--------------------------------------------------|
| `skipped_reason: FRED_API_KEY not configured` | Missing/blank env var                  | Re-check `.env`, restart container               |
| `failed: ['DGS10', ...]` in summary  | Network blip / rate-limit                      | Re-run `refresh()` — failed series retry next day |
| 429 spam in logs                     | Concurrent refreshes                           | Redis lock should prevent this; check scheduler  |
| Table empty after deploy             | Migration not applied                          | `alembic upgrade head`                           |

## 6. What ships in this PR

- `app/models/macro.py` — `MacroIndicator` ORM model
- `alembic/versions/a1b2c3d4e5f7_add_macro_indicator_table.py` — migration
- `app/data/providers/fred_provider.py` — FRED API client
- `app/services/macro/fred_service.py` — 24-series registry + refresh logic
- `app/services/macro/__init__.py`
- `app/services/news/scheduler_jobs.py` — added `run_fred_refresh`
- `app/core/scheduler.py` — registered `fred_macro_daily` cron
- `app/api/v1/macro.py` — FRED read endpoints (list / series / admin refresh)
- `app/schemas/macro.py` — Pydantic shapes (also extended for Phase 2 CN)
- `app/main.py` — wired `/api/v1/macro` router
- `app/models/__init__.py` — re-exports `MacroIndicator`
- `app/tests/test_fred_provider.py`, `app/tests/test_fred_service.py`
- `web/src/api/macro.ts`, `web/src/hooks/useMacro.ts`
- `web/src/pages/Macro/index.tsx` — new `/macro` page
- `web/src/routes.tsx`, `web/src/api/index.ts` — route + export wiring