# Overnight 研究中间快照 #8

- **生成时间**：2026-07-19 04:19:02 UTC
- **数据来源**：公开网络搜索 + RSS/feed + LLM 结构化提取
- **记录总数**：143
- **高质量记录（quality_score >= 60）**：71

## 主题分布

| 主题 | 记录数 |
|------|--------|
| china_mechanisms | 56 |
| investor_speeches | 17 |
| academic_research | 3 |
| industry_deep_dive | 22 |
| event_cases | 45 |

## 改进说明

v2 相对 v1 的主要改进：
1. **Supervisor 循环**：theme agent 结束后自动换方向重新 spawn，避免空等 deadline。
2. **LLM 多 provider fallback**：Anthropic → OpenAI → DeepSeek → MiniMax。
3. **搜索与提取增强**：Jina Reader / Jina Search、SearXNG、RSS、readability-lxml、Playwright 兜底。
4. **增强记录字段**：核心论点、数据论据、影响链条、投资启示、风险点、质量分。
5. **跨主题去重与链接**：URL + title 相似度去重。
6. **中间快照**：每 2 小时生成 report_snapshot。

## 后续建议

1. 将 `overnight_research_v2.db` 同步到本地项目作为 RAG 知识库。
2. 接入平台 AI 问答模块。
3. 根据质量分对低质量记录做二次 LLM 提炼。
