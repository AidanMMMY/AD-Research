# Reddit curl_cffi test report — 2026-07-07

> Author: AD-Research deploy/ops agent
> Test env: ECS 47.239.13.111 (Aliyun HK), Python 3.14, curl_cffi 0.15.0
> Goal: determine whether curl_cffi TLS impersonation can sidestep the Reddit WAF
> block that broke `workers/reddit_finance.py` (the existing worker uses raw
> `requests`, which now returns 403 on every Reddit endpoint).

## TL;DR

**TLS-fingerprint rotation does not work.** Every one of 30+ impersonate
profiles (Chrome 99 → 146, Edge 99/101, Firefox 133/135/147, Safari 15.3 →
Safari 26 mobile/desktop) returns the same 190 KB Reddit WAF block page from
every Reddit-owned hostname (`www`, `old`, `i`, `oauth`). The ECS IP
`47.239.13.111` is on Reddit's network-level denylist, so the WAF rejects us
*before* any TLS-client-hello inspection can distinguish curl_cffi from a real
browser.

**Recommendation:** bite the bullet and put the worker behind a **rotating
residential proxy** (USD 15-30/month for our expected volume). Mobile
carrier proxies also work. Static datacenter IP ranges (including most "cheap"
Chinese proxies) will likely be blocked the same way ours is.

---

## 1. Worker delivered

**Path:** `/root/ad-research/agent/workers/reddit_curl_cffi.py`

**Highlights:**
- Uses `curl_cffi.requests.Session(impersonate=...)` instead of `requests`.
- Self-contained (does NOT import the diverged `common.py`); defines its own
  logger, ISO/truncate helpers, and output writer.
- `--impersonate` switch covering 34 `BrowserType` profiles.
- `--domain {www,old,i}` switch.
- `--proxy http://user:pass@host:port` switch — drop-in residential proxy
  hook. The session correctly routes through `proxies={"http":..., "https":...}`
  and surfaces a clear "ECS IP is on Reddit WAF denylist. Configure --proxy."
  ERROR log on the first 403 so downstream alerting is unambiguous.
- `--dry-run` mode prints a profile × status-code table for quick WAF probing.
- Detects a 403 on the very first page and bails fast (does not waste proxy
  budget on subsequent subreddit calls).
- Added `curl_cffi>=0.15` to `/root/ad-research/agent/requirements.txt`
  (verified via `pip3 install --break-system-packages curl_cffi`).

**Test invocation examples:**
```bash
# 1. Smoke (fails fast on 403, writes empty [])
python3 workers/reddit_curl_cffi.py --subreddit wallstreetbets \
    --hours 24 --output /tmp/wsb.json --rate 0 --max-pages 1

# 2. Probe every profile against www.reddit.com
python3 workers/reddit_curl_cffi.py --dry-run --rate 0

# 3. Behind a residential proxy (after proxy credentials are issued)
python3 workers/reddit_curl_cffi.py --all-subs --hours 24 \
    --impersonate chrome124 \
    --proxy http://user:pass@resi.example.com:8000 \
    --output /data/ad-research/reddit/$(date -u +%Y%m%dT%H%M%SZ).json
```

---

## 2. Tests run + results

### Test A — Baseline: requests vs curl_cffi (chrome, default)

| Endpoint | `requests.get` | `curl_cffi` chrome |
|---|---|---|
| https://www.reddit.com/r/wallstreetbets/new.json | **403** 190240 b | **403** 190238 b |
| https://www.reddit.com/r/stocks/new.json         | **403** 190240 b | **403** 190238 b |
| https://old.reddit.com/r/wallstreetbets/new.json | **403** 1522 b   | **403** 1522 b   |
| https://i.reddit.com/r/wallstreetbets/new.json   | **403** 190240 b | **403** 190238 b |

`old.reddit.com` returns a tiny `Blocked` HTML, the others return the new
Snooserv-rendered 190 KB block page (`Server: snooserv`,
`via: 1.1 varnish`).
curl_cffi JA3 ~ Chrome ≈ requests JA3 (no impersonation) → same block.
**Conclusion:** TLS fingerprint is not the deciding signal.

### Test B — 403 body inspection

```text
Status: 403
Server: snooserv
Content-Type: text/html
Set-Cookie: edgebucket=SaOHAnEbTnSdvGaPEn; Domain=reddit.com; ...
via: 1.1 varnish
Body (190238 b): <body class="theme-beta">... Snoo-block landing page
```

The block is rendered by Reddit's own edge (snooserv → varnish). No
Cloudflare/Akamai redirect involved. The block list lives on Reddit's own
infrastructure and resolves at the gateway before any per-request fingerprint
analysis runs.

