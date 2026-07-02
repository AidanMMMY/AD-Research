# FRED Macro Pipeline — Deploy Checklist (2026-07-02)

Phase 3 introduced the FRED macro-indicator pipeline (US GDP/CPI/yields/etc.).
This runbook captures the deploy-time steps and operational notes.

## 1. Set FRED_API_KEY on the server

A free API key can be obtained at
<https://fred.stlouisfed.org/docs/api/api_key.html> (~30s, no credit card).
The key for this environment is:

```
FRED_API_KEY=3f952f78ef1a3405cbc9591b8edeeace
```

Append it to `/opt/ad-research/.env` on `ad-research`:

```bash
ssh ad-research "grep -q '^FRED_API_KEY=' /opt/ad-research/.env && echo exists || echo 'FRED_API_KEY=3f952f78ef1a3405cbc9591b8edeeace' >> /opt/ad-research/.env"
```

Then restart the backend container so the new env is picked up:

```bash
ssh ad-research "cd /opt/ad-research && docker compose restart backend"
```

## 2. Apply the new Alembic migration

```bash
ssh ad-research "cd /opt/ad-research && docker compose exec backend alembic upgrade head"
```

This creates the `macro_indicator` table.

## 3. Trigger an initial backfill

The FRED scheduler job runs at 03:00 Beijing time on weekdays. To seed
the table immediately:

```bash
ssh ad-research "cd /opt/ad-research && docker compose exec backend python -c 'from app.services.macro.fred_service import FredService; from app.core.database import SessionLocal; db = SessionLocal(); s = FredService(db=db); print(s.refresh(lookback_days=730))'"
```

This pulls the last 2 years (~365 rows × 24 series ≈ 8.7k rows).

## 4. Verify

- Backend health: `curl http://47.239.13.111:8000/api/v1/macro/indicators?region=us | head`
- Scheduler job registered: `GET /api/v1/admin/scheduler/jobs` should list
  `fred_macro_daily` (id) / `FRED 美国宏观日刷` (name).
- Frontend: open <https://ad-research.example.com/macro> and confirm
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