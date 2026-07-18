# 2026-07-18 夜间研究任务规范

> 任务： overnight research on 中国经济社会运行机制、投资大佬公开讲话、学术研究、行业深度、历史事件-市场反应，最终形成可搜索数据库 + 中文报告。
> 周期：约 20 小时。
> 输出目录：`docs/research/20260718-overnight-research/`

## 输出要求

每个子 agent 必须产出：
1. 一份 Markdown 摘要：`raw/<topic>.md`
2. 一份结构化 JSON：`raw/<topic>.json`（数组，每条记录一个对象）
3. 所有来源必须带 URL、访问时间（`accessed_at`）。

## JSON 记录通用字段

```json
{
  "id": "唯一ID（slug 或 UUID）",
  "title": "标题/主题",
  "source": "来源名称",
  "url": "来源URL",
  "date": "原始日期（YYYY-MM-DD，未知则空）",
  "accessed_at": "2026-07-18",
  "category": "机制 / 讲话 / 论文 / 行业 / 事件",
  "tags": ["tag1", "tag2"],
  "summary": "中文摘要（300-800字）",
  "key_points": ["要点1", "要点2"],
  "related_sectors": ["新能源", "半导体"],
  "related_tickers": ["510300.SH", "159915.SZ"],
  "impact": "对A股/美股的潜在影响方向（看多/看空/结构性/长期）",
  "original_language": "zh / en",
  "translated": true
}
```

## 主题划分

1. `china_mechanisms` — 中国社会、政治、经济运行机制
2. `investor_speeches` — 投资大佬公开讲话与分享
3. `academic_research` — 学术研究（资产定价、宏观因子、A股实证、行为金融）
4. `industry_deep_dive` — 代表性行业深度（新能源、半导体、金融、消费、房地产）
5. `event_cases` — 历史事件-市场反应案例

## 数据库构建

由整合 agent 读取所有 `raw/*.json`，写入 SQLite：`db/overnight_research.db`。
表名与各 JSON category 对应，字段与 JSON schema 一致，并加 FTS（全文搜索）索引。

## 最终报告

整合 agent 基于数据库撰写中文报告：`report.md` + `report.html`。
报告需包含：
- 执行摘要
- 五大主题核心发现
- 投资研究框架（如何将发现接入平台）
- 可接入平台的结构化数据说明
- 后续建议

## 约束

- 以中文输出为主；英文内容需翻译成中文并在 `original_language` 标注。
- 无明确排除人物；投资大佬覆盖中外（如巴菲特、芒格、达里奥、李录、高毅、张坤、但斌等）。
- 不接受付费墙内容；优先公开可访问来源。
- 不承诺 100% 覆盖；优先高质量、高可信度来源。
