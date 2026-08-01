# 2026-08-02 资讯源三波扩容（+170 源）统一接线 + cls 段落根治 runbook

## 总览

三波并行扩容 agent（A 英文财经 / B 官方机构+行业垂直 / C 中文媒体+日韩+加密）各自从生产 ECS 实测验证候选（浏览器 UA、HTTP 200、>5KB、可解析 RSS/Atom、≥5 条、最新条目 ≤30 天），主会话统一接线。

| 波次 | 文件 | 源数 | 批次 | job 命名空间 | crawler |
|---|---|---|---|---|---|
| A 英文财经 | `en_fin_batch.py` | **56** | a-f (10×5+6) | `news_enf_*_60m` | `EnFinBatchCrawler` |
| B 官方+垂直 | `official_batch.py` | **56** | a-f (10×5+6) | `news_ofc_*_60m` | `OfficialBatchCrawler` |
| C 中文/日韩/加密 | `zh_media_batch.py` | **58** | a-f (10×5+8) | `news_zhm_*_60m` | `ZhMediaBatchCrawler` |

合计 **+170 源 / +18 个 hourly job**（IntervalTrigger 60m + jitter 600 + coalesce，与既往波次一致）。

## 关键决策与陷阱（下次扩源必读）

1. **`market="global"` 是前端隐身哨兵**：`news.py::_GLOBAL_MARKETS = ("cn_a","us","crypto")`，market=global 的文章在默认视图不可见。三波一律按 asen_* 先例：英文/日韩/东南亚 → `us`；港台陆 → `cn_a`；加密 → `crypto`。
2. **并行波次互相撞车**：A/B 各自只保证对存量零重叠，跑完后才发现 7 个 URL 撞车——fedspeeches / fedmonetary / cbo / cato / cfodive / paymentsdive（A 删，留 B）+ mining.com（A 删，留 B 的 miningcom）。**接线时必须做跨波次 URL 交集检查**（测试 `test_no_overlap_with_official_wave` 已固化）。
3. **cato 两个 feed 不同**：B 收 `cato.org/feed`（主站），A 曾收 `cato.org/rss/blog`（博客）。撞车裁决以 B 为准。
4. **接线三步走**（每波都要）：`scheduler_jobs.py` 加 factory（镜像 `_zhb_batch_job`，import 放函数外但带 `# noqa: E402`）→ `app/core/scheduler.py` 注册循环 → `app/api/v1/news.py` 加 `_WORKER_KEYWORDS`（`enf_`/`ofc_`/`zhm_`）+ `_WORKER_META` 标签。wiring 测试在 `test_expansion_wave_wiring.py` + `test_official_batch.py::TestSchedulerWiring`。

## 质量备注（后续审计勿误判）

- **付费墙摘要源**（Economist×2 / FT Alphaville / NZ Herald）：RSS 只给摘要，正文走抓取层——不是低质源。
- **BOJ**：feed 仅标题+链接+日期，正文走抓取层，官方一手源特意保留。
- **CFTC×3**：体积 4.5-4.9KB 略低于 5KB 铁律，但 10 条全新鲜，docstring 已明示。
- **FDIC**：feed 慢（~20s/900KB），crawler timeout 25s 覆盖；日后超时首先淘汰它。
- **hoover/mckinsey/fca/fiercehealth**：pubDate 非标准或无日期，`parse_rss_items` 回退抓取时间入库；根治需在 `_parse_date` 补 "July 31, 2026" / "Fri, 31 Jul 2026" 格式。
- **Nikkei Asia**：RSS 1.0 无日期 feed，同样回退抓取时间。

## cls 段落粘连根治（同批部署）

- **根因**：cls/wallstreetcn 的 crawler 用 `BaseCrawler.strip_html()`（`re.sub(r"\s+"," ")` 全部空白折叠）先把 API 纯文本正文拍平，normalizer 的 `raw.body or _strip_html_to_text(...)` 短路，8-01 修的段落保留器根本没机会跑。财联社 API `content` 字段**本身带 `\n\n`**（已实证）。
- **修复**：`BaseCrawler.strip_html_preserve_paragraphs()`（与 normalizer/rss_common 同一块级边界规则，对无标签纯文本安全）；cls.py brief/content_text 与 wallstreetcn.py HTML 回退路径切换；无标题快讯标题兜底先折叠再截 50 字（防换行进标题）。原 `strip_html` 语义不变（标题/brief 单行场景）。
- **测试**：`test_strip_html_paragraphs.py` +10 用例（基类/cls 真实 payload/wallstreetcn 回退）。
- **存量**：生产 138 行 cls 打平行（2026-07-25→08-01，全部 `【...】` 开头，其中 23 行 `N、` 编号快讯）。修复方案：启发式 `re.sub(r'([。！？”》]) ', r'\1\n\n', text)` 恢复三字段，**先 dry-run 打印 10 条人工确认再 UPDATE**（生产写操作，待用户批准；脚本模式参照 huxiu refetch：scp→docker cp→`docker exec -e PYTHONPATH=/app`）。

## 验证

- `pytest app/tests/news/` → **753 passed**（含新增 wiring 测试 22 项）
- 全量 `pytest app/tests/` 见提交前记录
- 部署后冒烟：ECS `docker logs <backend>` 看 `news_enf_a_60m`/`news_ofc_a_60m`/`news_zhm_a_60m` 首轮 ETL 日志；`psql -U etf -d ad_research -c "SELECT source, count(*) FROM news_article WHERE fetched_at > now() - interval '3 hours' AND (source LIKE 'enf\_%' OR source LIKE 'ofc\_%' OR source LIKE 'zhm\_%') GROUP BY 1 ORDER BY 2 DESC"`；资讯健康度面板 18 个新 worker 亮灯。

## 淘汰清单（三波合计 ECS 实测 ~650 候选）

完整清单在各模块 docstring（`en_fin_batch.py` / `official_batch.py` / `zh_media_batch.py`），按原因归类：Cloudflare/Akamai 403（IMF/OECD/Investopedia/Benzinga/The Block…）、无原生 RSS（WSJ/Bloomberg/Reuters/BOJ 除外的多家央行…）、死 feed/停更（Forbes 全系/CNN Business/Blockworks…）、超 30 天不新鲜、feed 内含未来日期毒数据（BIS 研究论文/Bank of Canada/Richmond Fed——**验证时务必检查最新条目不能在未来**）、标题党拒收（Coinpedia/CryptoNewsZ 等）。
