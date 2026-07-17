# 2026-07-17 /data 磁盘满导致 Redis 写失败、健康检查 degraded

> 关联文档：[[20260717-deploy-health-celery-followup]]、[[20260712-celery-worker-runbook]]

---

## 1. 现象

- 时间：2026-07-17 约 12:46 UTC 部署成功（GitHub Actions #273）后，过了数小时。
- 外部访问 `https://www.alloyresearch.net/health` 返回：
  ```json
  {
    "status": "degraded",
    "ready": false,
    "db": "error: OperationalError",
    "redis": "error: ResponseError"
  }
  ```
- `docker compose ps` 显示：
  - `alloyresearch-backend` unhealthy
  - `alloyresearch-postgres` unhealthy
  - `alloyresearch-redis` healthy（但写操作被禁用）

## 2. 根因

- ECS 数据盘 `/dev/vdb`（挂载 `/data`）**100% 满**：
  ```text
  /dev/vdb  40G  38G  0  100% /data
  ```
- Redis 启用 RDB + AOF 持久化，RDB 后台保存时因 `No space left on device` 失败，触发 `stop-writes-on-bgsave-error`，导致所有写入命令返回 `MISCONF Redis is configured to save RDB snapshots...`。
- backend `/health` 的健康检查会尝试写 Redis（分布式锁 / 计数器），命中写错误后报 `ResponseError`；DB 侧同样因磁盘满出现 `OperationalError`。
- 磁盘满的构成（清理前）：
  | 项目 | 大小 |
  |---|---|
  | Docker Images | 7.9 GB |
  | Docker Build Cache | 7.3 GB |
  | Docker Local Volumes | 21.5 GB |
  | 其中 `aliyun-ecs_postgres_data` | 11.9 GB |
  | 其中 `aliyun-ecs_cninfo_pdfs` | 8.0 GB |
  | 其他日志/Runner 产物 | 约 2 GB |

## 3. 修复过程

1. 检查磁盘使用：`df -h` 确认 `/data` 100%。
2. 清理 Docker 未使用镜像与构建缓存：
   ```bash
   docker image prune -af
   docker builder prune -af
   ```
   共释放 **4.817 GB**。
3. 清理后 `/data` 剩余 **4.2 GB**，Redis 恢复写能力，Postgres 健康检查恢复。
4. 重新验证 `/health`：
   ```json
   {
     "status": "ok",
     "ready": true,
     "git_sha": "0985d56",
     "db": "ok",
     "redis": "ok",
     "data": { "status": "ok", "latest_date": "2026-07-15" }
   }
   ```

## 4. 当前状态

- `/data` 使用率从 100% 降至 **89%**，可用 4.2 GB。
- 所有容器 healthy：backend、celery-worker、postgres、redis、nginx。
- 队列正常消费，`cninfo` PDF 回填继续。

## 5. 后续加固与监控

| 优先级 | 措施 | 说明 |
|---|---|---|
| P1 | 增加磁盘告警 | 在 `/data` 使用率达到 80% / 90% 时发送告警（钉钉/邮件），避免 100% 才发现 |
| P1 | 限制容器日志大小 | `docker-compose.yml` 增加 `logging: options: max-size: 50m, max-file: 3`，防止单容器日志无限增长 |
| P2 | 评估 cninfo PDF 保留策略 | `aliyun-ecs_cninfo_pdfs` 已达 8 GB，需确认是否所有 PDF 都需要长期保留，或按日期归档到 OSS |
| P2 | Postgres 定期 VACUUM / 归档 | `aliyun-ecs_postgres_data` 11.9 GB，检查是否有大量过期 WAL、临时表或索引膨胀 |
| P2 | Docker 镜像 tag 保留策略 | 目前保留多个历史镜像，建议只保留最近 3-5 个 tag，旧 tag 自动清理 |
| P3 | Redis 持久化容错 | 可考虑在磁盘短暂满时降级为只告警而不完全阻塞写（需评估数据安全） |

## 6. 操作命令速查

```bash
# 1. 查看磁盘使用
df -h /data

# 2. 查看 Docker 占用
docker system df

# 3. 查看各 volume 大小
for v in $(docker volume ls -q); do
  size=$(docker run --rm -v ${v}:/v alpine du -sh /v 2>/dev/null | cut -f1)
  echo "$size $v"
done | sort -hr

# 4. 安全清理未使用镜像与构建缓存（不删 volume）
docker image prune -af
docker builder prune -af

# 5. 危险：清理 volume 前务必确认数据已备份
docker volume prune -af   # 仅删除未被容器引用的 volume

# 6. 查看 Redis 持久化错误
docker logs --tail=30 alloyresearch-redis

# 7. 生产健康检查
curl -sS https://www.alloyresearch.net/health | python3 -m json.tool
```

## 7. 决策与回滚

- **决策**：本次磁盘满属于运维事件，未修改业务代码；清理镜像/缓存后服务恢复。
- **风险**：如果未来 PDF 或 Postgres 持续增长，40 GB 数据盘将再次告急，需按上表加固。
- **回滚方式**：本次只删除了未使用的 Docker 镜像和构建缓存，不影响运行中容器与 volume；无需回滚。
