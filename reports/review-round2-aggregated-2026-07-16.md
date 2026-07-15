# 第二轮资深用户审查综合报告（2026-07-16）

本轮共完成 7 份独立审查（其中宏观沿用第一轮 `review-macro-researcher.md`），合计 **~145 个 P0/P1 问题**。本报告按模块归类，并标注本轮已修 / 待修。

## 审查清单

| # | 报告 | 角色 | P0 | P1 | P2 |
|---|---|---|---|---|---|
| 1 | `review-a11y-mobile.md` | 资深 A11y / 移动端 | 5 | 9 | 7 |
| 2 | `review-news-analyst.md` | 资深新闻分析师 | 6 | 16 | - |
| 3 | `review-uiux-designer.md` | 资深 UI/UX 设计师 | 12 | 9 | 8 |
| 4 | `review-ops-admin.md` | 资深运营管理员 | 7 | 15 | 8 |
| 5 | `review-quant-deep.md` | 资深量化研究员 | 10 | 12 | 19 |
| 6 | `review-dataviz.md` | 数据可视化专家 | 6 | 6 | 6 |
| 7 | `review-macro-researcher.md` | 资深宏观研究员 | 6 | 13 | 8 |
| **合计** | | | **52** | **80** | **56** |

## 本轮已修复（commit `e0a2086`）

| 来源 | 问题 | 修复 |
|---|---|---|
| news P0-1 | 全文搜索功能完全失效（前端传 `q` 但后端无此参数） | `app/api/v1/news.py` `list_news` 新增 `q` 参数，标题/摘要/全文 ILIKE AND 多词搜索 |
| news P0-3 | 情绪标签口径分裂（bullish/bearish vs positive/negative） | `app/services/news/sentiment/sentiment_pipeline.py:477` 改写为 `positive/negative/neutral` |
| quant P0-1 | Sharpe RFR 永远 0.02，用户传 RFR 形同虚设 | `app/services/backtest_engine.py` `_simulate` 与 `metrics` 都接收 `risk_free_rate`，并透传到 Sharpe 公式 |

## 待修 P0 优先级排序（按"用户感知度 × 易修复度"）

### 一周内必须修（影响核心交互）

#### 1. News Jina 清洗阈值过严（news P0-5）
- **位置**：`app/services/news/content_fetcher.py:50`
- **影响**：80% 文章被标 `failed`，详情页刷红色 Alert
- **修复**：把 `MIN_BODY_LENGTH=20` 调到 80 或加入"原文摘要降级展示"

#### 2. 散户讨论面板永远空状态（news P0-4）
- **位置**：`web/src/pages/News/detail.tsx:578-592` vs `app/api/v1/news.py:668`
- **影响**：后端 API 已实现，前端从未调用
- **修复**：前端调用 `newsApi.retailSentiment(symbol)`，移除"Agent E 后续接入"占位文案

#### 3. 跨源去重死代码（news P0-2）
- **位置**：`app/services/news/dedup.py` 与 `normalizer.py:90-160`
- **影响**：同一事件被多家媒体刷量 3 遍，情绪聚合失真
- **修复**：在 `NewsNormalizer.normalize` 中调用 `is_duplicate` 与 `normalized_content_key`，落库前合并

#### 4. A 股 ETF 实时报价字段统一（trader P0-1，已在第一轮修）
- ✅ 已修 `app/data/providers/akshare_provider.py` 中文列名标准化

#### 5. 登录 Label / aria-label 缺失（a11y P0-1）
- **位置**：`web/src/pages/Login.tsx:243-305`
- **影响**：屏幕阅读器无法识别输入框
- **修复**：用 `<Form.Item label="...">` 包裹，或加 `aria-label`

#### 6. 仪表板 StatCard 键盘不可达（a11y P0-2）
- **位置**：`web/src/components/StatCard.tsx:38-41`
- **影响**：键盘用户无法点击 KPI 卡片
- **修复**：加 `role="link"` `tabIndex={0}` `onKeyDown` 处理 Enter/Space

#### 7. TickerTape 60s 滚动无法暂停（a11y P0-4）
- **位置**：`web/src/components/TickerTape.tsx:140-187`
- **影响**：动效 + 颜色仅区分（违反 SC 1.4.1）
- **修复**：加 `prefers-reduced-motion` 检测，hover 暂停；增加箭头/趋势图标

