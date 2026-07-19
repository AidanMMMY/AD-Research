# 20 小时 Overnight 研究 Worker 改进报告

> **报告时间**：2026-07-18  
> **目标**：让 `overnight_research.py` 能持续 20 小时高密度地搜集、分析、沉淀高质量学习/研究资料。  
> **文件**：`agent/workers/overnight_research_v2.py`（保留旧版 `overnight_research.py`）  
> **测试目录**：`/data/ad-research/overnight_test_20260718/`

---

## 1. 摘要

当前 ECS 上运行的 `overnight_research.py`（v1）在启动后约 1 小时内 5 个 theme agent 全部退出，剩余 ~17 小时 orchestrator 空转，只产生 68 条记录，且内容相关度、来源质量、字段深度均不理想。

本次改进实现 `overnight_research_v2.py`，核心变化：

1. **Supervisor 持续循环**：任一 theme agent 结束后自动换方向/换子主题重新 spawn，直到 deadline。
2. **LLM 多 provider fallback**：Anthropic → OpenAI → DeepSeek → MiniMax，自动处理敏感/过滤错误并拆分 prompt。
3. **搜索与提取增强**：Jina Reader / Jina Search、SearXNG、RSS/feed（含 stdlib 兜底）、readability-lxml、Playwright 兜底。
4. **增强记录字段**：核心论点、数据/论据、影响链条、投资启示、风险点、质量分、跨主题引用、原始正文片段。
5. **跨主题去重与链接**：URL 精确去重 + title 相似度去重 + content_hash 去重。
6. **中间报告快照**：每 2 小时生成一次 `report_snapshot_<n>.md/html`。
7. **更详细可观测性**：heartbeat 携带各 agent 记录数、LLM/搜索成功失败比例、失败原因统计。

---

## 2. 当前架构与问题诊断

### 2.1 v1 架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                       Orchestrator (主进程)                      │
│  - 计算 deadline（20h）                                          │
│  - 为每个主题 spawn 一个 multiprocessing.Process                  │
│  - 每 5 分钟 heartbeat：统计记录数                               │
│  - 到 deadline 后 terminate 子进程、合并 DB、生成 report          │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ 机制    │ │ 讲话    │ │ 论文    │ │ 行业    │ │ 事件    │
   │ ThemeAgent │ ThemeAgent │ ThemeAgent │ ThemeAgent │ ThemeAgent │
   │ - queries  │ - queries  │ - queries  │ - queries  │ - queries  │
   │ - search   │ - search   │ - search   │ - search   │ - search   │
   │ - fetch    │ - fetch    │ - fetch    │ - fetch    │ - fetch    │
   │ - LLM 提取 │ - LLM 提取 │ - LLM 提取 │ - LLM 提取 │ - LLM 提取 │
   │ - reflect  │ - reflect  │ - reflect  │ - reflect  │ - reflect  │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

### 2.2 关键问题

| 问题 | 表现 | 根因 |
|---|---|---|
| **Worker 提前退出** | 5 个 theme agent 在 1 小时内全部结束，orchestrator 空等 18+ 小时 | `while queries:` 依赖 reflection 持续补充 query；当 reflection 返回空或重复时，循环自然退出，没有换方向/重启机制 |
| **搜索成功率低** | 学术主题 0 记录；总体有效查询率约 23% | Bing/Baidu/DDG  scraping 脆弱；部分查询过宽，返回大量不相关结果；无备用搜索源 |
| **内容提取浅** | 仅 title/summary/key_points，缺少论点、论据、影响链、投资启示 | `ResearchRecord` 模型字段不足 |
| **LLM 稳定性差** | 日志大量 `LLM call failed: input new_sensitive (1026)` | v1 只初始化一个 provider，无自动降级；长 prompt 容易触发 MiniMax 敏感过滤 |
| **去重弱** | 同 URL 重复出现（如 china_mechanisms 9 组重复 URL） | 仅依赖 content_hash 且作用域局限在单主题 |
| **可观测性不足** | 仅 INFO 级别心跳，失败原因未分类统计 | 日志级别为 INFO，DEBUG/ERROR 信息未充分记录 |
| **空等 deadline** | 68 条记录后 17 小时无产出 | 没有 supervisor 重新 spawn 机制，也无中间快照 |

### 2.3 当前运行数据（ECS `/data/ad-research/overnight_20260718/`）

