# 2026-07-20 ECS 生产环境全面排查报告与优化落地记录

> **注**：本文为 2026-07-20 的时点记录，部分内容可能已过时。

> 方法：10 个只读排查 agent 并行上 ECS（ssh ad-research）覆盖 cron/Docker/backend/celery/采集 agent/PG+Redis/nginx/数据新鲜度/磁盘日志/APScheduler 十域；
> 随后 11 个修复 agent 并行落地（9 个代码修复 + 2 个服务器操作）。本文记录排查结论、已落地修复与遗留事项。

## 一、排查结论总览

| 域 | 评级 | 核心发现 |
|---|---|---|
| cron/定时脚本 | 有故障（已止血） | 采集 8 源曾全挂 8 天零告警；**生产库零备份**；死脚本/死进程若干 |
| Docker/资源 | 健康有隐患 | 45GB 镜像+缓存清不掉（清理策略失效）；hermes orphan 容器 |
| backend 容器 | 有隐患 | 新闻情绪流水线 24h 打爆连接池 26+ 次，30s 情绪任务反复失败 |
| celery worker | 有隐患 | 5 条周日任务滞留 unacked（自动重放）；部署即丢任务审计能力 |
| 采集 agent | 有隐患偏严重 | 镜像误删事故 7/19 重演 16h；reddit/x/stocktwits 慢性失败（WAF 封 IP） |
| PG + Redis | 有隐患 | sentiment_data 七成写入被 FK 丢弃；不明角色探测 FATAL |
| nginx + TLS | 有隐患 | **SSE 专用 location 路径漏 /v1 成死配置**，长连接 60s 被掐 |
| 数据新鲜度 | **有故障** | 美股日线断 17 天；crypto 日线假成功零落库；A 股 ETF 7/16 起连续失败 |
| 磁盘/日志 | 有隐患 | cninfo PDF 3 天涨 12.6GB（全量需 100GB+，超磁盘） |
| APScheduler | 有故障 | a_share_daily_etl 代码 bug 连续失败；宏观三件套中断 3-4 天 |

## 二、已落地修复

### 代码修复（本地仓库，待 commit + 部署生效）

1. **crypto 日线假成功（P0）**— 根因：api.binance.com 在阿里云被地域封锁，请求失败被静默吞掉。
   `binance_provider.py` 加 `data-api.binance.vision` 官方容灾 host + 全失败抛 `DataProviderError`；
   `crypto_daily.py` 空结果置 failed（触发 ETL 告警）；kline 日期解析改 UTC。新增 8 测试。实测容灾 host 取回真实 K 线。
2. **美股日线断供 17 天（P0）**— 根因：Tiingo 正常但 yfinance 被 Yahoo 429 限流（ECS 基本不可用），双源同时空返回。
   provider 错误信息明确化 + 降级策略修复（3 文件 + 6 测试）。
3. **A 股 change_pct bug（P0）**— 定位确认修复已在生产镜像（commit 1d5b8f0，7/18 部署），7/18 重试失败是部署时间差。
   补充编译级回归测试 3 个（`test_data/test_a_share_daily_upsert.py`）。**残留**：`a_share_stock_daily.py:114` 同款隐患未修（见遗留）。
4. **DB 连接池耗尽（P1）**— 两类长持连接：SSE 生成器把 session 押过 `yield` 挂起窗口（stream.py）；
   4 个情绪批任务把 SELECT 连接押进分钟级 LLM 阶段（scheduler_sentiment.py）。修复 + pool 10+20 调 15+30。
   新闻爬虫 7/19 17:39 停止落库即此的连锁反应。
5. **sentiment_data FK 七成丢弃（P1）**— 根因：LLM 产出原始 ticker（`BA`）与 FK 目标内部代码（`BA.US`）不匹配。
   `_persist` 加 `symbol_mapper.internal_code` 映射 + etf_info 预查过滤 + 提交顺序修正；finnhub 路径同修。
