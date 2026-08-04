# 2026-08-04 站点断访 20h 事故：nginx 被磁盘自愈 prune 删除

> 时间线、根因、处置与加固全记录。事故日 2026-08-04（CST），修复人 Claude（Aidan 报告后介入）。

## TL;DR

`/data` 磁盘 8/3 起越过 90%（峰值 94%）→ runner_healthcheck 每 5 分钟 `docker system prune -af` → nginx 凌晨陷入崩溃-重启循环（exit 1，23:20→01:40 重建 5 次）→ 容器停止后被 prune 整体删除 → **站点断访约 20 小时无人知晓**，用户报告后 `docker compose up -d nginx` 一把恢复。同日凌晨 pg 备份也因探针设计缺陷产出 20B 空文件且未报警。

## 时间线（CST）

| 时间 | 事件 |
|---|---|
| 8/3 08:00 起 | /data ≥90%（94%），runner_healthcheck 每 5min `docker system prune -af --filter until=24h` |
| 8/3 23:20 → 8/4 01:40 | nginx 五次反复重建/重启（dockerd sbJoin 日志），exit 1 崩溃循环 |
| 8/4 02:27 | 容器 b76592e2 以 10-20s 间隔重启（restartCount 4→7） |
| 8/4 ~02:00 后 | nginx 容器从停止态被 prune 删除，**站点全黑** |
| 8/4 02:30 | pg 备份探针链全部失败 → 回退本地 pg_dump（不存在）→ pipefail 中断，留 20B 空 gzip，旧备份清理未执行 |
| 8/4 22:05 | 用户报告网站无法访问 |
| 8/4 22:07 | `docker compose up -d nginx` 恢复，https 健康 200 |

## 根因分析

### 主因：激进 prune 策略（scripts/runner_healthcheck.sh 旧版）

- 阈值 90% 对 120G 盘意味着还剩 12G 就触发**每 5 分钟** `system prune -af`；
- `-af` 会删「未被任何容器引用的镜像」——崩溃-重启循环窗口内容器状态不稳定，一旦容器进入 Exited 并被 container prune 收走，下次重启即告失败；
- 容器消失后 `web_dist` 命名卷变为 unreferenced——若此时叠加 `--volumes` 深 prune（旧脚本 /var/lib/docker ≥95% 分支），**前端构建产物也会被删**，故障会升级为「需重新部署才能恢复」。

### 次因 1：pg 备份脚本探针设计缺陷（scripts/backup_postgres.sh 旧版）

- 探针 = 完整跑一次 `pg_dump > /dev/null`：每晚白跑 1-2 次全库导出（3.3G IO、数分钟），且在容器重启窗口探针失败直接跌进本地 pg_dump 分支；
- `set -euo pipefail` 下 pg_dump 不存在 → 管道 127 → 脚本中断，**`-s` 检查都没跑到**，20B 空 gzip 残留占用 retention 槽位；
- 失败无任何告警渠道。

### 次因 2：站点级监控空白

runner_healthcheck 只盯 runner 主机（磁盘/daemon/锁），没有任何「站点本身是否可达」的拨测。nginx 死后 20 小时无告警。

## 处置记录

1. `docker compose up -d nginx` 立即恢复（22:07），外网 www.alloyresearch.net /health 200；
2. 清理备份目录：删 20B 残缺文件 + 超期 7/29、7/30 两份（释放 6.5G，/data 87%→82%）；
3. 手动补跑 8/4 备份（~3.2G）。

## 加固措施（本次全部落地）

### A. runner_healthcheck.sh 受控 prune（仓库 + ECS /root 已同步）

- /data 阈值 90% → **95%**；
- 容器只清 72h+ 且 `label!=com.docker.compose.project=aliyun-ecs`（栈内容器停止也留尸排查）；
- 镜像：先悬空层，未引用镜像 168h+ 才清（崩溃循环中的容器镜像受保护）；
- **永不裸 `--volumes`**；深清分支（/var/lib/docker ≥97%）volume prune 也带 compose 标签保护；
- 生效路径：cron 已改指 `/root/runner_healthcheck.sh`（**不碰 /opt 工作树**，tripwire #5）。

### B. backup_postgres.sh 修复（仓库 + ECS /root 已同步）

- 探针改 `pg_dump --version`（廉价，只验存在性）；
- 产物加 `MIN_BACKUP_BYTES`（默认 100MB）底线校验；
- 失败即删残缺文件 + exit 1（不再静默残留）；
- cron 已改指 `/root/backup_postgres.sh`。

### C. 新增 site_watchdog.sh（仓库 scripts/ + ECS /root + cron.d）

- 每 5 分钟外部视角探 `https://www.alloyresearch.net/health`；
- 连续 2 次失败 → 查 nginx 容器，非 running 一律 `docker compose up -d nginx` 自愈（容器被删也能重建）；
- 自愈失败/恢复 → `docker exec alloyresearch-backend` 走 `NotificationService.send_etl_alert('site_watchdog', ...)` 通知全部 active admin 渠道（复用存量配置，零新凭据）；
- 告警节流 30 分钟/次；
- 日志 `/var/log/site-watchdog.log`，cron `/etc/cron.d/ad-research-site-watchdog`。

## 排障口诀（下次站点不可达）

1. `docker ps -a | grep nginx` —— 容器在不在；
2. 不在 → `cd /opt/ad-research/deploy/aliyun-ecs && docker compose up -d nginx`；
3. 在但不通 → `docker logs alloyresearch-nginx --tail 50`；
4. 顺便 `df -h /data`：≥90% 就是高危区，先看 `/var/log/runner-health.log` 最近有没有 prune 记录；
5. `tail /var/log/site-watchdog.log` 看拨测连续失败从何时开始 = 断网起始点。

## 遗留 TODO

- [ ] /data 长期扩容或清理策略（containerd 49G + docker 35G，cninfo PDF 14G 待 B4 验证后删）；
- [ ] 备份成功/失败本身也接 send_etl_alert（当前只看日志）；
- [ ] 邮箱 163 授权码用户配置后，site_watchdog 告警才真正到邮件（当前走已配置的 webhook 渠道）；
- [ ] nginx 凌晨 exit 1 崩溃循环的确切触发未完全定位（疑似 prune 抽走依赖资源；watchdog 已兜住后果）。