| 主题 | 记录数 | 唯一 URL | 备注 |
|---|---:|---:|:---|
| china_mechanisms | 38 | 25 | 混入大量香港社会新闻，与主题相关度低 |
| event_cases | 20 | 17 | 含 Wikipedia 虚构 2026 战争条目，来源不可靠 |
| industry_deep_dive | 5 | 3 | 来源集中在 ai-bot.cn 和百度热搜 |
| investor_speeches | 5 | 4 | 严重跑题：CISA 网络安全、百度百科“投资”词条 |
| academic_research | 0 | 0 | 零记录 |
| **合计** | **68** | — | 有效研究时间约 35 分钟 |

---

## 3. 改进设计

### 3.1 v2 整体流程

```text
┌────────────────────────────────────────────────────────────────────┐
│                          Supervisor (主进程)                        │
│  - 启动 5 个 theme agent                                          │
│  - 每 N 秒 heartbeat：统计记录数、LLM/搜索失败率                   │
│  - 任一 agent 结束 → 读取 DB 记录数 → 生成新方向 → 重新 spawn     │
│  - 每 2 小时触发 Merger + SnapshotReporter                         │
│  - 到 deadline 后 wind-down、最终合并、生成 report_v2.md/html       │
└────────────────────────────────────────────────────────────────────┘
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ ThemeAgent │ ThemeAgent │ ThemeAgent │ ThemeAgent │ ThemeAgent │
   │ v2       │ v2       │ v2       │ v2       │ v2       │
   │ - 初始 queries + fallback_directions                          │
   │ - 搜索失败/无结果 → 自动换引擎 → RSS 兜底                     │
   │ - 提取增强：arguments/evidence/impact_chain/quality_score 等  │
   │ - query 耗尽 → LLM 生成新方向 → 继续研究                       │
   │ - 到 deadline 或外部 SIGTERM 才退出                            │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────┐
   │  Merger + CrossReference                                   │
   │  - 合并 5 个主题 DB                                          │
   │  - URL 精确去重 + title Jaccard 相似度去重 + content_hash 去重 │
   │  - 生成合并后的 overnight_research_v2.db + FTS5              │
   └────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────┐
   │  SnapshotReporter / ReportBuilder                          │
   │  - 每 2h 生成 report_snapshot_<n>.md/html                    │
   │  - 最终生成 report_v2.md/html                                │
   └────────────────────────────────────────────────────────────┘
```

### 3.2 关键模块改进

#### 3.2.1 LLMClient（多 provider fallback）

- 初始化时依次注册 Anthropic、OpenAI、DeepSeek、MiniMax。
- 按优先级排序：`Anthropic → OpenAI → DeepSeek → MiniMax`。
- `complete()` 内循环调用每个 provider；任一失败时自动切换下一个。
- 对敏感/内容过滤类错误（`sensitive/new_sensitive/content_filter/policy/moderation/1026/10013`），先尝试将 prompt 拆成 4000 字符块分别调用，再降级。

#### 3.2.2 SearchEngine（多源搜索）

- 默认顺序：Jina Search → Bing → DDG → Baidu。
- 若环境变量 `SEARXNG_URL` 存在，则优先使用 SearXNG JSON API。
- 新增 `FeedSource`：为每个主题配置 2 个 RSS/feed 源，作为搜索补充；支持 `feedparser` 或 stdlib `xml.etree.ElementTree` 解析。

#### 3.2.3 Fetcher（多层正文提取）

```text
URL → Jina Reader → 直接请求 + readability-lxml → Playwright 无头兜底 → 返回可用文本
```

- 修正 Jina Reader URL 构造：`https://r.jina.ai/http://<host>` / `https://r.jina.ai/https://<host>`。
- 若 `readability-lxml` 未安装，自动降级到 BeautifulSoup 启发式提取。
- 若 `playwright` 未安装，跳过该层。

#### 3.2.4 ThemeAgent（持续迭代）

- 主循环 `while time.time() < deadline - 10s`，由 supervisor 通过 SIGTERM 终止。
- 当 `queries` 耗尽时，调用 `_generate_new_directions()` 基于已有记录生成 5-8 个新子主题。
- 若 LLM 生成失败或达到最大 reflection 次数，使用 `fallback_directions` 继续。
- 每 3 次迭代做一次 reflection，补充新 query。
- 启动时先处理 RSS 源，加速种子记录生成。