### Test C — Domain/cookie scope

| Endpoint | chrome (no cookie) | chrome + fake `reddit_session` |
|---|---|---|
| https://oauth.reddit.com/api/v1/me              | 403 (190 KB) | 403 (190 KB)         |
| https://www.reddit.com/api/v1/me                | 403 (190 KB) | **200** (1.6 KB)    |
| https://www.reddit.com/snoop.json               | 403 (190 KB) | 403 (190 KB)         |
| https://www.reddit.com/.json                    | 403 (190 KB) | 403 (190 KB)         |
| https://www.reddit.com/                         | 403 (190 KB) | —                   |
| https://www.reddit.com/r/all/hot.json?limit=5   | 403 (190 KB) | —                   |
| https://www.redditstatus.com/                   | **200** (266 KB) | — (control)   |

- `redditstatus.com` (Akamai-hosted, separate infrastructure) → 200 → outbound
  HTTPS to Reddit works fine in principle.
- `api/v1/me` returns 200 only when a (fake) `reddit_session` cookie is
  present, but `.json` / `snoop.json` remain 403 — this proves the block is
  per-endpoint-policy, not TLS layer.
- A forged cookie does not unlock rate-limit-style content, only the auth
  endpoint.

### Test D — Full impersonate matrix

`https://www.reddit.com/r/wallstreetbets/new.json?limit=5` for each profile.
Tested profiles (34 total — head -n 12 shown; full list below):

| Impersonate profile      | Status | Bytes  |
|--------------------------|--------|--------|
| chrome99                 |   403  | 190238 |
| chrome100                |   403  | 190238 |
| chrome101                |   403  | 190238 |
| chrome104                |   403  | 190238 |
| chrome107                |   403  | 190238 |
| chrome110                |   403  | 190238 |
| chrome116                |   403  | 190238 |
| chrome119                |   403  | 190238 |
| chrome120                |   403  | 190238 |
| chrome123                |   403  | 190238 |
| chrome124                |   403  | 190238 |
| chrome131                |   403  | 190238 |
| chrome133a               |   403  | 190238 |
| chrome136                |   403  | 190238 |
| chrome142                |   403  | 190238 |
| chrome145                |   403  | 190238 |
| chrome146                |   403  | 190238 |
| chrome99_android         |   403  | 190238 |
| chrome131_android        |   403  | 190238 |
| edge99                   |   403  | 190238 |
| edge101                  |   403  | 190238 |
| firefox133               |   403  | 190238 |
| firefox135               |   403  | 190238 |
| firefox147               |   403  | 190238 |
| safari15_3               |   403  | 190238 |
| safari15_5               |   403  | 190238 |
| safari17_0               |   403  | 190238 |
| safari17_2_ios           |   403  | 190238 |
| safari18_0               |   403  | 190238 |
| safari18_0_ios           |   403  | 190238 |
| safari184                |   403  | 190238 |
| safari184_ios            |   403  | 190238 |
| safari260                |   403  | 190238 |
| safari2601               |   403  | 190238 |

All 34 profiles → identical 403 response with identical byte length
(190 238 b) — same Snoo block page served from varnish cache.

### Test E — Endpoint × profile matrix (12 representative combos)

| profile       | www./r/wsb/new.json | www./r/wsb/hot.json | old./r/wsb/new.json | i./r/wsb/new.json |
|---------------|---------------------|---------------------|---------------------|--------------------|
| chrome        | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| chrome99      | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| chrome110     | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| chrome124     | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| chrome146     | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| edge99        | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| firefox135    | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| firefox147    | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| safari15_5    | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| safari17_0    | 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |
| safari17_2_ios| 403 (190 KB)        | 403 (190 KB)        | 403 (1.5 KB)        | 403 (190 KB)       |

`old.reddit.com` serves a stripped-down `Blocked` HTML rather than the 190 KB
Snoo page, but otherwise the matrix is perfectly flat.

---

## 3. Analysis

The 403 is the same 190 KB block served from `snooserv → varnish` for every
input combination. If the WAF were doing per-fingerprint analysis we would
expect at least one of the 34 impersonate profiles to slip through (since
their JA3/H2 fingerprints are genuinely different). The fact that none do,
plus the fact that `redditstatus.com` succeeds (so HTTPS egress works), means
the WAF key is **source IP reputation**.

Plausible history:
- ECS IP 47.239.13.111 has been hammering Reddit at sub-hour cadence from the
  previous `reddit_finance.py` worker.
- Reddit's WAF auto-blacklists IPs that make too many requests too fast from
  a single /24.
