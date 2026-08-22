# 2026-08-22 PG 备份链 18 天停摆修复 + 磁盘定期清理落地

> 触发：磁盘审计子 agent 发现 /data/backups/postgres 最新备份停在
> 2026-08-04，18 天零备份。两个子 agent 并行处理（备份链 / 磁盘清理），
> 主会话装 cron + 修仓库脚本。

## 一、PG 备份链：根因与修复

**根因（一句话）**：8/4 事故修复时把 backend 容器探针从「完整试跑一次
pg_dump」改成 `pg_dump --version`——backend 镜像内置 pg_dump 17，探针
必中，而该分支用 `-h localhost` 连库；容器内 localhost 指向容器自身
（postgres 是独立容器）→ connection refused → 只产出 20B 空 gzip 被
100MB 底线校验删除。**8/4 起连续 18 天每天 02:30 准时失败**，cron/
daemon/脚本调度全都正常，是分支逻辑钉死了错误路径。旧探针会完整试跑、
连不上就失败、自然跌进 postgres 容器分支成功导出——探针"优化"反而
引入了必败分支。

**修复**（`/root/backup_postgres.sh`，改前备份 `.bak-20260822`）：
1. 分支顺序改为 **alloyresearch-postgres 容器优先**（容器内本地导出，
   pg_dump 16 与 server 版本一致，零网络依赖）
2. backend 分支降保底，主机从 `localhost` 改为 compose 服务名
   `postgres`（DNS 已验证解析 172.22.0.4）
3. 仓库 `scripts/backup_postgres.sh` 带同一 bug（commit 1559ac7 引入），
   已同步修复（cron 调的是 /root 副本，仓库版是防复发）

**验证**：手动跑通 `ad_research_20260822_210124.sql.gz` **3.7G**，
`gunzip -t` 全量 GZIP_OK，头部 `-- PostgreSQL database dump` + 尾部
`\unrestrict` 终结标记齐全。cron 行无需改动，当晚 02:30 自动生效。
retention（5 天）顺带清掉 8/4 前 5 份旧备份（-12G）。

**口诀**：容器里 `-h localhost` 永远指向容器自己——跨容器连库必须走
compose 服务名；探针要验证「真实依赖路径」而不是「二进制存在」，
`--version` 探针验证不了网络/主机名/认证任何一项。

## 二、磁盘定期清理：机制全景与新增 janitor

| 机制 | 频率 | 覆盖 |
|---|---|---|
| update.sh 部署清理 | 每次部署 | 保留当前 sha+latest；builder prune 72h |
| docker-cleanup.sh（cron 周日 03:00） | 每周 | dangling/builder `-a` 168h/ad-research 留 3 sha/PROTECTED_IMAGES |
| **disk-janitor.sh（cron 周日 04:30，本次新增）** | 每周 | dangling、ad-research 留 2 sha（含 previous_head 回滚指针）、builder until=168h（不加 -a）、白名单核验、df 前后对比日志 |
| site_watchdog | 每 5 分钟 | 拨测+自愈，不管磁盘 |

- 新脚本 `/root/disk-janitor.sh`：`flock` 自锁 + **部署锁
  `/var/run/ad-research-deploy.lock` 被持有时跳过**；只 `image prune -f`
  绝不 `prune -a`（2026-08-04 nginx 被删事故教训）；PROTECTED_IMAGES
  复用 `:__keep__` tag 技巧
- cron：`/etc/cron.d/disk-janitor` = `30 4 * * 0`（已装，与 03:00 的
  docker-cleanup 错开且幂等兼容）
- 实测：释放 ~1.4G（悬空镜像 734M + runner 旧版 2.335.1 的
  bin/externals 674M，进程确认在 2.336.0 上），七容器全程 Up，
  /data 51%→50%；叠加备份 retention 的 12G，**一天净释放 ~13.4G**

**遗留**：
1. containerd 7.4G 缓增——只观察，严禁裸 prune（2026-08-02 教训）
2. docker-cleanup（留 3 sha）与 janitor（留 2 sha）并存无副作用；
   想单一口径可停前者
3. **备份失败无告警**——18 天零产出无人察觉。待办：backup.log 的
   `[ERROR]` 接 site_watchdog 告警通道
4. 当前只剩 1 份备份，当晚 cron 后恢复冗余

## 相关

- [[20260804 站点断访20h事故]]（裸 prune 删 nginx）
- [[20260805 首页/研报故障+满盘停摆复盘]]（update.sh 自动清理由来）
- [[20260719-orchestrate-image-fix]]（PROTECTED_IMAGES 由来）
- [[20260821-digest-title-dedup]]（同日 MiniMax 额度耗尽发现）