#### 8. KLineChart 纯 canvas 零可访问（a11y P0-5）
- **位置**：`web/src/components/KLineChart.tsx:418`
- **影响**：屏幕阅读器看不到 K 线数据
- **修复**：提供 `<table>` 替代视图（aria-hidden + sr-only 详细数据）

#### 9. 涨跌色 Legend 在 A 股模式下文字写反（uiux P0-4）
- **位置**：`web/src/pages/News/index.tsx` 等
- **影响**：positive=绿 在 A 股红涨绿跌模式下误导
- **修复**：根据 `colorConvention` 动态切换 label 文案与图标

#### 10. 双 Card 系统并存（uiux P0-1）
- **位置**：`ant-card` 与 `ad-panel`
- **影响**：admin/portfolio/strategy-library 等仍用 antd Card，视觉分裂
- **修复**：抽 `Panel` 统一组件，逐步替换 ant-card

#### 11. ADMIN 写操作 0 审计日志（ops P0-1）
- **位置**：`app/api/v1/admin_users.py`、`admin_deployments.py`
- **影响**：谁在何时改了什么无法追溯
- **修复**：引入 `AuditLog` model + 中间件自动写所有 admin 路由

#### 12. 最后一名 admin 保护缺失（ops P0-2）
- **位置**：`app/api/v1/admin_users.py`
- **影响**：误删最后一个 admin 后无法恢复
- **修复**：role=admin 用户删除/降级前校验至少保留 1 个 active admin

#### 13. 推送 webhook URL 明文落 DB（ops P0-3）
- **位置**：`app/models/notification.py`
- **影响**：DB 泄露即泄露所有外部推送通道
- **修复**：使用 Fernet 加密 webhook URL，密钥从 env

#### 14. Docker socket 暴露给 web = admin 端 RCE（ops P0-4）
- **位置**：`docker-compose.yml`
- **影响**：admin 端可通过 docker API 在 host 执行任意命令
- **修复**：仅 admin 容器的 backend 挂载 socket；其他容器不挂

#### 15. 登录无 brute-force 限流（ops P0-5）
- **位置**：`app/api/v1/auth.py`
- **影响**：可暴力破解密码
- **修复**：按 IP/账号加 Redis 限流（5/min）

#### 16. ETL 失败 0 主动通知（ops P0-6）
- **位置**：`app/core/scheduler.py` ETL 失败路径
- **影响**：夜间 ETL 失败无人感知
- **修复**：在 `ETLPipeline.run` 失败时调用 `NotificationService.send_etl_alert`

#### 17. `SECRET_KEY` 默认值在源码里（ops P0-7）
- **位置**：`app/config.py`
- **影响**：生产若忘了 env，会使用公开的默认值
- **修复**：启动时检查默认值即拒绝启动

#### 18. 量化 Sharpe 年化用 252（quant P0-4）
- **位置**：`app/services/backtest_engine.py:400`
- **影响**：A 股 244、加密 365 全部算错
- **修复**：根据 `market` 字段选择 252/365/244

#### 19. NAV 净值曲线 CSS 变量直传 echarts（dataviz P0-1）
- **位置**：`web/src/pages/BacktestDetail/index.tsx:119-128`
- **影响**：echarts 不能解析 `var(--xxx)`，分割线/面积色全失效
- **修复**：走 `resolveChartColor`（其他组件正确路径）

#### 20. CorrelationHeatmap visualMap 用涨跌幅（dataviz P0-2）
- **位置**：`web/src/components/CorrelationHeatmap.tsx:128`
- **影响**：相关性不是涨跌幅，违反涨跌幅约定
- **修复**：发散色阶从 [-1, +1]，中心 0 = 中性灰

### 两周内修复（影响专业研究可信度）