6. **4 个新闻源静默（P1）**— 根因：robots.txt 检查用 urllib **无超时**，ECS 访问 WAF 站点挂起 → max_instances=1 后续 tick 全跳过；
   且 wrapper 吞错记假成功。robots.py 重写为 httpx 10s 硬超时；4 个 wrapper 异常改 re-raise 记 failed。
7. **research_reports_daily（P2 确定性 bug）**— service 方法内部已落库返回 int，pipeline 对 int 迭代。
   拆出 fetch-only 方法，upsert 只发生一次。6 测试。
8. **sw_industry 双 bug**— 排查确认两个 bug 均已被 commit 18db812 修复（numpy 2.x repr `np.float64(...)` 被 psycopg2 当 schema 限定名），
   属未部署而非未修复。零 diff。**注意**：psycopg2 + numpy 2.x 是系统性地雷，建议全库审计 insert 参数来源。
9. **nginx SSE 死配置（P1）**— 旧 location `/api/notifications/stream` 永不命中；改正则 `~ ^/api/v1/(.*/)?stream(/|$)`
   统一 proxy_buffering off + 86400s 超时（双 server 块）；新增 `log_format main_timing`（rt/urt）。
10. **compose 治理**— celery worker 加 `-E`（task events 可审计）；celery env 移除 `ENABLE_SCHEDULER=true` 地雷（backend 保留）。
11. **API key 日志脱敏（P2 安全）**— tiingo/fmp/finnhub/fred 四个 provider + backfill 脚本的 URL key 统一 `***` 脱敏。
    **生产已泄漏的 key 建议轮换**。
12. **crypto 指标任务每天静默跳过（P2）**— 根因：锁等待窗口错位 5 分钟（ETL 锁 08:05+3600s vs 指标任务 08:30+1800s）。
    wait_timeout 2100 + etl_log job_name 按市场映射（修复运维看板 never_run 观测黑洞）。
13. **backup_postgres.sh 修复**— 脚本三处问题（无执行权限、backend 容器内无 pg_dump、宿主机未装）导致从未跑过；
    加 `docker exec alloyresearch-postgres pg_dump` 分支，仓库与服务器同步修复。

### 服务器操作（已生效）

14. **数据库备份体系（P1，从零到有）**— 每日 02:30 cron 已安装并**真实跑通两次**：
    `/data/backups/postgres/ad_research_20260720_*.sql.gz`（2.2G，gzip -t 通过）；crontab 已备份（/root/crontab.bak-20260720）。
15. **Docker 清理体系重写**— 旧 `until=168h` 策略对高频部署永远回收 0B；改为「保留在用 + previous_head 回滚版 + 最新 3 个」
    白名单策略（保留 7/19 的 alloyresearch-agent 保护逻辑）。实跑回收 **23GB**（/data 62%→42%）；
    顺带清理 github-runner 旧版本 535MB、孤儿卷 ×2。backup：/root/docker-cleanup.sh.bak。
16. **死进程清理**— recalc_monitor.sh ×2（13 天）+ /tmp/monitor_indicator.sh（查固定日期 7/15 已无意义）已 kill。
17. **僵尸 etl_log 清理**— `id=32754 cninfo_reports_daily` 僵尸 running 标记 failed（Celery 任务硬崩溃未回写，见遗留）。

### 排查确认无需修的

- alembic current = p1r4s0t7u8v9（线上 head 正确）；单实例调度确认（celery 不跑 lifespan）
- 周日关键任务（池周报 ×8、ETF 扫描、信号 22718 条、评分）全部正常
- A 股日线/指标（100% 覆盖）/期货数据新鲜度正常；Redis/PG 容量与锁健康
- TLS 证书在期（至 2026-09-30）；unacked 5 条消息会按 visibility_timeout 自动重放，无需干预

## 三、部署与验证清单（按时间序）

