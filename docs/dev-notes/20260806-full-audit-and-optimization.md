# 2026-08-06 项目全面审计与优化

> 范围：全仓库（app/、web/、deploy/、.github/、scripts/、agent/、research/）
> 方法：4 个并行只读审计域（后端安全 / 后端性能与数据库 / 前端质量 / 部署与 CI）+ 本地实测基线（pytest / tsc / vite build / eslint / ruff）
> 结论：基线 1802 测试全绿（沙箱限制误报除外），tsc 通过，eslint 1 error + 127 warnings，ruff 1371 errors。

## 1. 已修复（4 个 commit）

### 1.1 `dce20aa` — 安全：对象级授权 + 路径穿越 + SSRF + 未鉴权端点
- **Chat 会话 IDOR（HIGH）**：`ChatService` 的 get/delete/send/get_messages 全部按 `user_id` 隔离，任何用户不再能读取/删除/注入他人 AI 聊天历史。
- **池读取 IDOR（HIGH）**：`GET /pools/{id}/weights|analytics|correlation|snapshots` 补齐 owner 校验（与写路径一致），他人私有池返回 404（不泄露存在性）。
- **报告生成 IDOR + 路径穿越（HIGH）**：`report_type`/`format` 白名单（Pydantic pattern + Literal）+ 解析后路径包含校验 + 池归属隔离（generate/list/status/download 全部按池可见性过滤），封堵任意文件写入。
- **Webhook SSRF（MEDIUM）**：URL 仅允许 http/https、拒绝 localhost/.local/内网/保留地址（含云元数据 169.254.169.254、阿里云 100.100.100.200），发送禁用重定向；create/update/send 三处校验。
- **未鉴权端点**：`/etfs/scan/logs`、`/research/ai/status` 改为需登录。
- 新增 38 个回归测试。

### 1.2 `5681168` — 性能：N+1、索引、超时
- `get_sector_constituents`：~200 次逐成员查询 → 1 次 IN 查询 + Python 归并。
- `chat_service._build_data_context`：每条消息 3×N → 3 次 IN 查询（窗口函数取最新行）。
- 新增 9 个数据库索引（alembic `e8f0a2c4d6e8`）：`research_note(instrument_code, created_at)`、`sentiment_data(instrument_code, ingested_at)` + `(published_at)`、`ai_chat_session(user_id)`、`ai_chat_message(session_id, created_at)`、`signal(created_at DESC)` + `(etf_code, trade_date)`、`etf_score(template_id, trade_date, rank_overall)`、`notification_log(config_id, created_at)`。
- 模型补齐与既有迁移一致的索引声明（消除 autogenerate 漂移）。
- MiniMax/DeepSeek OpenAI client 增加 `httpx.Timeout(60s 读 / 10s 连接)`（此前默认 ~600s 会挂死请求）。
- sentiment ingest 去重从逐条 SELECT 改为批量查询。

### 1.3 `7757f45` — 部署 / CI 加固
- **Dockerfile**：`COPY scripts/seed_users.py`（修复全新部署容器内 seed 步骤必然失败）；poetry install 后卸载 poetry + 清 pip 缓存（镜像瘦身）。
- **rollback.sh**：`celery-worker` → `celery-worker-indicator` + `celery-worker-cninfo`（此前自动回滚永远失败）。
- **生产 compose**：从两个 celery worker 移除 docker.sock（worker 解析不可信 PDF，消除 worker RCE → 宿主 root 路径）。
- **开发 compose**：backend 增加 `image: ad-research:latest` 标签（修复 workers 拉取不存在镜像）。
- **.gitignore**：新增 `*.key`/`*.pem`/`*.p8`/`reports/credentials.md`；`git rm --cached` 移除已提交的明文账号密码文件。
- **.env.example**：`DATABASE_URL` asyncpg → psycopg2（与同步引擎一致）。
- **deploy.yml**：新增 CI 门禁（轮询该 SHA 的 combined status，CI 失败中止部署）。
- **backend-ci.yml**：新增 ruff 检查 job。
- **secrets-scan.yml**：补充 push main 触发（此前 PR-only 可被直接 push 绕过）。