#### 3.2.5 ResearchRecord（增强字段）

新增字段：

| 字段 | 含义 |
|---|---|
| `arguments` | 核心论点（50-200 字） |
| `evidence` | 关键数据/论据（50-200 字） |
| `impact_chain` | 影响链条（如政策→行业→个股→风险） |
| `investment_implications` | 投资启示 |
| `risk_factors` | 风险点 |
| `quality_score` | 0-100 质量分（字段完整性、摘要长度、关联标的等） |
| `cross_refs` | 跨主题引用记录 id |
| `original_text` | 原始正文片段（用于溯源/去重） |

#### 3.2.6 去重策略

- 主题内：插入前检查 `content_hash` 是否已存在。
- 主题间：Merger 合并时先 URL 精确去重，再 title 字符二元组 Jaccard 相似度 >= 0.82 去重。
- 质量分：为每条记录计算 `quality_score`，便于后续筛选和排序。

### 3.3 短周期测试设计

- 命令：`python /workspace/workers/overnight_research_v2.py --output /data/ad-research/overnight_test_20260718 --runtime-hours 0.5`
- 验证点：
  1. 5 个 theme agent 是否持续运行，结束后是否被 supervisor 重新 spawn。
  2. LLM fallback 是否生效（所有 provider 被注册）。
  3. 新字段是否正确写入 DB。
  4. 中间快照是否生成。
  5. 各主题记录数、LLM 成功/失败数、搜索成功/失败数。

---

## 4. 实现清单与关键代码说明

### 4.1 文件变更

| 文件 | 操作 | 说明 |
|---|---|---|
| `agent/workers/overnight_research_v2.py` | 新建 | 改进版 worker，保留旧版 |
| `agent/requirements.txt` | 修改 | 新增 `readability-lxml>=0.8.1` |
| `docs/research/20260718-overnight-research-improvement.md` | 新建 | 本报告 |
| `docs/research/20260718-overnight-research-improvement.html` | 新建 | 自包含 HTML 版 |

### 4.2 关键代码片段

#### 4.2.1 Supervisor 持续 spawn

```python
class Supervisor:
    def _spawn_theme(self, theme: str) -> None:
        if self.deadline - time.time() < 60:  # 不足 1 分钟不再 spawn
            return
        phase = self.phase_counter[theme]
        p = self.ctx.Process(
            target=_run_theme_agent,
            args=(theme, self.output_dir, self.deadline, phase),
        )
        p.start()
        self.processes[theme] = p
        self.phase_counter[theme] += 1

    def _respawn_finished(self) -> None:
        for theme, p in list(self.processes.items()):
            if not p.is_alive():
                p.join(timeout=10)
                # 读取记录数后重新 spawn，换方向
                self._spawn_theme(theme)
```

#### 4.2.2 LLM 多 provider fallback

```python
class LLMClient:
    def __init__(self) -> None:
        self.providers: list[_LLMProvider] = []
        # Anthropic / OpenAI / MiniMax / DeepSeek 注册
        self.providers.sort(key=lambda p: p.priority)

    def complete(self, prompt, system=None, max_tokens=2048, temperature=0.6) -> str:
        for provider in self.providers:
            try:
                return provider.complete(prompt, system, max_tokens, temperature)
            except Exception as exc:
                # 敏感/过滤错误：先拆分 prompt，再降级
                if any(k in str(exc).lower() for k in ("sensitive", "new_sensitive", ...)):
                    # split prompt retry
                continue
        return ""
```

#### 4.2.3 Fetcher 多层提取

```python
class Fetcher:
    def fetch_content(self, url: str) -> str:
        text = self.jina_read(url)
        if len(text) >= 80: return text
        text = self.direct_fetch(url)
        if len(text) >= 80: return text
        text = self.playwright_fetch(url)
        if len(text) >= 80: return text
        return text
```

#### 4.2.4 增强提取 prompt

```text
请从正文中提取 1-3 条高质量研究记录。每条记录包括：
- title, source, url, date, tags, summary, key_points
- related_sectors, related_tickers, impact
- arguments: 核心论点
- evidence: 关键数据/论据
- impact_chain: 影响链条
- investment_implications: 投资启示
- risk_factors: 风险点
```

---

## 5. 短周期测试结果