- [ ] **commit + push 本批修复**（两轮共 ~100 文件），deploy.yml 自动部署；nginx.conf 变更需 recreate nginx 容器
- [ ] 部署后验证 `/health` git_sha、`docker exec alloyresearch-nginx nginx -t`
- [ ] **今日 15:30（周一）盯 a_share_daily_etl**：change_pct 修复首次真实交易日检验
- [ ] 部署后补跑缺口：crypto 断供 ~8 天（按 target_date 逐日补）、确认 7/17 A 股 ETF 行是否需回补（连带指标/评分重算）
- [ ] 次日 09:05 后查 etl_log：`crypto_daily_etl` 与 `crypto_indicator_calculation` 应各有当日记录
- [ ] 观察 QueuePool timeout 是否归零（判断 15+30 是否足够）
- [ ] 7/26（周日）03:00 新版 docker-cleanup.sh 首次 cron 实战，当天复核 alloyresearch-agent 镜像存活

## 四、遗留事项（需决策/排期）

### P1
- [ ] **采集故障无告警通道**：orchestrate 连续非零 exit 接通知 webhook（平台已有 notification 体系）——8 源全挂 16h 无人知的根因
- [ ] **reddit/x/stocktwits 三源 WAF 封 IP**：需代理资源或标记 deprecated 停止空转（非代码可解）
- [ ] **宏观三件套（global_indices/china_macro/fred）中断 3-4 天**：执行体身份存疑（注册时间与 etl_log 运行时间不符），今日 09:30/16:00 窗口观察后定位
- [ ] **a_share_stock_daily.py:114 同款 change_pct 隐患**（个股日终 16:00 任务）按 a_share.py 模式修
- [ ] **cninfo PDF backfill 范围管控**：11.1 万公告 vs 1.1 万 PDF，全量需 100GB+ 超磁盘，需限定日期窗口 + 磁盘水位告警
- [ ] **美股日终结构性脆弱**：Tiingo 免费层 50 只/天轮询 + yfinance 被限流，需评估付费源或东财/新浪美股源
- [ ] **scheduler_fetch_full_content.py** 同款 session 跨慢 I/O 持有（连接池修复的遗留点）
- [ ] **已泄漏 API key 轮换**（Tiingo/FMP/Finnhub/FRED）

### P2
- [ ] TLS 证书无自动续期（9/30 到期前手动续或上 acme.sh）
- [ ] overnight_v2 无调度无监控（heartbeat 7/19 13:24 停止），确认是否每日应跑并纳入 cron
- [ ] xueqiu cookie 失效（cookie_rejected），需 scripts/inject_cookies.py 重注
- [ ] hermes orphan 容器：确认用途，纳入编排或清理；补日志轮转
- [ ] celery 任务硬崩溃不回写 etl_log 的兜底（id=32754 暴露的问题）
- [ ] base.py 空 extract 仍 success 的统一约定（10 个 pipeline 受影响面，需设计）
- [ ] 港股/日股管线不存在（大功能，属 roadmap）
- [ ] postgres 不明角色探测 FATAL：可临时开 log_connections 抓来源
- [ ] 扫描器噪音：已知扫描路径 return 444 或静态 location 限流
- [ ] fed_intl rc=0 空占位与真实条目不区分（status_report 改进）

## 五、追加 tripwire（2026-07-20 晚，部署 run 29709418777 失败实录）

**教训：不要在 `/opt/ad-research` 工作树上直接改文件，哪怕只是服务器侧的热修。**

本次 backup_postgres.sh 的服务器侧热修（agent 同步改了仓库并验证 diff 一致）仍让工作树
`git status` 变脏，deploy.yml step 2 的脏检查（tripwire #1 保护）直接 bail，第一次部署失败。
正确姿势：服务器热修后立刻 `git checkout -- <file>` 还原（修复已在仓库里，reset 后自然生效），
.bak 文件放 `/root/` 而非工作树内。

另：本地网络对 GitHub 的访问可能整体抖动（443 全部 IP 超时但 SSH 22 通）。应急 push 路径：
`git bundle create x.bundle origin/main..main` → scp 到 ECS →
`git fetch x.bundle main && git push origin FETCH_HEAD:refs/heads/main`（凭据在
`/data/ad-research/.git-credentials`，push 不触碰工作树，不影响部署脏检查）。
