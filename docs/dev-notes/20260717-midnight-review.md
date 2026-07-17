# 2026-07-17 凌晨复盘报告

## 1. 当前整体状态

- **ECS 服务**: 已恢复并部署到 `5f5f07b`，backend / nginx / postgres / redis 均 healthy。
- **Celery worker**: 为加速 A 股 2026-07-15 指标补齐，已临时切换为仅监听 `indicator` 队列（4 并发）。`cninfo` 队列有 17 个任务被暂停，不会丢失。
- **指标重算**: `etf_indicator` 2026-07-15 已有 463 条记录，目标应补齐到 7000+。4 个 worker 正在用 SQL backend 处理，每个 chunk 20 codes 约 40 秒，预计还需 1.5~2 小时完成。
- **数据对齐**: `instrument_daily_bar` 最新为 2026-07-15，`etf_indicator` 正在追赶。

## 2. 本次会话已解决的问题

| 问题 | 根因 | 修复 |
|------|------|------|
| GitHub Actions deploy #255-#258 失败 | `/data` 磁盘满导致 Docker 构建/日志写入失败 | 清理旧镜像与 build cache，释放约 9GB 空间 |
| cninfo PDF 下载 `Permission denied` | celery-worker 以 `app` 用户运行，但 `CNINFO_PDF_DIR` 未在 entrypoint 中 chown 给 app | 修改 `scripts/docker-entrypoint.sh` 在启动时 chown/chmod `CNINFO_PDF_DIR`；临时在 ECS 上 chown 已解决当前任务 |
| 指标重算极慢 | 生产环境未设置 `INDICATOR_BACKEND=sql`，走 pandas 路径 | 在 `.env` 和 `docker-compose.yml` 中默认启用 `INDICATOR_BACKEND=sql` |
| indicator/cninfo 任务互相阻塞 | Celery 任务未分队列，全部堆积在默认 `celery` 队列 | 配置 `task_routes`，indicator 走 `indicator` 队列，cninfo 走 `cninfo` 队列；worker 命令保留监听三队列 |
| SQL backend 查询失败（1e85e9f） | 优化后的 `windowed` CTE 缺少 `amount`/`volume` 列 | 已修复并部署到 `5f5f07b` |
| SQL backend 仍然慢 | `full_history=False` 时仍扫描每个 code 全部历史 bars | 已优化为只读取最近 500 条 bars（`5f5f07b`） |

## 3. 仍然未解决的问题

1. **指标重算尚未完成**: `etf_indicator` 2026-07-15 只有 463 条，预计还需 1.5~2 小时才能补齐到 7000+。
2. **celery-worker 临时改为 indicator-only**: 完成后必须恢复为 `-Q celery,indicator,cninfo`，否则 cninfo 任务会无限积压。已写入 memory。
3. **cninfo 队列 17 个任务暂停**: 这些任务是之前触发的 PDF 下载/回填，待 indicator 补齐后恢复消费。
4. **ECS 磁盘空间仍紧张**: `/data` 40G 已用 34G（90%），需要长期监控和自动清理策略。
5. **SQL backend 仍有优化空间**: chunk size 20 导致大量小查询，可考虑增大到 100/200 进一步提速。
6. **cninfo 任务长事务问题**: `backfill_cninfo_reports` / `download_cninfo_pdfs` 整个 shard 在一个事务中，产生大量 `idle in transaction`，建议每个 stock 处理后 `commit()`。
7. **SSH 连接不稳定**: 本会话中多次被 `Connection reset by peer`，影响操作效率，可能与 ECS 安全组/防火墙/负载有关。

## 4. 处理失败或做得不够好的地方

1. **误删了 9ac6dd9 镜像**: 第一次清理磁盘时使用 `docker image prune -a -f`，删除了刚构建好的 `ad-research:9ac6dd9` 镜像，导致需要重新构建。
2. **SQL 优化引入了回归**: 第一次 `windowed` CTE 缺少 `amount`/`volume`，导致 SQL backend 查询失败并回退到 pandas，浪费了时间和一次部署。
3. **git push 多次失败**: 网络不稳定导致 push 失败两次，第三次才成功。
4. **监控脚本多次写错**: 通过 ssh 传输复杂脚本时引号嵌套错误，最终未能可靠启动后台监控。
5. **没有第一时间检查磁盘**: deploy 失败后应该先检查磁盘空间，而不是反复重试 update.sh。
6. **任务粒度太大**: `calculate_indicators` 一个任务处理整个市场（7081 codes），即使 4 worker 并行也慢；未来应考虑按 code 区间或按市场拆分为更细粒度任务。

## 5. 必须立即跟进的待办

1. **等待并验证指标补齐**: 每 10~15 分钟检查 `etf_indicator` 2026-07-15 行数，直到接近 7000。
2. **恢复 celery-worker 三队列监听**: 指标补齐后执行：
   ```bash
   ssh -i ~/.ssh/claude_aliyun root@47.239.13.111
   sed -i 's/-Q indicator/-Q celery,indicator,cninfo/' /data/ad-research/deploy/aliyun-ecs/docker-compose.yml
   cd /data/ad-research/deploy/aliyun-ecs
   docker compose up -d celery-worker
   ```
3. **清理 ECS 临时文件**: `/tmp/migrate*.py`, `/tmp/monitor.sh`, `/tmp/indicator_progress.log`, `/tmp/explain.sql` 等。
4. **考虑设置磁盘自动清理**: 例如 cron 每周运行 `docker image prune -a -f` 和 `docker builder prune -f`。
5. **考虑增大 INDICATOR_SQL_CHUNK_SIZE**: 在 `.env` 中设置 `INDICATOR_SQL_CHUNK_SIZE=100` 或 `200` 测试性能。
6. **修复 cninfo 任务事务**: 每个 stock 处理后 `db.commit()`，减少 `idle in transaction`。

## 6. 代码变更总结

本次会话提交到 main 的 commit：

- `9ac6dd9` feat(celery): 为 indicator/cninfo 任务配置独立队列路由
- `e1fc3eb` ops(compose): 默认启用 INDICATOR_BACKEND=sql 提升批量指标计算速度
- `9546904` fix(docker): entrypoint 确保 CNINFO_PDF_DIR 对 app 用户可写
- `1e85e9f` perf(sql-indicator): full_history=False 时只读取最近 500 条 bars 加速最新日指标计算
- `5f5f07b` fix(sql-indicator): windowed CTE 缺少 amount/volume 列导致查询失败

所有代码已 push 到 GitHub。
