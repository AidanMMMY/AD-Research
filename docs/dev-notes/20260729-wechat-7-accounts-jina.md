# 2026-07-29 JINA_API_KEY 配置 + 7 个公众号 wewe-rss 接入记录

> 背景：晨报遗留 3 项用户配合待办全部闭环。用户提供 JINA key + 完成 wewe-rss 重扫码 + 提供 7 个公众号文章链接。

---

## 1. JINA_API_KEY 配置（解锁 investing.com 全文）

### 生效路径（两个坑）

1. **env 注入方式**：生产 compose（`deploy/aliyun-ecs/docker-compose.yml`）的环境变量是**显式清单**
   （`x-backend-env` anchor），**没有 env_file 指令**——.env 只用于 `${VAR}` 插值。
   新 key 必须同时在 ① `.env` 写值 ② compose 清单登记 `JINA_API_KEY: ${JINA_API_KEY:-}`（commit `342e8eb`）。
2. **compose 目录**：生产 compose 在 `/opt/ad-research/deploy/aliyun-ecs/`，
   `/opt/ad-research/docker-compose.yml` 是 **dev 版**（backend-dev/postgres-dev/redis-dev）。
   在根目录跑 `docker compose up -d` 会拉起 dev 容器组（本次误启已全部清理，生产零影响）。
   **铁律：生产操作一律 `cd /opt/ad-research/deploy/aliyun-ecs`。**

### 验证

- 容器内 `printenv JINA_API_KEY` ✓
- 实测 investing.com 经 r.jina.ai：200 / 63KB（此前匿名 AbuseAlleviationError 封域）
- 624 篇纯标题 investing 文章由 full-content drain 自动补抓，无需手动回填

## 2. wewe-rss 重扫码（用户操作，已验证）

- 用户完成微信读书重扫码；近 2h 容器日志 `暂无可用读书账号` 0 次（此前 24h 内 16 次）
- 8 个老公众号（智谷/远川/沧海/付鹏/李迅雷/聪明投资者/北纬/晚点）恢复抓取

## 3. 7 个公众号接入（wewe-rss tRPC 全自动）

流程：`platform.getMpInfo`（文章链接→MP_WXS id）→ `feed.add` → `feed.refreshArticles`，
slug 写入 `WECHAT_RSS_FEED_MAP`（backend 重建加载）。**注意 backend 重建时机**：
CI deploy 与手动改 .env 的先后顺序决定配置何时生效，改完 .env 必须
`cd /opt/ad-research/deploy/aliyun-ecs && docker compose up -d backend` 才加载。

| 公众号 | MP_WXS id | source slug | feed |
|---|---|---|---|
| 杨国英观察 | 3016597504 | wechat_yangguoying | ✅ 30 篇 |
| 叫小宋别叫总 | 3943649816 | wechat_xiaosong | ✅ 30 篇 |
| 投资界 | 3298956650 | wechat_touzijie | ⏳ 代理持续返回 0（见下） |
| 墨子连山 | 3276873487 | wechat_mozilianshan | ✅ 30 篇（首次 0 重试后恢复） |
| 半导体行业圈 | 3598840296 | wechat_bandaoti | ✅ 30 篇 |
| 金融时报 | 3292158393 | wechat_jinrongshibao | ✅ 30 篇 |
| 泽平宏观 | 3877603551 | wechat_zepingmacro | ✅ 30 篇（原 0 产出遗留源复活） |

**feed URL 格式**：爬虫走 `/feeds/{feed_id}.json?limit=30`（JSON API），
`/feed/{id}` 是 404——排障时别用错。

**投资界待办**：`getMpArticles(MP_WXS_3298956650)` 多次返回 0（无报错，空列表）——
7-27 runbook 记载的 weread 代理抖动同症。容器每小时 `:35` CRON 会兜底重试；
若 24h 后仍 0，考虑删 feed 重新 onboarding 或换源。

## 4. 当日 CI 失败排查结论（子 agent 复核）

- 全天仅 2 个失败 run：Web CI #37/#38（71154f3/f338a9e），同为 stylelint 裸色
  `#dc2626` fallback（`ad-research/no-bare-color-values`），当天下午已由 `da073c5` 修复
- Deploy 全天全绿；当前 main（342e8eb）全部 workflow 绿，本地 check:ci 复现通过
- 流程教训：UI commit 推送前本地先跑 `npm run check:ci`（30 秒可拦截）
