# 微信公众号 RSS 接入（wewe-rss + AI 营销过滤）

> 状态：✅ 代码已合入 main，待用户在 ECS 上部署 wewe-rss 容器即可联调。
> 适用范围：A 股宏观 / 政策类公众号订阅（默认适配「泽平宏观」）。
> 最后核实更新：2026-07-21（修正：生产 compose 的 backend 服务名、LLM provider 说明）

## 1. 为什么选 wewe-rss

微信公众平台不开放 RSS / API，且微信读书的文章列表本身就是公众号
RSS 化最稳的代理。社区项目 `cooderl/wewe-rss`
（<https://github.com/cooderl/wewe-rss>）提供一个轻量 Docker 镜像，
扫码登录一次后，把每个订阅的公众号暴露成 JSON feed：

```
GET {base_url}/feeds/{feed_id}.json?limit=30
```

返回的 JSON 形状与 RSS-JSON 兼容，包含 `items[].title / url /
description / content_html / date_published / authors`，正好可以
无损喂给我们平台现有的 `RawArticle` 管线。

我们评估过的备选：

- **feeddd / wechat-feeds** 等公共代理：稳定性差、容易限流，长期
  不可控。
- **直接抓 mp.weixin.qq.com**：会触发反爬封号，且平台条款禁止。
- **企业微信 API**：仅自建应用可见，无法订阅第三方公众号。

wewe-rss 是目前唯一一个「零代码、零封号风险、自托管」的方案。

## 2. 部署 wewe-rss

### 2.1 推荐：docker compose

新建 `/opt/wewe-rss/docker-compose.yml`：

```yaml
version: "3.8"
services:
  wewe-rss:
    image: ghcr.io/cooderl/wewe-rss:latest
    container_name: wewe-rss
    restart: unless-stopped
    ports:
      - "4000:4000"
    environment:
      # 关闭强制更新（避免频繁触发微信读书风控）
      - DATABASE_URL=sqlite:/data/db.sqlite
      # 邮件通知可选
      - AUTH_CODE=${AUTH_CODE:-}        # 第一次扫码登录成功后填入
    volumes:
      - ./data:/data
```

启动：

```bash
cd /opt/wewe-rss
docker compose up -d
docker compose logs -f wewe-rss
```

访问 `http://<ECS-IP>:4000` → 点击「添加账号」→ 微信扫码登录微信
读书 → 登录成功后会显示一个 `AUTH_CODE`，把它写回
`.env`：`AUTH_CODE=xxxxxxx`，再 `docker compose restart`。

> ⚠️ **风控提示**
> 微信读书的扫码态有效期约 14 天，掉线后用同一个手机重新扫码即可。
> 不要在同一 IP 上并发跑多个 wewe-rss 实例，会触发风控。

### 2.2 订阅公众号

登录 wewe-rss 后台 → 「公众号管理」 → 粘贴公众号文章页 URL
（如 `https://mp.weixin.qq.com/mp/homepage?__biz=...`）→ 等待
wewe-rss 抓取一次首页 → 订阅成功后系统会给每个公众号分配一个
`feed_id`，格式形如 `MP_WXS_3077122839`。

复制 feed id 备用，下一步填进平台 `.env`。

> 暂未联调前可以先用任意测试公众号 id 占位，平台在没有真实 feed
> 数据时会自动 no-op，不会影响其他资讯源。

## 3. 平台侧配置

### 3.1 `.env` 新增

```bash
# wewe-rss 服务地址；本地 / 容器内访问用 http://localhost:4000，
# 跨主机 / 跨 ECS 用 http://<ECS-IP>:4000
WECHAT_RSS_BASE_URL=http://localhost:4000

# 订阅的 feed id；多个用逗号分隔（每个公众号一行）
# 例：泽平宏观
WECHAT_RSS_FEED_ID=MP_WXS_3077122839

# 单次 HTTP 请求超时（秒）；wewe-rss 慢的情况下可放宽
WECHAT_RSS_TIMEOUT_SECONDS=10

# 是否启用 LLM 二次判定；关键词黑名单始终生效
WECHAT_MARKETING_FILTER_LLM_ENABLED=true
```

`.env.example` 里已经写入默认值，新人按上面例子替换即可。

### 3.2 验证

重启 backend，让新的 cron job 注册（生产 compose 里 backend 的
service 名是 `backend`，容器名 `alloyresearch-backend`）：

```bash
docker compose restart backend
docker compose exec backend python -c "
from app.config import get_settings
s = get_settings()
print('base:', s.wechat_rss_base_url)
print('feeds:', s.wechat_rss_feed_id)
"
```

打开健康页 `/news/health` → 看到 `wechat_zeping` 行的
`job_id = news_wechat_zeping_15m` 即代表 cron 已上线。

第一次 tick 会立刻抓一次；如果 wewe-rss 不可达，`last_etl.status`
会显示 `failed` 且 `error_msg` 类似
`crawl_error: All connection attempts failed` —— 这是预期行为，
不会阻塞其他资讯源。