- quant P0-2 完全无做空（`_simulate` 永远平多）
- quant P0-3 无真实基准（alpha/beta/IR 无法计算）
- quant P0-5 walk-forward 伪 OOS（不重选参数）
- quant P0-6 信号 look-ahead（trade_date 当日 bar 可见）
- quant P0-7 paper trading 无风控
- quant P0-8 auto_trade 不按强度缩放
- quant P0-9 缺 Sortino/Calmar/VaR/CVaR/回撤持续期
- quant P0-10 缺蒙特卡洛/bootstrap/显著性检验
- news P0-6 情绪分数 -100 vs -1 双口径
- dataviz P0-3 SectorRotation 硬编码 ±6% 域
- uiux P0-5 DensityToggle 幽灵控件（注释说删但还在）
- uiux P0-7 涨跌色约定切换在 News detail/Portfolio/PoolDetail 不生效
- uiux P0-8 空状态 60% 没有 icon（缺 first-time/no-results/coming-soon）
- ops P1-1 调度任务 UI 不可见
- ops P1-2 SSE query-param JWT 后门
- ops P1-3 APScheduler + Celery Beat 并存混乱
- ops P1-4 缺 ETL 重跑端点
- ops P1-5 缺数据修复工具
- ops P1-6 推送系统是死代码
- ops P1-7 stale 阈值不合理
- a11y P1-1 多个 drawer 缺焦点恢复（`useFocusRestore` 缺失）
- a11y P1-2 暗色 rise/fall token 小字号 3.2-4:1 过不到 AA
- a11y P1-3 `--text-tertiary` 白底 3.62:1 / `--text-muted` 1.60:1 不达标
- a11y P1-4 BUY/SELL/HOLD 纯颜色区分（违反 SC 1.4.1）
- a11y P1-5 触摸目标 < 44x44

### 一月内修复（系统性问题）

- uiux P0-2 ADX_STYLE 动效层在 6+ 页面 100% 重复 → 抽 `useChartMotion` hook
- uiux P0-3 30+ 处 inline `style={{var(--*)}}` → 全部走 token
- uiux P0-9 移动/平板断点图表与 Sticky Header 不完整
- uiux P0-10 `<Table showHeader={false}>` 破坏无障碍
- uiux P0-11 Loading/Empty/Error 三态分裂（5 Skeleton / 3 EmptyState / 2 Error）
- dataviz P0-4~6 + P1-1~6（图表库共享、themeTick 样板、reduced-motion）
- quant P1 全套（参数优化、敏感度、组合回测、做空、加减仓、再平衡）
- ops P1-9~15 多环境隔离、Docker socket 白名单、容器健康探针、日志聚合、配置版本化
- a11y P1-6~9 OnboardingTour 跳过链接、jest-axe/eslint-plugin-jsx-a11y CI、forced-colors 主题

## 缺失能力（按模块）

### News
- 跨源事件聚合 / event clustering
- source_trust_score 评级
- theme/industry 多层标签
- 个股 × 资讯因果归因
- 自托管 AI 兜底

### 量化
- 参数优化（网格/贝叶斯）
- walk-forward UI
- 蒙特卡洛 / bootstrap / 显著性检验
- 组合回测、目标权重、再平衡
- 多策略信号合成器
- 自定义策略导入
- 团队共享 + 权限

### 运营
- 会话管理（在线用户、踢下线）
- 调度任务 UI
- ETL 重跑 + 数据修复工具
- 日志聚合入口
- 灰度发布 / 金丝雀
- 多环境隔离

### UI/UX
- 命令面板（⌘K）
- 全局搜索
- 数据导出 CSV/Excel
- 打印样式
- 多语言（i18n）
- 深色模式跟随系统
- 性能预算 + Web Vitals

### A11y
- jest-axe 单元测试
- eslint-plugin-jsx-a11y CI 集成
- useFocusRestore hook
- KLineChart accessible alternate
- forced-colors 主题

## 修复路线图

| 周次 | 主题 | 目标 |
|---|---|---|
| Sprint W1 | 用户感知核心 | news P0-1/3/5/6, a11y P0-1/2/4/5, uiux P0-4 |
| Sprint W2 | 安全与权限 | ops P0-1~7 + ops P1-1/2/5/6 |
| Sprint W3 | 量化正确性 | quant P0-1~10, dataviz P0-1~3 |
| Sprint W4 | 视觉与 a11y 系统性 | uiux P0-2/3/5~11, a11y P1-1~9 |
| Sprint W5 | 量化增强 + 缺失能力 | quant P1, 缺失能力逐项启动 |

## 报告产出汇总

- `reports/review-senior-aggregated-2026-07-16.md`（第一轮 11 份 review 聚合）
- `reports/review-round2-aggregated-2026-07-16.md`（本轮 7 份 review 聚合）
- 单份：`review-a11y-mobile.md`、`review-news-analyst.md`、`review-uiux-designer.md`、`review-ops-admin.md`、`review-quant-deep.md`、`review-dataviz.md`、`review-macro-researcher.md`、`review-trader.md`、`review-platform-admin.md`、`review-quant-researcher.md`