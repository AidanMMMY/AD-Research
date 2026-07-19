# Orchestrate_v2 镜像丢失根因 + 修复 Runbook

**日期**：2026-07-19
**触发**：8 个 source 全部 7-11 后没刷过，`orchestrate_v2` cron rc=66。
**作者**：总管 Agent
**影响**：所有 quick/logged_in 抓取源 191h 没刷新 → 必须排查 + 修复 + 加白名单。

## 背景

`agent/scripts/orchestrate_v2.py` 每小时 :47 调 8 个 worker
(eastmoney_news / gov_china / fed_intl / stocktwits / cls /
xueqiu_playwright / x / reddit_curl_cffi)。
每个 worker 通过 `agent/scripts/run_worker.sh` → `docker run alloyresearch-agent:latest ...`
起一次性容器。镜像不存在时 `docker run` rc=125，
被 orchestrate_v2 统一包装成 66（`exit code 66` 来自 run_worker.sh 的 "image not found" 分支）。

## 根因

`scripts/docker-cleanup.sh` 周日 02:00 跑（cron 触发），
里面有这一行：

```bash
docker image prune -a --filter "until=168h" -f
```

- `-a`：所有 unused 镜像
- `--filter until=168h`：7 天没被任何容器引用过的镜像

`alloyresearch-agent:latest` 是 *按需启动* 的一次性 worker 镜像，
周末没有 cron 触发就 0 次容器引用 → 周日就被 prune 干掉。
下次周一 :47 cron 触发时，镜像已经消失 → 全部 worker rc=66。

**确认时间线**：

| 日期 | 事件 |
|---|---|
| 2026-07-11 (周六) 22:47 | 最后一次正常 cron（fetched_at 都在 7-11 10:5x） |
| 2026-07-12 (周日) 02:00 | docker-cleanup.sh 周日清理跑，`alloyresearch-agent:latest` 被 prune |
| 2026-07-12~07-19 | cron 每小时 :47 跑但全部 rc=66 |
| 2026-07-19 11:xx | 总管 Agent 排查 status_report critical 告警时发现 |

## 修复（双保险）

### 修复 1：`run_worker.sh` 找不到镜像时自动 build

`agent/scripts/run_worker.sh` 加 build fallback 分支：

```bash
if ! docker image inspect "$AD_AGENT_IMAGE" >/dev/null 2>&1; then
  AGENT_ROOT="${AD_AGENT_ROOT:-/root/ad-research/agent}"
  DOCKERFILE="$AGENT_ROOT/Dockerfile"
  if [[ ! -f "$DOCKERFILE" ]]; then
    echo "[run_worker] ERROR: image $AD_AGENT_IMAGE not found locally and Dockerfile missing at $DOCKERFILE" >&2
    exit 66
  fi
  echo "[run_worker] image $AD_AGENT_IMAGE missing, building from $DOCKERFILE ..." >&2
  if ! docker build -t "$AD_AGENT_IMAGE" -f "$DOCKERFILE" "$AGENT_ROOT" >&2; then
    echo "[run_worker] ERROR: docker build failed for $AD_AGENT_IMAGE" >&2
    exit 66
  fi
  ...
fi
```

**行为**：镜像缺失 → 自动从 `/root/ad-research/agent/Dockerfile` build → 重新跑 worker。
即使白名单没生效，单次 build 也能恢复 cron。
**潜在风险**：build 几百秒，cron worker 队列可能堆积；
若 Dockerfile 缺失 → exit 66（保持原有失败码）。

### 修复 2：`docker-cleanup.sh` 加白名单（首选）

`scripts/docker-cleanup.sh` 加 `PROTECTED_IMAGES` 数组 + tag trick：

