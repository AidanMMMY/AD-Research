# 2026-07-23 Runner Host On-call Checklist

> **触发场景**：每次 push 后 GitHub Actions 出现 `Deploy to Aliyun` 连续 2 次以上
> "step 5 success + step 6 cancelled + 后续 skipped + job failure" 模式（runner cascade failure）。
>
> 7-19 之后已经发生过 #316 / #317 / #318 / #319 4 次同一个 mode，
> 说明 ECS 上 self-hosted runner host 健康是当前 deploy 链路最大单点。

---

## 1. 一键诊断（90 秒）

SSH 上 ECS runner host，按顺序跑：

```bash
# 1.1 磁盘（30 秒）
df -h
echo "---"
docker system df
echo "---"
du -sh /opt/ad-research/.buildx-cache 2>/dev/null || echo "no buildx cache"
du -sh /var/lib/docker 2>/dev/null

# 1.2 内存 + OOM（10 秒）
free -h
echo "---"
dmesg | tail -100 | grep -iE "oom|killed|memory" | tail -20

# 1.3 runner daemon 状态（10 秒）
systemctl status actions.runner.* --no-pager | head -40

# 1.4 runner 心跳 / 注册状态（10 秒）
journalctl -u actions.runner.* -n 50 --no-pager | tail -30

# 1.5 docker 进程 / 资源占用（10 秒）
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -20
```

---

## 2. 决策树（看哪个 metric 就走哪条）

### 2.1 磁盘满（df -h 显示 /data 或 /var/lib/docker > 85%）

```bash
# 立刻清理 — 安全动作
docker image prune -af               # 清所有未用 image（>1GB 常见）
docker builder prune -af --filter "until=72h"  # 清 buildx cache
docker system prune -f --volumes    # 清孤儿 volume（注意会清挂起卷）

# 检查 /opt/ad-research/.buildx-cache（deploy/update.sh 用的 buildkit 缓存）
ls -la /opt/ad-research/.buildx-cache 2>/dev/null
# 如果 > 20GB，清掉部分：
rm -rf /opt/ad-research/.buildx-cache/cache/*

# 7-17 历史：/data 满事件后已释放，但 buildx cache 可能没清理
# 保留 PROTECTED_IMAGES tag 的镜像（见 cleanup.sh）
bash /opt/ad-research/scripts/cleanup.sh --dry-run  # 先 dry-run 看会清什么
```

清理完跑：
```bash
# 触发新一轮 deploy（GitHub Actions 页面 → Re-run 或 workflow_dispatch）
```

### 2.2 OOM / 内存压力（free -h 显示 available < 2GB 或 dmesg 有 killed）

```bash
# 哪个进程最占内存？
ps aux --sort=-%mem | head -10

# 常见元凶：docker compose build 期间同时跑 8 个 worker container
# 解法：在 deploy/aliyun-ecs/update.sh 里 build 步骤前临时停 worker
docker compose stop celery-worker-indicator celery-worker-cninfo
# build 完再 start
```

如果 OOM 是 runner daemon 自身被杀：
```bash
sudo systemctl restart actions.runner.*
# 等 30s 看 daemon 是否 healthy
journalctl -u actions.runner.* -n 50 --no-pager | tail -20
```

### 2.3 runner daemon 失联（systemctl status 显示 inactive/failed）

```bash
# 找具体 service 名
ls /etc/systemd/system/ | grep -i runner
# 假设名是 actions.runner.ad-research.ad-research-etf.service
sudo systemctl restart actions.runner.ad-research.ad-research-etf.service

# 验证
systemctl status actions.runner.ad-research.ad-research-etf.service
# 应该显示 "active (running)" + "listening on http://..."
```

### 2.4 网络/registry 抖动（其他都健康）

阿里云 HTTP/2 registry 偶发 RESET_STREAM。update.sh 内部已有 retry + 5s sleep。
**额外动作**：
```bash
# 在 runner 上手动试一次 docker pull
docker pull ad-research:latest 2>&1 | tail -5
# 如果 OK，可能是当时窗口问题；触发 Re-run
# 如果失败 → 检查 aliyun ECS 容器镜像服务状态
```

---

## 3. 跑通验证

健康恢复后跑一次完整 deploy 验证：

```bash
# 在 GitHub Actions 页面 → Deploy to Aliyun → Re-run jobs
# 期望：所有 step success（最长 step 5 应在 15min 内结束，由 c4afbdd 修复保证）

# 或手动 deploy
cd /opt/ad-research/deploy/aliyun-ecs
FORCE=1 bash update.sh
# 走完 step 5 (build + stop + migrate + start) → step 6 (smoke) → step 9 (health probe)
```

---

## 4. 验证 backend 跑新代码

```bash
# 容器内 import 校验新路由存在
docker exec alloyresearch-backend python -c "
from app.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
new_routes = [r for r in routes if '/internal/' in r]
print('internal routes:', new_routes)
assert '/api/v1/internal/orchestrate-alert' in routes, '新路由未注册'
print('OK: f9445e7 deployed')
"

# 内部 API 不鉴权路径不应返回 200
curl -sS -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/api/v1/internal/orchestrate-alert
# 期望：403（无 token）或 503（INTERNAL_API_TOKEN 未配置）

# 配了 token 之后应返回 200
TOKEN=$(grep INTERNAL_API_TOKEN /opt/ad-research/.env | cut -d= -f2)
curl -sS -X POST http://localhost:8000/api/v1/internal/orchestrate-alert \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"failed_workers":[],"schedule":"all"}'
# 期望：{"accepted":true,"notification_log_id":null,"status":"skipped","failed_count":0}
```

---

## 5. 永久加固（无需 on-call）

考虑在 runner host 加：

```bash
# /etc/cron.d/runner-health
*/5 * * * * root /opt/ad-research/scripts/runner_healthcheck.sh >> /var/log/runner-health.log 2>&1
```

`runner_healthcheck.sh` 检查：
- `/data` / `/var/lib/docker` 容量 > 85% 报警
- `systemctl is-active actions.runner.*` 否则重启
- `free -m | awk 'NR==2{print $7}' < 1024` 时发飞书告警

> 这条等 f9445e7 部署上后做（依赖 NotificationLog 已可用）。

---

## 6. 已落地与未落地

- [x] 7-23 `deploy.yml` step 5/6 加 `timeout-minutes: 15`（c4afbdd）—— runner 失联时单步最多 15min 被切，不至于 22min 后才 job-level cancel
- [x] 7-23 `backend-ci.yml` Setup Python 加 `cache-dependency-path`（c4afbdd）—— 暂时未生效（GitHub service transient 仍 fail），待 re-run
- [x] 7-23 `.env.example` + `deploy/aliyun-ecs/.env.example` 加 `INTERNAL_API_TOKEN` / `ORCHESTRATE_ALERT_*`
- [ ] runner_healthcheck.sh 加固（依赖 f9445e7 上线）
- [ ] 用户 SSH 跑 §1 一次性体检（**这是当下阻塞 deploy 的唯一事项**）