### 1.4 `aee0ad6` — 前端：崩溃、a11y、性能、包体积
- **BacktestDetail 条件 hooks 崩溃（HIGH）**：useMemo 上移到条件 return 之前，修复冷加载 "Rendered more hooks" 崩溃。
- **Sparkline 条件 hook**：同样上移；渲染期 `Math.random()` 改用 `useId()`。
- **DetailDrawer a11y**：scrim 改 `<button>`（eslint 唯一 error 清零）；与 panel 平级消除 button 嵌套（axe nested-interactive）；Tab 焦点循环移到 document 级；scrim `aria-hidden` 避免读屏重复"关闭"；新增 axe 回归测试。
- **Dashboard SSE 减半**：删除 `usePriceStream`（与 `useMarketStream` 订阅同一端点），4 连接 → 2。
- **InstrumentList**：columns `useMemo` + `LivePriceCell` `React.memo`（SSE 3s 不再整表重渲染）。
- **ScoreRadar**：颜色 useMemo 依赖补 `themeTick`（主题切换后正确变色）。
- **echarts 按需注册**：`echarts/core` + `echarts-for-react/lib/core`，chunk gzip 350KB → 238KB（-32%）。
- **vite**：生产关闭 sourcemap（-8.5MB）；chunk 告警阈值 500KB。
- **index.html**：移除冗余 Google Fonts（字体已自托管）。
- **react-query**：默认 retry 1（此前 3 次 × 30s 超时，后端挂掉体验极差）。
- **卸载 11 个零引用依赖**（recharts、@ark-ui/react、@react-spring/web、@use-gesture/react、polished、chroma-js、colorjs.io、culori、lucide-react、@formkit/auto-animate、@ant-design/pro-components）。

### 1.5 `630535a` — ruff 清理 + 真实 bug 修复
- ruff 1371 → 128 项（清理 ~90%）。
- 修复 8 处真实 bug：`check_cookies.py` 字符串索引 KeyError、`orchestrate_v2.py` 缺 requests import（NameError）、`warmup_social_profiles.py` 死代码 + cookie_name 未定义、`us_stock_enrichment.py` 重复导入、akshare/binance 重复 property、`scheduler_xueqiu.py` 闭包捕获循环变量、`update_daily_data_nobacktest.py` 文件头残留。

## 2. 验证基线（修复后）

| 检查 | 结果 |
|---|---|
| pytest（全量，本地 Redis + Postgres） | **1824 passed, 2 skipped** |
| 前端 vitest | **73 passed** |
| tsc --noEmit | 通过 |
| vite build | 通过（echarts 713KB / ui 1.2MB，无 sourcemap） |
| eslint（--max-warnings=0） | **0 errors**，125 warnings（多为 react-hooks/set-state-in-effect 等既有警告） |
| ruff | 128 剩余（风格债） |
| alembic upgrade head | 通过（含新索引迁移，已在本地库验证 9 个索引生效） |
| docker compose config | dev + prod 均通过 |

## 3. 待用户 / 运维决策的高风险项（未自动处理）

1. **[CRITICAL] TLS 私钥已提交 git**：`deploy/aliyun-ecs/ssl/www.alloyresearch.net.key` 与线上证书匹配（有效期至 2026-09-30）。已加 `.gitignore` 防护，但**直接 `git rm` 会导致服务器下次 `git pull` 删除工作区证书文件 → nginx TLS 失效**。建议：
   1. 立即在服务器备份 key 到仓库外路径并改 compose/nginx 挂载；
   2. 重新签发证书（新 key）并轮换；
   3. `git filter-repo` 清理历史 + force-push。
2. **[HIGH] `reports/credentials.md` 明文账号密码**：已从索引移除 + gitignore，但**这些密码可能对应线上账号，需人工轮换**（我无法访问生产）。
3. **[HIGH] nginx 8000 明文 HTTP 公开**：`deploy/aliyun-ecs/docker-compose.yml` 将 8000 发布到 0.0.0.0，README 公开宣传 `http://IP:8000`。建议绑定 127.0.0.1 或删除，仅留 443。
4. **[HIGH] SSE 端点阻塞事件循环**：`app/api/v1/stream.py`（价格流每 3s）与 `notifications.py`（每 5s）在 async 生成器内直接跑同步 SQLAlchemy。修复需 `run_in_executor` + 批量 IN 查询，改动面较大，建议单独排期。
5. **[MEDIUM] `/analysis/ranking` 与 `/analysis/screen` 全表 GROUP BY（etf_indicator ~16M 行）**：建议 Redis 缓存（模式同 screening_service）或维护"每 code 最新指标"物化表。
6. **[MEDIUM] `GET /scoring` 热路径**：`_latest_dates_by_market_subquery` 每次请求扫两次 etf_score（~1M 行），建议缓存 + 已补 `(template_id, trade_date, rank_overall)` 索引。
7. **[MEDIUM] Docker 镜像体积**：gcc + poetry 仍留在运行时镜像（~2.67GB，曾触发磁盘满事故）。建议多阶段构建（build stage 装 gcc/poetry，runtime 只拷 site-packages）。
8. **[LOW] 剩余 ruff 128 项**：N806 命名 / E402 导入位置 / SIM105 / B904 等，需人工逐处判断。
9. **[LOW] 通知 API 返回解密后的 SMTP/Webhook 密钥**（前端编辑需要，但建议改掩码返回 + 仅服务端解密）。
10. **[INFO] Fernet 密钥回退到 AUTH_SECRET_KEY**：建议独立 `NOTIFICATION_ENCRYPTION_KEY` 以便独立轮换。

