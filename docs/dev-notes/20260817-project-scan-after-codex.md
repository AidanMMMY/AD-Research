# 2026-08-17 项目全面扫描报告（Codex 更新后首次接手）

> 背景：Codex 于 2026-08-06 ~ 08-08 对仓库做了 15 个 commit 的大修，本报告为扫描结论 + 生产现状 + 待办清单。

## 一、代码现状

- **本地 HEAD = origin/main = `3b08edc`**（2026-08-08），工作树干净，Codex 工作已全部 push（含我 8/5 的 `868b731` 运维 runbook 提交，共 16 个 commit 在远端）。
- Codex 15 个 commit，461 文件，+4307/-5079：
  - `dce20aa` 安全批：Chat/池/报告 IDOR、路径穿越、Webhook SSRF、未鉴权端点 +38 测试
  - `5681168` 性能批：两处 N+1 消除、9 个新索引（`e8f0a2c4d6e8`）、LLM 客户端 60s/10s 超时
  - `7757f45` 部署/CI 批：Dockerfile seed 修复、rollback.sh worker 名、生产 worker 去 docker.sock、gitignore 秘钥、deploy CI 门禁、ruff CI job、secrets-scan 覆盖 push
  - `aee0ad6` 前端批：条件 hooks 崩溃×2、a11y、SSE 4→2、echarts 按需（gzip -32%）、sourcemap 关、11 个零引用依赖卸载
  - `630535a` ruff 1371→128 + 8 个真实 bug
  - `486d79e` 功能批：**alembic env.py 从未加载 news 模型 → duplicate_of/embedding 列从未迁移 → news/learning 全页 500**（补 `f0b2d4e6f8a0/f0b2d4e6f8a1`）、SPA fallback、/strategies/templates、event-signals 路由顺序、选择器 422、详情页 404、A 股 ETL 跨日补数、指标日期锁 6h TTL、情绪批处理 NOT EXISTS 去抖
  - `84cdae9`/`e4feec0`/`3b08edc`：Yahoo 429 退避+降密度+实时缓存、yfinance 测试 7min→0.7s、纳斯达克 code 统一
- 基线（Codex 验证）：pytest 1831 passed / 2 skipped，vitest 73 passed，tsc+vite build 过，eslint 0 error，ruff 128 余。

## 二、生产现状（2026-08-17 实测）

| 项 | 状态 |
|---|---|
| 部署版本 | **`de17fe5`（8/5 我的版本）——Codex 15 个 commit 全部未部署** |
| 站点健康 | /health ok，db/redis ok，nginx 11 天 |
| 磁盘 /data | 48%（60G 余量，健康） |
| alembic | `c4d6e8f0a2b4` (head) — 与 de17fe5 一致，Codex 新迁移未 apply |
| backend | Up 4h healthy，但**累计 14 次 restart**（最近 8/17 08:14 UTC）——需留意 OOM/健康检查重启 |
| **LLM** | **DeepSeek 402 Insufficient Balance（余额耗尽）**，营销过滤在 fall through 降级；每日研报/AI 功能受影响，**需用户充值** |

## 三、Codex 遗留：10 项待决策

1. **[CRITICAL] TLS 私钥在 git 历史里**：`deploy/aliyun-ecs/ssl/www.alloyresearch.net.key` 与线上证书匹配（有效期至 2026-09-30）。**陷阱：直接 `git rm` 会让服务器下次 git pull 删掉工作区证书 → nginx TLS 失效**。正确顺序：①服务器备份 key 到仓库外+改挂载 → ②重签发轮换 → ③filter-repo 清历史 + force-push。
2. [HIGH] `reports/credentials.md` 明文密码（已从索引移除）需人工轮换。
3. [HIGH] nginx 8000 端口明文 HTTP 公开到 0.0.0.0。
4. [HIGH] SSE 端点（stream.py 3s / notifications.py 5s）async 生成器内同步 SQLAlchemy 阻塞事件循环。
5. [MEDIUM] /analysis/ranking|screen 对 16M 行 etf_indicator 全表 GROUP BY。
6. [MEDIUM] /scoring 热路径双扫 etf_score（~1M 行）。
7. [MEDIUM] 镜像 2.67GB 需多阶段构建（满盘事故元凶之一）。
8. [LOW] ruff 128 余项。
9. [LOW] 通知 API 返回解密后密钥，建议掩码。
10. [INFO] Fernet 密钥建议独立 NOTIFICATION_ENCRYPTION_KEY。

## 四、Codex 遗留：5 项技术债

1. 新闻全文/摘要毒行无限重试（需 attempt 列）。
2. score/signal 不写 ETLLog + job_name 命名错位（运维面板 never_run、stuck 清理删错锁）。
3. 测试 Redis 缓存隔离（test_etf_service 偶发失败）。
4. 详情页移动端 ~980px 内部横向滚动。
5. web-vitals 上报 70 次 ERR_ABORTED → 改 sendBeacon。

## 五、我的 8/5 遗留（仍未闭环）

- 7/27-31 个股指标回补重算（Tushare 占位符事故尾巴）。
- wewe-rss 重新扫码（~19 公众号断供）；~45 反爬源待 Jina（余额耗尽待充值）/浏览器方案。
- 163 邮箱授权码未配（site_watchdog 邮件告警依赖）。
- TIINGO_API_KEY 未配（美股备用源单点）。
- PDF B4（等 reextract 完成后）。
- `sudo xcodebuild -license accept`（用户本机操作）。
