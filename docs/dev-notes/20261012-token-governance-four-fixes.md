# 2026-10-12 Token 治理四快赢 + ECS 磁盘回收 实施记录

> 承接《2026-10-12 ECS+LLM 成本全面诊断报告》。本文件记录诊断报告中
> 「B 组代码快赢」4 项 + ECS 侧可立即执行项的实施细节、验证结果与口诀。
> commit：`7a9e968`（代码）+ `aff405d`（诊断报告入库）。

## 一、改动清单

### P0-1 情绪管线「永不落章」毒丸队列根治 ⭐最大收益

**病灶**：`sentiment_pipeline.py` 的 `_backfill_article_sentiment` 在
无 symbols（无 scores）时 early-return，`event_category` / `importance` /
`sentiment_processed_at` 全部丢弃。而行选择集是
`event_category IS NULL`——LLM 费已付，行却永远留在选择集里，
30 天结果缓存到期后完整重烧，无限循环。约 85% 日流量走这条路，
也是 importance 覆盖率仅 ~15%（卡死翻译/摘要门）的根因。

**修复**（三处联动）：

1. `_backfill_article_sentiment`：无 scores 也写回三字段；
   `sentiment_score`/`sentiment_label` 保持 NULL 不伪造。
2. `process_article` 缓存命中路径：补调 backfill + commit——
   修复前已入缓存但未落章的存量行，在缓存期内被选中时**零 LLM
   开销自愈**。
3. `run_news_article_categorization` 选择集：
   `event_category IS NULL` → `sentiment_processed_at IS NULL`。
   实体抽取合法返回 null 分类的行不应被无限重选；
   `sentiment_processed_at` 才是唯一可信的「LLM 见过这行吗」标记。

### P0-2 研报摘要「>5s 丢弃」100% 白烧根治

**病灶**：`research_report_service.py` 的 5s 墙钟阈值是 DeepSeek 时代
遗物；MiniMax 常态延迟 30-160s → token 付了结果被扔，`summary IS NULL`
选择集每 2h 重试 20 条，无上限永久循环。

**修复**：

- 删除 5s 丢弃逻辑（付费结果一律落库，墙钟不再是判据）。
- 新增 `research_reports.summary_attempts` 列（迁移 `e2f4a6b8c0d3`），
  每次 LLM 尝试前置 +1 并独立 commit（失败也计数）。
- 批次选择集加 `summary_attempts < 3` 封顶。
- 每日 `news_attempts_daily_reset` 任务同步清零研报表封顶行——
  MiniMax 周配额窗口期失败的行在充值/重置后自动回池，不会永久驱逐。

### P1-2 Prompt 截断

- 情绪管线：body 统一截到 `_PROMPT_BODY_MAX_CHARS = 2000` 字符
  （`sentiment_pipeline.py` 单一收口点，entity/sentiment 两阶段共用）。
  分类/打分只需要标题+导语，full_content 全文灌入可达 10k+ 字符，
  预计砍 stage-1/2 prompt token 50-80%。
- 翻译：`_MAX_INPUT_CHARS` 30000 → 16000。**注意这是折中**：
  30k 是 2026-07-27 为「全文翻译质量」刻意从 12k 提上来的；
  现在重要性门已把正文翻译量砍 ~90%，量由门控制，长度是剩余杠杆。
  16k 字符 ≈ 4-5k tok，覆盖绝大多数长文不截断，峰值成本减半。

### P1-1 content_fetcher tier-3（LLM 正文抽取兜底）重要性门

- 新配置 `news_content_llm_min_importance: int = 3`（config.py）。
- `_extract_with_llm_tier` 开头查门：`importance` NULL 或 < 门 →
  跳过 LLM 层。tier-1（trafilatura）/ tier-2（Jina）不受门控。
- **NULL 不烧**的设计依据：入库即抓的新文 importance 必为 NULL，
  先走确定性层；分类管线（P0-1 修复后覆盖率→~100%）落章后，
  `news_full_content_10m` drain 会自动捡回重要文章的正文。
  与翻译/摘要门同一逻辑：**不值得翻译的文章，也不值得花 8k tok 救正文**。

## 二、ECS 侧已执行项（无需代码）

| 项 | 操作 | 效果 |
|---|---|---|
| 备份 retention 5→3 | crontab `RETENTION_DAYS=5→3` + 手动删 >3 天旧备份 | **-14.4G**（/data 74G→60G，66%→53%） |
| journald  vacuum | `journalctl --vacuum-size=500M` | -358M |

**未动**：docker prune（2026-08-04 裸 prune 删 nginx 致断站 20h 事故，
只能走受控清理）；cninfo_pdfs 15G（提取信心低，先升级管线再谈删）。

## 三、验证

- `pytest` 全量：**1930+ 通过**（新增 10 个测试：落章回归 / 缓存自愈 /
  prompt 截断 / 慢调用保留 / attempts 计数与封顶 / tier-3 门三态）。
- `ruff check` 改动文件全绿；alembic 单头 `e2f4a6b8c0d3`。
- black 未跑全文件格式化（仓库存量非 black-clean，CI 只 gate ruff，
  避免格式churn 污染 commit）。

## 四、部署注意

- 含迁移 `e2f4a6b8c0d3`（research_reports 加列，server_default 0，
  存量行自动回填）——backend 容器启动命令自动 `alembic upgrade head`。
- 部署后 importance 覆盖率会随分类管线爬升（缓存命中自愈 + 新文落章），
  翻译/摘要/tier-3 三个门的有效半径随之恢复——**门后量级预计从
  「几乎为零」回升到「≥3 文章的正常水平」，这是设计意图不是回归**，
  观察一周 token 曲线确认总量仍远低于门前。

## 五、口诀（新增）

- **「LLM 处理过就必须落章，哪怕是空结果——否则选择集永不清空」**
  （P0-1 根因，与 2026-08-02 翻译封顶事故同源：跳过≠失败，但跳过必须留痕）
- **「超时可以丢弃结果，但阈值必须匹配 provider 常态延迟」**
  （P0-2：DeepSeek 时代 5s 阈值在 MiniMax 30-160s 常态下 = 100% 白烧）
- **「门控三段式：WHERE 层排除（不占窗口）+ 落章驱动（覆盖率即半径）+
  失败计数封顶（每日回池）」**——三个门（翻译/摘要/tier-3）共用同一套
  语义，新增 LLM 消费方时照抄。

## 六、待用户决策（本轮做不了）

- **A：LLM 链配 key**——ECS .env 加 GLM_API_KEY / KIMI_API_KEY
  （链立即三棒齐活），或 `LLM_PROVIDER_CHAIN` 加 deepseek
  （key 已在生产，需先确认余额）。digest 已连续 13 天占位，配 key 后
  需补跑死日报。
- **C：实例降配 4C/16G → 4C/8G（e-c1m2.xlarge）**——峰值验证结论：
  OOM 是 backend 撞自身 3G 容器限额（主机当时闲 9.7G），CPU 峰值仅
  ~48%（09:10 指标链）/ ~42%（02:40 备份），内存峰值 33%——降 8G
  内存零风险，CPU 余量原样保留，celery -c 4 不用动。控制台操作。
- backend 内存膨胀（2.5 天涨到 3G 限额）根治：泄漏排查或临时
  限额 3G→4G + 低峰定时重启兜底。
