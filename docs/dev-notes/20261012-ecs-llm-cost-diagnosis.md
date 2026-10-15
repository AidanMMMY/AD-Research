# 2026-10-12 ECS 资源 + LLM token 全面诊断报告

> 触发：用户反馈 ECS 和 token 开支无法忍受。三个子 agent 并行：
> 资源体检（生产实测）/ token 消耗实测（生产实测，94 天计量）/
> 浪费点代码审计（本地）。本报告为汇总，全部只读未改动生产。

## 〇、TL;DR（钱在哪）

| 层 | 现状 | 最大浪费 | 可省 |
|---|---|---|---|
| ECS 实例 | 4C/16G 香港，CPU<20% 内存 36% | **规格超配一倍** | 降 2C/8G 省实例费 **40-50%** |
| ECS 磁盘 | 73G/118G | 备份 29G + cninfo PDF 15G | 立省 ~25G |
| LLM token | 门前峰值 12-20M tok/天，门后 0.6-0.8M | **切换链没配 key 形同虚设 + 情绪管线毒丸队列周期性重烧** | 见下 |

## 一、LLM token 实测（94 天 Redis 计量 + DB 代理量）

### 1.1 消耗时间序列（分割线是 9/29 重要性门上线）

| 期 | 情绪管线计量 | 正文翻译（DB） | 全站估算 |
|---|---|---|---|
| 门前活跃日（MiniMax 可用） | 7-11M tok/天 | 8-16M tok/天 | **12-20M tok/天** |
| 门后两周 | ~0.6M tok/天 | ≈0.04M | **~0.7M tok/天** |

**周配额周期清晰可见**：周一前后重置 → 周三/四烧穿 → 归零到周末。

### 1.2 三个必须直面的真相

1. **重要性门效果超预期但已变形**：正文翻译 27,147 → 131 篇/周
   （-99.5%）。设计是「只翻 ≥3」，实际是分类管线因 MiniMax 枯竭
   跑不动（近 7 天 98% 文章 importance=NULL）→ 门永远不开。
   「LLM 越不可用 → 门后翻译越少」的正反馈。
2. **切换链形同虚设**：ECS 上 `GLM_API_KEY`/`KIMI_API_KEY` 长度
   为 0——9/28 部署后至今未配。`active_chain=[minimax]`，
   MiniMax 处于「6h 冷却→重试→2056→再冷却」死循环（24h 内冷却
   触发 12 次），**每日研报连续 13 天六节全占位（278 字）**。
3. **DeepSeek key 配着但被浪费**：默认链 minimax,glm,kimi 不含
   deepseek，legacy 扫描只在链全空时触发——现成兜底被排除。

### 1.3 计量盲区

只有情绪管线接 `record_call`；翻译/摘要/digest 不计量。
`run_nightly_flush` 是摆设——`llm_usage_daily` 表不存在，只打一行
日志。建议：计量扩展到全部消费方 + flush 真落库（否则成本永远
只能靠 DB 代理量估算）。

## 二、结构性浪费（代码审计，按 ROI 排序）

### P0-1 情绪管线「永不落章」毒丸队列 ⭐最大
`sentiment_pipeline.py:546`：抽不出标的符号的文章直接 return，
**LLM 费已付但 event_category/importance/sentiment_processed_at
全部丢弃** → 永久留在两个 job 的选择集里，30 天缓存到期后重新
完整烧一遍，无限循环。这同时解释了 importance 覆盖率仅 ~15%
（门的有效半径被卡死）。**修复：无 scores 也写回三字段**，
一行级改动，消灭毒丸 + 覆盖率→~100%。

### P0-2 研报摘要「>5s 丢弃」100% 白烧
`research_report_service.py:349`：DeepSeek 时代的 5s 阈值，
MiniMax 常态 30-160s → **token 付了结果被扔**，每 2h 重试 20 条
无 attempts 上限，永久循环。修复：删阈值 + 加 attempts 封顶。

### P1 级
- **P1-2 prompt 不截断**：分类管线把 full_content（可达 10k 字符）
  全文灌入；截到 1500-2000 字符砍 50-80%（分类只需开头+标题）。
  翻译 `_MAX_INPUT_CHARS` 30000 也偏高。
- **P1-1 content_fetcher LLM 兜底无重要性门**：Jina 欠费窗口期是
  隐藏巨鲸（单篇可达 8k tok）。
- **P1-3 digest 同一 news 包重复发 5 次**：~0.7M tok/月冗余。

### P2 资源类
- `sentiment_batch_30s`：SentimentData 表唯一写入方是手动 API，
  近乎死表，却每 30s 全表扫（url varchar(1000) 无索引）2880 次/天
- `sentiment_low_latency_5m`：选择集是 batch 的真子集且无 NOT
  EXISTS 守卫，纯重叠 churn，可删
- `sentiment_retail_agg_30m`：自述 no-op（retail_comment 表不存在）
- `duplicate_of` 标记无人消费：跨源重复文章全部进 LLM
- 凌晨 1-6 点 8 个资讯抓取 job 全速空转

## 三、ECS 资源实测

| 维度 | 规格 | 实际 | 结论 |
|---|---|---|---|
| CPU | 4 核 | 常态 10-20% | 过剩 |
| 内存 | 14G | 36% | 过剩（backend RSS 2.5G/3G 上限有膨胀嫌疑，2.5 天涨到此） |
| 数据盘 | 118G | 73G | 备份 29G + docker 卷 40.8G（PG 23.3G + cninfo PDF 15G） |

**可立即回收 ~25-30G**：备份 retention 5→3（-9.6G）+ cninfo_pdfs
决策（-15G）+ build cache/journald（-1.2G）。
**降配是唯一大钱**：e-c1m4.xlarge(4C/16G) → large(2C/8G)，注意
celery indicator worker `-c 4` 需同步降到 2。香港 region 是刻意的
（外网源+免 ICP），不动。

## 四、行动清单（按见效速度排序）

**今天就能做（纯配置）**：
1. ECS .env 加 `GLM_API_KEY`/`KIMI_API_KEY` → 链立即三棒齐活，
   研报/翻译/分类全部复活
2. 或更快：`LLM_PROVIDER_CHAIN=minimax,deepseek,glm,kimi`（DeepSeek
   key 已在生产，前提是余额已充）

**代码快赢（本轮一起做掉）**：
3. P0-1 落章修复（sentiment_pipeline.py:546）
4. P0-2 研报摘要删 5s 阈值 + attempts 封顶
5. P1-2 prompt 截断
6. P1-1 content_fetcher 加重要性门

**ECS 账单（需要停机窗口/控制台操作）**：
7. 实例降配 4C/16G → 2C/8G（celery 并发同步降 2）
8. 备份 retention 5→3 天
9. cninfo_pdfs 15G 去留决策（记忆：提取信心低，先升级管线再谈删）

**中期**：
10. 计量扩展到翻译/摘要/digest + nightly flush 真落库
11. 死/重 job 清理（batch_30s 降频、low_latency/retail_agg 删除）
12. duplicate_of 接入下游 WHERE + 每日 dedup job