## 4. 过程资产
- 审计原始报告：`tmp/audit/{security,performance}.md`（subagent 产出，含完整 file:line 证据）。
- 建议清理：`tmp/audit/` 为一次性资产，可删除。

---

# 追加：2026-08-08 功能可用性 / 逻辑循环 / UX 审计与修复

> 方法：本地起全栈（Postgres/Redis + uvicorn + Playwright）实测 35 个页面，
> 2 个并行只读审计（前后端契约、调度/管道循环），逐端点复现 500/422/404。

## 已修复（`486d79e`）

### 功能断点（页面实测）
- **news / learning 全页 500**：`alembic/env.py` 从未加载 `app/models/news.py`
  （`app/models/news` 包遮蔽），`news_article` 的 `duplicate_of`/`embedding` 等列
  从未迁移 → 生产查询 UndefinedColumn。修复：env.py 经 `_model_loader` 加载 +
  2 个补列迁移（`f0b2d4e6f8a0` / `f0b2d4e6f8a1`），本地库已验证生效。
- **SPA fallback**：uvicorn 直连时深层路由 404（生产靠 nginx try_files 兜底，
  后端直连端口断）。非 API 路径 404 → index.html；API/带扩展名仍 404。
- **/strategies/templates 500**：`params` 必填但模板只有 `param_specs` → 改可选。
- **/news/event-signals 422**：路由顺序 bug（`/{article_id}` 抢匹配）→ 调整顺序。
- **选择器 422**：3 处 `page_size=10000` 触发后端 `le=200` → 新增轻量
  `GET /etfs/options` + `useEtfOptions`（规避连接池饱和历史问题）。
- **详情页 404**：A 股无后缀（510300）→ `get_etf`/indicators 补后缀 fallback +
  前端规范 code 重定向。
- **ReturnComparison 崩溃**：`/market-data/snapshot` 对象当数组 → 类型对齐。
- **BacktestDetail 归因空表**：渲染后端真实单桶 attribution。
- **news 序列化缺 5 字段**（body/importance/event_category/sentiment_confidence/
  sentiment_drivers）→ 前端信息位恢复。
- **AIHelpDrawer 403 回归**：全局渲染导致 /login 未登录调 ai/status → 移入 RequireAuth。

### 逻辑循环 / 断点（Cicero 审计 + 本地修复）
- **A 股日终 ETL 无跨日补数**（HIGH）：从库内最新交易日次日续抓，断档日自动补数。
- **指标日期锁 12h 永不释放**（HIGH）：6h TTL + 任务成功/最终失败主动释放。
- **情绪批处理 30s 无限重选**（HIGH）：NOT EXISTS 过滤已处理行 + 失败 10min 防抖缓存。
- **部署日志 SSE 断线不重连**（MEDIUM）：封顶退避重连。
- **dev celery 无 industry 队列消费者**（MEDIUM）：compose 对齐生产。
- 修复 E741 改名引入的 `asia_en_batch.py` 回归。

### UX
- useApiErrorToast 同 key 10s 冷却去重（避免 toast 轰炸）。

## 验证
- 全量 pytest：**1829+ 通过**（本地 Redis flushdb 后；2 例需共享缓存隔离）。
- 前端 tsc + vite build 通过；eslint 0 error。
- Playwright 35 页实测：无 JS 崩溃、无 document 级横向溢出；
  页面内容量修复前后明显提升（如详情页 461→966）。
- 截图资产：`tmp/shots/desktop-*.png`、`mobile-*.png`、`login.png`（共 43 张）。

## 遗留（建议后续）
1. **新闻全文/摘要毒行无限重试**（每 10min force 重抓/调 LLM，需加 attempt 列）。
2. **score/signal 不写 ETLLog + job_name 命名错位**（运维面板显示 never_run、
   stuck 清理删错锁，需统一命名 + `@record_etl`）。
3. **测试 Redis 缓存隔离**（共享 Redis 导致 test_etf_service 偶发失败，
   建议 conftest 加 autouse flush 或独立 db）。
4. **详情页移动端**：内容最小宽度 ~980px（内部横向滚动），需实测调优。
5. **web-vitals 上报**：70 次 ERR_ABORTED（页面切换中断遥测），建议改
   `navigator.sendBeacon`。
6. `/analysis/ranking|screen` 全表 GROUP BY 缓存、SSE 阻塞事件循环等
   （见前文性能章节）。