> **容器启动命令**：
> ```bash
> docker run -d --rm --name alloyresearch-overnight-v2-test \
>   --entrypoint python \
>   -v /opt/ad-research/agent/workers:/workspace/workers:ro \
>   -v /data/ad-research/overnight_test_20260718:/data:rw \
>   --env-file /tmp/overnight_v2_env.txt \
>   -e RESEARCH_SNAPSHOT_SECONDS=600 \
>   -e RESEARCH_HEARTBEAT_SECONDS=60 \
>   ad-research:a539451 \
>   /workspace/workers/overnight_research_v2.py --output /data --runtime-hours 0.5
> ```
> 其中 `/tmp/overnight_v2_env.txt` 从当前运行的 `alloyresearch-overnight-research` 容器复制 API key 环境变量，避免硬编码。
> 
> **进程内命令**：`python /workspace/workers/overnight_research_v2.py --output /data --runtime-hours 0.5`

### 5.1 运行概况

| 指标 | 数值 |
|---|---|
| 测试开始时间 | 2026-07-18 11:07:36 UTC |
| 测试结束时间 | 2026-07-18 11:34:45 UTC |
| 总运行时长 | 约 27 分钟（0.5h 的 90% 主循环 + 10% wind-down） |
| 5 个 agent 是否持续运行 | 是，整个主循环期间 `alive=5/5` |
| 是否有 agent 提前结束 | 否 |
| 是否被 supervisor 重新 spawn | 30 分钟内未触发（agent 未退出），但代码已实现；新方向生成已验证 |

### 5.2 记录统计

| 主题 | 原始记录数 | 合并后记录数 | 高质量记录数 (>=60) | 备注 |
|---|---:|---:|---:|:---|
| china_mechanisms | 6 | 3 | 3 | 去重后剩余 3 条 |
| investor_speeches | 6 | 6 | 6 | 无跨主题重复 |
| academic_research | 3 | 1 | 1 | 学术搜索仍偏难，部分被跨主题去重 |
| industry_deep_dive | 14 | 10 | 10 | 数量最多，半导体/AI 相关 |
| event_cases | 5 | 4 | 4 | 部分 Nexon/游戏事件记录被去重 |
| **合计** | **34** | **24** | **24** | 合并去重 10 条；质量分分布全部在 80-100 区间 |

### 5.3 LLM 与搜索统计

| 指标 | 数值/说明 |
|---|---|
| LLM 总调用次数 | 30 分钟测试未完全统计；5 分钟最终代码验证为 94 次（industry 21 + investor 24 + academic 19 + china 16 + event 14） |
| LLM 失败次数 | 5 分钟验证中 `llm_failures=0`；30 分钟测试中观察到 Anthropic `input new_sensitive (1026)` 与 OpenAI `invalid model gpt-4o-mini` 报错，但记录仍持续产生，说明 fallback 生效 |
| 搜索总调用次数 | 5 分钟验证为 29 次 |
| 搜索失败次数 | 5 分钟验证为 7 次（搜索失败率约 24%） |
| 提取失败/内容过短 | 5 分钟验证中 `fetch_failures=5`；部分 URL 因 Jina 429 或内容过短被跳过 |
| 去重跳过 | 30 分钟测试合并去重 10 条；5 分钟验证去重 2 条 |

### 5.4 Supervisor 循环与新方向生成验证

| 检查项 | 结果 |
|---|---|
| 是否有 agent 提前结束 | 否，5 个 agent 全程运行到 wind-down |
| 结束后是否被重新 spawn | 代码已实现；30 分钟与 5 分钟测试均未触发（agent 未退出） |
| 是否有新方向生成 | 是。日志可见 `[investor_speeches] generated new directions: 8`、`[event_cases] generated new directions: 8` 等 |
| 中间快照是否生成 | 30 分钟测试生成 4 份 snapshot（最终代码已修复启动时即快照的问题）；5 分钟验证仅 1 份最终快照 |
| 最终报告 | 生成 `report_v2.md` + `report_v2.html` |

### 5.5 新字段验证

| 字段 | 是否写入 DB | 示例说明 |
|---|---|---|
| arguments | 是 | "Nexon 通过 2006 年设立 NXC 母公司...完成跨国控股架构转型" |
| evidence | 是 | "2011 年 12 月日本子公司升格...NXC 直接持股 28.5%..." |
| impact_chain | 是 | 已写入，可在 DB 中查询 |
| investment_implications | 是 | "Nexon 的跨国控股模式为 A 股游戏公司...提供参考..." |
| risk_factors | 是 | "1）控股母公司 NXC 的间接持股结构增加治理复杂性..." |
| quality_score | 是 | 合并后 24 条全部 >= 80，最高 100 |
| cross_refs | 是 | 字段已存在，30 分钟测试内跨主题引用较少 |
| original_text | 是 | 原始正文片段已保存 |

