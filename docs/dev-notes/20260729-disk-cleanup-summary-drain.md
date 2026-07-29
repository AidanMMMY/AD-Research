# 2026-07-29 磁盘清理 + 摘要 drain 全灭修复 + 回填执行记录

> 背景：晨报遗留 5 项待办，用户「全部做」指令下由主会话执行的部分。
> 同场并行：子 agent A 排查三页面对齐问题、子 agent B 排查非中文正文翻译（各自结论见对应 runbook）。

---

## 1. /data 磁盘清理：85% → 48%（释放 ~42GB）

清理前：`/dev/vdb 118G 已用 96G (85%)`。
构成：containerd 43G + docker 28G + backups 24G。

执行动作：

| 动作 | 释放 | 说明 |
|---|---|---|
| `bash /root/docker-cleanup.sh`（手动触发周日清理） | ~18G | 删除 ad-research:<sha> 旧镜像，保留容器引用 + previous_head 回滚指针 + 最新 3 个 tag（脚本 7-20 版策略） |
| `docker builder prune -af` | 26.39G | 构建缓存全量清（0 active）；下次构建变慢但安全 |
| 删除 >5 天的 postgres 备份 | ~7G | 9 份 → 6 份（7-24..7-29） |

**cron 变更**：备份保留天数 7 → 5：

```
30 2 * * * RETENTION_DAYS=5 /opt/ad-research/scripts/backup_postgres.sh >> /var/log/ad-research/backup.log 2>&1
```

注意：

- `alloyresearch-agent:latest` 当前不存在于 ECS（7-19 事件后靠 run_worker.sh 按需构建），cleanup 脚本白名单机制对它天然无副作用。
- docker 使用 containerd 镜像存储（moby namespace），清 docker 镜像会同步释放 /data/containerd。
- 备份体积增速快（一周 2.3G→3.1G，652 源入库后 news_article 膨胀），RETENTION_DAYS=5 把备份上限锁在 ~15G。

## 2. 存量回填 SQL（extraction fix §5.4，已批准并执行）

```sql
UPDATE news_article
SET full_content = NULL, full_content_fetched_at = NULL, ai_cleanup_status = NULL
WHERE fetched_at >= now() - interval '14 days'
  AND full_content ~* '(Live TV|Scan to Download|Get App|Read Time:|Sign up for)'
  AND length(full_content) > 2000;
```

**结果：UPDATE 314**。这些被导航垃圾污染的正文已由 drain job 用 7-29 新清洗器重抓。

## 3. 摘要 drain 全灭根因与修复（commit 16f6f1e）

### 现象

`news_summarize_10m` 上线 ~14h：etl_log 全 "skipped"（reason=skipped，时长 100-470s）+ 2 failed，
`summary_zh` 只有 110 行，而 `summary_zh IS NULL AND importance >= 3` 排队 5,179 篇。

### 根因链

1. `summary_service.py` 慢调用守卫：`elapsed > 30s` → 丢弃结果（**tokens 已消耗**）。
2. MiniMax（minimax-m3，minimaxi.com CN 端点）空闲时单次 2.2s，但多 drain 并发时实测 30-160s/次（服务端排队）。
3. → 并发高峰每个 tick 的 20 篇全部在 tokens 烧完后被丢弃，零进展且纯浪费。
4. m3 默认开 think（`reasoning_tokens`），进一步拉长单次延迟。

### 修复

守卫 30s → 120s（对齐 `translation_service._MAX_LLM_CALL_SEC=120`），600s tick budget 仍兜底。
测试 16/16 通过。慢但成功的响应现在会被接受。

### 翻译 drain 同场实测（12:15Z）

- 近 6h：18 success / 811 篇 ≈ **3,240/天**；近 24h `translation_generated_at` 共 2,847。
- 近 48h 非中文无 `title_zh` 积压 **5,577 且仍在涨**（流入 ~4,400/天 > 消化）。
- 同样的 >120s 丢弃在翻译侧也存在，吞吐受 MiniMax 并发排队限制。
- 后续方向（已转交子 agent B 评估）：tick 内并发 3-5 路调用 / 关闭 think / 正文翻译按 importance 分级。

## 4. 当日其他已办

- 晨报 5 项待办中由主会话执行的部分全部完成（本文件 1-3）。
- 用户配合项（JINA_API_KEY / wewe-rss 扫码 / 7 公众号链接）已在会话中给出逐步指引。

## 5. 待观察

- [ ] 摘要 drain 修复部署后 24h：`summary_zh` 行数应稳定增长（容量 ~800-2,880/天 vs 排队 5,179）。
- [ ] 翻译积压是否随子 agent B 的修复收敛。
- [ ] /data 增速： backups 5 天上限 ~15G + docker 周日清理，预期长期 <70%。