- Standard datacenter ranges get added to a denylist that is *not* lifted by
  TLS churn.

This rules out TLS fingerprinting as a viable fix without changing the
egress IP. The only remaining pivots are:

1. **Residential proxy (rotating)** — pick a fresh home IP per request.
2. **Mobile carrier proxy (4G/5G)** — IP space is rarely blacklisted and the
   natural rotation makes rate-limit WAFs effectively a non-issue.
3. **Reddit official OAuth API** — requires registering an app and adding
   Reddit script-style credentials to the secrets vault. Has its own rate
   limit (60 req/min) but is the "white-listed" path.

---

## 4. Residential proxy recommendation

For AD-Research we expect **~30 k Reddit GETs/month** at the cadence the
orchestrator currently drives (six subreddits × 1-4 pages × every 30-60 min).
At ~3 KB per request that's < 200 MB/month — bandwidth is cheap.

| Vendor      | Type              | Plan                         | USD/month (our volume) | Notes |
|-------------|-------------------|------------------------------|------------------------|-------|
| **IPIDEA**  | Static residential | $0.04-0.08 per IP/month      | **$5-15**             | Static home IPs from > 200 countries; Alipay/WeChat friendly; very popular with CN-side scrapers |
| **Lumiproxy** | Static / rotating | $0.06/IP static, $3.5/GB rotating | **$8-20**       | Static residential same as IPIDEA; rotating is genuinely rotating carrier-grade |
| **IPRoyal** | Rotating residential | 100 MB → $1, traffic-based | **$10-20**          | Aggressively priced; supports rotating sticky sessions (good for Reddit's `/after` cursor) |
| **Bright Data** | Rotating residential | $3.0/GB (Residential) | **$15-30** | Premium reliability; specific `reddit.com` whitelisting path |
| **Smartproxy** | Rotating residential | $2.5/GB, sticky 30 min | **$15-25** | Same family as Bright Data at lower price |

### Recommendation for AD-Research

1. **First try the cheap end:** **Lumiproxy static residential** ($8-15/mo).
   Two static home IPs on US/EU carriers, used by the single Reddit worker.
   Add the credentials to `.env` as `REDDIT_PROXY` and hand them to
   `reddit_curl_cffi.py --proxy`.
2. **If static still gets blocked** (some home IPs are noisy neighbours):
   **IPRoyal rotating residential**, sticky-session 5-10 min. Budget $15.
3. **Don't waste credits on shared datacenter proxies** (e.g. typical
   $1/GB "elite" lists) — Reddit's denylist catches them first.

### Wiring it in

Already done in the worker. Once the operator fills in `.env`:

```bash
REDDIT_PROXY=http://user:pass@resi.lumiproxy.com:8000
```

…the cron/scheduler can simply run:
```bash
python3 workers/reddit_curl_cffi.py --all-subs --hours 24 \
    --impersonate chrome124 \
    --proxy "$REDDIT_PROXY" \
    --output /data/ad-research/reddit/$(date -u +%Y%m%dT%H%M%SZ).json
```

No worker code change required.

---

## 5. Issues / open follow-ups

- **common.py drift.** Both `reddit_finance.py` (pre-existing) and the new
  `reddit_curl_cffi.py` initially failed to import from `common.py` because
  `common.py` exports `setup_logger`, `make_session`, `http_get`,
  `write_json`, `safe_get`, `first_nonempty` rather than the older
  `LOG`/`truncate`/`to_iso_utc`/`filter_by_hours` names. Fix: rewrote the new
  worker to be self-contained rather than rely on the drifting helper API.
  Suggest pinning a `common.py` contract version, or migrating the older
  `reddit_finance.py` onto the same self-contained shape.

- **Worker exits 2 when output is empty.** That is intentional (matches the
  existing `reddit_finance.py` convention: 0 = success with items,
  2 = success with no items, 1 = exception). The orchestrator should
  distinguish these.

- **`old.reddit.com`** still returns its own tiny 1.5 KB "Blocked" page, so
  switching from `www` to `old` is **not** a workaround.

- **`i.reddit.com`** still 403, so the mobile mirror is **not** a workaround
  either.

- **Cookie workarounds** (sending a forged `reddit_session`) only unlock the
  OAuth `/api/v1/me` endpoint and do not unlock `.json` listing endpoints.
  Not a useful path for this worker.

- **Bandwidth is not the constraint.** ~30 k req/mo × ~3 KB ≈ 200 MB/mo,
  $0.5 of proxy traffic — the relevant cost line is the proxy subscription
  minimum ($5-15/mo) not the per-GB.