```bash
PROTECTED_IMAGES=(
    "alloyresearch-agent:latest"
)
for img in "${PROTECTED_IMAGES[@]}"; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        # tag 成 :__keep__ 让镜像在 prune 期间被引用,不会被 -a 清掉
        docker tag "$img" "${img%:*}:__keep__" >> "$LOG" 2>&1 || true
    fi
done
docker image prune -a --filter "until=168h" -f >> "$LOG" 2>&1 || true
for img in "${PROTECTED_IMAGES[@]}"; do
    if docker image inspect "${img%:*}:__keep__" >/dev/null 2>&1; then
        docker rmi "$img" >> "$LOG" 2>&1 || true          # 删原 tag
        docker tag "${img%:*}:__keep__" "$img" >> "$LOG" 2>&1 || true  # 还原
        docker rmi "${img%:*}:__keep__" >> "$LOG" 2>&1 || true         # 清 :__keep__
    fi
done
```

**tag trick 原理**：Docker `image prune -a` 跳过 *有至少一个 tag 且该 tag 名不在 pruned 列表* 的镜像。
通过 `docker tag alloyresearch-agent:latest alloyresearch-agent:__keep__`，
镜像暂时有 2 个 tag；prune -a 把没人用的 tag 清掉，但有 `__keep__` 留着的镜像不算 unused。
prune 完再 `docker rmi alloyresearch-agent:latest` + 还原 + 清 `__keep__`，
最终只留下 `:latest` 一个 tag 镜像，prune 没动它。

> **为什么不直接用 `--filter "label!=keep"`？**
> Docker prune 不支持 label-based filter。
> 试过 `docker image prune -a --filter "label!=keep"`，返回
> `Error response from daemon: No such filter: label`，所以用 tag trick。

## 部署 + 验证

### ECS 部署（已 2026-07-19 19:43 完成）

```bash
# pull + 验证
cd /opt/ad-research
git pull
bash scripts/setup_cron.sh status

# 验证白名单工作：手动跑一次 cleanup
bash /root/docker-cleanup.sh
docker images alloyresearch-agent --format "{{.Repository}}:{{.Tag}}"
# 期望：
#   alloyresearch-agent:latest
tail /var/log/docker-cleanup.log
```

### 已验证输出

```
== after ==
alloyresearch-agent:latest
== log tail ==
Filesystem      Size  Used  Avail Use% Mounted on
/dev/vdb        118G   62G   52G  55% /data
2026-07-19T19:43:45+08:00 Cleanup done
```

### 验证 build fallback（已 2026-07-19 18:30 完成）

```bash
# 模拟镜像丢失
docker rmi alloyresearch-agent:latest
# 跑 run_worker.sh 触发 build fallback
bash /root/ad-research/agent/scripts/run_worker.sh cls /data/ad-research/cls/test.json
# 期望：
#   [run_worker] image alloyresearch-agent:latest missing, building from /root/ad-research/agent/Dockerfile ...
#   [run_worker] built alloyresearch-agent:latest ok
#   ... worker 正常完成
docker images alloyresearch-agent --format "{{.Repository}}:{{.Tag}}"
# 期望：alloyresearch-agent:latest 已恢复
```

## 当前风险

1. **白名单只有 1 个 image**：未来若有新 agent 镜像加入，必须更新 `PROTECTED_IMAGES`
2. **手动 `docker image prune` 没保护**：运维同学手敲 `docker image prune -a` 仍会清掉，
   必须配套 push awareness doc。
3. **Dockerfile 路径硬编码**：`AD_AGENT_ROOT` 默认 `/root/ad-research/agent`；
   ECS 与 `/opt/ad-research` 软链不一致时需显式设 env var。
4. **build fallback 阻塞**：第一次 build ~5min（agent 镜像含 playwright + chromium），
   后续 cron 错过就堆积。

## 关联

- [[2026-07-19 Overnight Worker 监控告警 Runbook]] — status_report 首先捕获到 8 source 191h 没刷
- [[20260719-overnight-monitoring]] — memory 指针
- [[20260719-deploy-tripwires]] — runbook #4 也是 image lifecycle 相关
- `agent/scripts/run_worker.sh` lines 66-87
- `scripts/docker-cleanup.sh` lines 11-42

## 后续

1. 将 `--filter label!=keep` 标记为 "Docker 不支持" 的注释永久写进 cleanup.sh 历史。
2. 等下次手动 cleanup 跑完（周日 02:00）观察白名单实际表现。
3. 若 `alloyresearch-agent` 换成 `alloyresearch-agent:vN` 命名，
   白名单需要同步更新。
