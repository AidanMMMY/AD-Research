# 2026-08-01 桌面去卡片化冲刺 + 繁转简 + LLM 切 DeepSeek 综合 runbook

## 1. 桌面去卡片化冲刺（b59e5aa / 5a7120b / 873839e）

按 `20260729-mobile-ui-redesign-research.md` 决策（排版代替容器）向桌面延伸，三个并行子 agent 完成 8 页 15 文件，零共享组件/零业务逻辑改动：

| 组 | 页面 | 改动 |
|---|---|---|
| A | StrategyLibrary / PoolList / SentimentDashboard | 自研卡片网格 → hairline 行式列表；摘 glass-card |
| B | InstrumentDetail / StockDetail | 9/11 段堆叠 → 双列核心区（K线 + 关键数据右栏 360px）+ 分区合并；StockDetail 6 tab → 4 tab，K线常驻 |
| C | GlobalMarkets / PaperTrading / TradingPanel | 7/7/9 Panel → 3/3/5；统计卡合成 KPI strip；下单按钮并入 Panel header |

**遗留（下轮）**：`.strategy-card` 基础样式下沉清理（components-cleanup.css）、TypeAwareModules 卡中卡、StatCard `bordered` 死参数、KPI strip 提炼共享类。

## 2. 繁体资讯自动转简体（219fa8a）

- **转换点**：`NewsNormalizer.normalize`（ingest 唯一入口）+ `ContentFetcher.fetch`（全文补抓）双汇合点
- **防误转**：中文变体语言门控 + ~130 繁体专属字符特征检测（排除两岸同形字）
- **依赖**：opencc-python-reimplemented（纯 Python）
- **存量回填**：`scripts/backfill_zh_traditional_to_simplified.py`（幂等、id 游标分批）——**注意容器内 `/app/scripts` 只有 entrypoint，repo scripts 不进镜像，需 `docker cp` 进容器跑**（本次：`docker cp /tmp/backfill_zh_traditional_to_simplified.py alloyresearch-backend:/tmp/` 后 `PYTHONPATH=/app python3 /tmp/...`）。已执行：608 行 / 2253 字段转换完成

## 3. LLM 主链路 MiniMax → DeepSeek

- 代码侧：sentiment_pipeline 收编进 `get_llm_provider` 统一抽象（e7a8628）
- 配置侧：ECS `.env` `LLM_PROVIDER=deepseek` + DEEPSEEK_API_KEY，MiniMax key 已注释保留（回滚：恢复 `/root/.env.bak-20260801` + recreate backend）
- 生产验证：`get_llm_provider()` → DeepSeekProvider / deepseek-v4-flash，实调成功
- **切换后观察项**：MiniMax 时代的 422 sensitive 翻译失败是否消失（translation_attempts>=5 行数变化）

## 4. 部署事故与 tripwire（新增 #6）

- **Deploy 首次失败 13s**：DeepSeek 子 agent 在 `/opt/ad-research/deploy/aliyun-ecs/` 留了 `.env.bak-20260801`，Sync 步骤的脏树检查**把未跟踪文件也算脏**。修复：`mv` 到 `/root/` 后 rerun 即过。**教训：ECS 上任何临时文件（备份/脚本/日志）都不要留在 git 仓库目录内，放 /root 或 /tmp。**
- **Backend CI 红（futures_pipeline 7 个失败）**：干净树复现的**既有问题**（与今日所有改动无关），但导致 main 上 CI 持续红色，掩盖真实回归——建议下轮优先修。

## 5. 当日全量验证

- `/health` ok（git_sha 219fa8a）、check:ci 全绿、620 news 测试全绿
- 翻译 drain 积压 18.7k → 持续排空中
- 评分排名三市场正常（fb12896）