## 4. AI 营销过滤逻辑

文件：`app/services/news/filters/wechat_marketing_filter.py`

```
classify(title, body) -> MarketingVerdict
```

判定流程：

1. **关键词黑名单**：标题或正文前 500 字命中以下任一关键词 →
   `is_knowledge=False, reason="keyword_blocklist"`，永远不调用 LLM。
   - 研学计划 / 研学营 / 课程报名 / 直播预告 / 直播预约
   - 全球财富会 / 论坛报名 / 峰会邀请
   - 扫码加入 / 席位预定 / 早鸟价 / 限时优惠 / 邀请函
   - 知识星球 / 私享会 / 闭门会 / 内部活动
   - 免费领取 / 限时免费 / 发布会 / 新品发布
2. **LLM 二次判定**：未命中关键词的边角案例 → 调用平台统一 LLM
   Provider（`app.services.llm.get_llm_provider()`；由 `LLM_PROVIDER`
   环境变量选择，默认 **MiniMax**，`deepseek` 为 legacy 选项）让 LLM 输出
   `{"knowledge": true|false, "confidence": 0.0-1.0}`。
   - 解析失败 / 超时 / API 未配置 → **fail-open**
     (`is_knowledge=True`)，保留文章避免误杀。
   - 结果在内存里缓存 24h，同一篇文章不会被反复计费。
3. `wechat_marketing_filter_llm_enabled=false` 时跳过 LLM
   步骤，只保留关键词判断（fast path，零成本）。

### 调试

```bash
docker compose exec backend python -c "
from app.services.news.filters.wechat_marketing_filter import WechatMarketingFilter
f = WechatMarketingFilter()
print(f.classify('泽平宏观研学计划开启报名', '扫码加入'))
print(f.classify('央行降准 0.5 个百分点解读', '本文从宏观流动性分析'))
"
```

如果发现漏网之鱼（误把营销放进来），把它的标题 / 关键词加到
`DEFAULT_MARKETING_KEYWORDS` 元组里即可；如果发现误杀（把好文过滤掉），
把 `wechat_marketing_filter_llm_enabled=true` 让 LLM 接管。

## 5. 排障清单

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `news_wechat_zeping_15m` 一直 `skipped` | 没填 `WECHAT_RSS_FEED_ID` | 登录 wewe-rss 后台复制 feed id 到 `.env` |
| `last_etl.status=failed, error_msg=crawl_error: ...` | wewe-rss 容器挂了 / 端口不通 | `curl http://<host>:4000/` 看是否能 ping 通；wewe-rss 日志看扫码态是否过期 |
| 文章数很少 | 公众号更新频率低 + limit 太小 | 把 `WechatZepingCrawler(limit=50)` 在 `scheduler_jobs.py` 里调大 |
| 误杀太多 | 关键词过严 / LLM 没启用 | `WECHAT_MARKETING_FILTER_LLM_ENABLED=true` |
| 漏杀太多（垃圾文章进了 feed） | 关键词太松 | 在 `DEFAULT_MARKETING_KEYWORDS` 追加命中关键词 |
| 后端报错 `ConnectError` | ECS 安全组没开 4000 端口 | 阿里云安全组 → 入方向 → TCP 4000 |

## 6. 已知限制

- **依赖微信读书扫码态**：14 天掉线一次是硬约束，需要人工介入。
  我们在 `_record_etl` 上报了 `failed` 但不会自动重启。
- **feed id 是手填的**：暂时没有自动 discover → 自动 subscribe 的
  流程，因为 wewe-rss 也不允许脚本化登录。
- **正文抓取**：wewe-rss 拿到的是公众号页面的截断 HTML，**没有图**；
  真正要全文阅读仍需配合平台已有的
  `scheduler_fetch_full_content.py` (Jina Reader) 在用户点击时再
  抓一次。
- **多公众号过滤粒度**：当前 filter 对所有公众号统一生效；如果某
  天用户想给某些公众号单独放宽 / 收紧，需要把 `feed_id` 注入到
  filter 里 —— 已经为此预留了位置（`extra["feed_id"]`）。

## 7. 后续 TODO

- [ ] **真实订阅**：用户在 ECS 部署 wewe-rss + 扫码登录 + 填入 feed id
- [ ] **关键词回归**：跑一周后回看 `_extra["marketing_verdict"]`
      字段，看 LLM 命中率，调整关键词
- [ ] **多公众号支持**：现在 `WECHAT_RSS_FEED_ID` 是单值；后续要
      改成 dict（每个公众号对应一组自定义关键词 / 严格度）
- [ ] **审核页**：在 news 健康页加一个 "营销拦截数" 统计，
      数据从 `etl_log.extra_data["rejected_marketing"]` 拿
- [ ] **LLM 缓存**：当前是进程内 dict；切多 worker 后要换成 Redis
      以避免每个 worker 各付一遍费