### 5.6 最终代码 5 分钟验证（修复后）

| 检查项 | 结果 |
|---|---|
| 启动时是否立即快照 | 否，已修复 |
| stats_v2.json 是否生成 | 是，按主题统计 LLM/搜索/记录数 |
| heartbeat 是否显示 LLM/搜索失败数 | 是 |
| 记录是否持续产生 | 是，5 分钟产生 15 条原始记录 |
| 学术主题 | 仍为 0 条，需要单独优化学术源 |

---

## 6. 下一步可继续优化方向

1. **搜索质量提升**
   - 部署私有 SearXNG 实例，聚合 Google/Bing/Baidu/DDG，减少单点失败。
   - 为每个主题维护“高质量源白名单”，优先抓取政府官网、主流财经媒体、券商研报、学术论文站点。
   - 引入搜索结果相关性打分，过滤标题/摘要明显跑题的结果。

2. **LLM 输出稳定性**
   - 使用 OpenAI/Anthropic JSON mode / tool use 强制结构化输出，降低解析失败率。
   - 对低质量记录做二次 LLM 提炼，提高摘要和论点质量。
   - 对 MiniMax 等敏感过滤频繁的 provider，增加输入预处理（关键词过滤、分段）。

3. **去重与质量**
   - 引入 simhash/minhash 做正文近重复检测，替代简单的 title 相似度。
   - 为来源域名建立权威性评分，自动降低低质量源权重。
   - 增加时效性评分，优先沉淀近 7-30 天内容。

4. **可观测性增强**
   - 日志切分 DEBUG/INFO/WARNING 级别，失败原因分类统计。
   - 将 stats 写入 SQLite 或 Prometheus metrics，方便面板监控。
   - 为每个 theme agent 保存独立日志，便于单独排查。

5. **内容深度**
   - 对 PDF/论文页面做特殊处理（pdfplumber / PyMuPDF）。
   - 增加“原始 vs 中文翻译”字段，对英文内容自动翻译并保存原文。
   - 提取表格、数据点，生成结构化 evidence 条目。

6. **部署与依赖**
   - 在 `ad-research:latest` 镜像中安装 `readability-lxml`、`feedparser`（已加入 requirements.txt，待 rebuild）。
   - 考虑为 overnight 单独构建一个容器/服务，避免与 backend 共用容器。
   - 增加 `HEALTHCHECK` 和自动重启策略。

---

## 7. 结论

`overnight_research_v2.py` 通过 Supervisor 持续循环、LLM 多 provider fallback、搜索/提取增强、字段深度扩展、跨主题去重和中间快照，解决了 v1 的核心问题：worker 提前退出、空等 deadline、LLM 失败无降级、内容字段浅、可观测性不足。

30 分钟短周期测试验证：
- 5 个 theme agent 全程运行，未出现 v1 中提前结束空等的情况。
- 新方向生成机制生效，agent 在初始查询耗尽或达到迭代预算后自动生成新子主题。
- LLM fallback 机制生效，在 Anthropic 返回 `input new_sensitive`、OpenAI 返回模型错误时，仍能持续产生记录。
- 增强字段（arguments、evidence、impact_chain、investment_implications、risk_factors、quality_score 等）已正确写入 DB。
- 跨主题去重生效，34 条原始记录合并后为 24 条，且全部在 80-100 质量分区间。
- 中间快照与最终报告正常生成。

测试中也暴露以下待继续优化点（已纳入下一步）：
- 搜索成功率仍偏低，Jina Reader 免费额度下 429 频繁；建议引入 SearXNG 私有聚合搜索或提高 Jina RPM。
- 学术主题（academic_research）搜索/提取难度大，产出偏少；建议增加 arXiv/NBER/SSRN 等专门源。
- 新方向生成偶有跑题；已在最终代码中加入主题约束，并可在实际运行中继续微调。
- 子进程日志默认进入 Docker 日志，落地文件需改进；同时 stats 持久化已修复为 SIGTERM 安全。
