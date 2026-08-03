# 2026-08-03 深夜冲刺交付报告

> 覆盖三条主线 + 一起生产事故的完整交付。所有 commit 已 push，CI/Deploy 全绿。

## 一、交付总览

| 主线 | 状态 | 关键产出 |
|---|---|---|
| 每日 AI 综合研报 | ✅ 已上线（前段会话） | 06:30 自动出报 + 四渠道；commits 0288a3f/f42573a/7e2156f/6aabbd3/fc240c5 |
| cninfo PDF→MD 管线 | ✅ B2 上线，B3 全量重提运行中 | pymupdf4llm 管线 + 迁移 c4d6e8f0a2b4 + 删除脚本；~47h 重提后删 PDF 省 13.5GB |
| Web UI 全面优化 | ✅ 两批已部署 | 设计系统收敛 + 移动端 P0×3 + 错误态体系 + 焦点管理，78 文件 |
| 原生 iOS/macOS 应用 | ✅ 地基+六模块 | 全原生 SwiftUI 单 target 双平台，39→60+ 文件，无 WebView/Catalyst |
| Tushare token 事故 | ✅ 已修复回填 | A股个股日线灭 5 天根因=生产 .env 占位符，已回填 7/27-8/3 |

## 二、cninfo PDF → Markdown（方案 A：先升级管线再删 PDF）

**背景**：11,663 个 PDF / 14.0GB（/data 88% 已用的 14%）。旧提取链表格列结构全丢、
12.7% 撞 200k 截断，「准确完整 md」信心低。

**B1 选型（实证）**：pymupdf4llm —— 无边框财务报表**完美还原为 md 表格**、0.344s/页、
无截断；3/11,660 打不开走旧链 fallback。AGPL-3.0：仓库公开满足 §13。

**B2 已上线**（commit 0665367）：
- 迁移 `c4d6e8f0a2b4`：+extracted_format / +md_path（生产已 apply）
- `extract_markdown()` 主链 + fallback + HTML 噪音剥除；md 写盘存档 `{MD_DIR}/{stock_code}/{announcement_id}.md`
- `reextract_cninfo_md` 分片任务 + 删除脚本（dry-run 默认）+ 10 测试
- runbook：`docs/dev-notes/20260803-cninfo-md-pipeline.md`

**B3 进行中**：2026-08-03 21:26 启动全量重提（11,643 行，预计 ~47h）。
踩坑：新 volume root:root 而 celery 跑 uid 999 → EACCES，已 chown 修复；
4 行漏写已 reset 回池。**B4（验收+删 PDF）待重提完成后执行**。

## 三、Web UI 优化（审计驱动）

四轮审计（桌面核心/数据页/移动端/设计系统）→ 三批修复（commits cbe3ae3 + 71f7e42，
78 文件，stylelint+tsc+build+71 vitest 全绿）：

1. **设计系统收敛**：图表取色单一事实源（chartColors.ts，8 消费方迁移）、
   第一代 density token 全退役（9 个）、幽灵 token 修复、<12px 字号违例清零、
   skip-to-content。
2. **移动端 P0×3**：GlobalMarkets 死类幽灵列 → columns 剔除；Microstructure
   四 tab 宽表 → 行式卡片降级（可点行进详情）；EtfHoldingsHistory 375px 布局。
3. **错误态体系**：新组件 ErrorState，11+ 页 isError 接线——接口失败不再伪装成
   「暂无数据」。
4. **焦点管理**：DetailDrawer 焦点移入/focus trap/兄弟容器 inert 三件套。
5. **共享渲染管线**：prepareNewsBody + NewsMarkdown（detail 页与抽屉统一）、
   情绪双标度统一（normalizeSentimentScore）、ResearchReports 服务端排序
   （后端 sortable +target_price）。

*注：子 agent 配额中途耗尽（API 403），7 个 agent 的部分编辑由主会话逐个审查、
修复两处半完成重构（ETLOpsDashboard 注释位置、ResearchReports 类型错误）后全部抢救上岸。*

## 四、原生 iOS/macOS 应用（ADResearch）

**全原生**：SwiftUI 多平台单 target（iOS 17+/macOS 14+），无 WebView、无 Catalyst、
无跨平台框架；Markdown 用 AttributedString 原生渲染；JWT+Keychain 认证；
Xcode 16 文件系统同步组（加文件免改 pbxproj）。

**全部 11 个分区实装完成**（59 个 .swift 文件，~7000 行）：

| 分区 | 内容 |
|---|---|
| 首页 Dashboard | 全球资产脉搏 + 每日研报摘要卡（iOS 卡片堆叠 / macOS 三栏） |
| 研报 Digest | 今日研报卡 + 历史列表 + 阅读页（摘要卡/降级章节标注/partial 徽章） |
| 资讯 News | 双语资讯流（市场/重要性筛选 + 搜索防抖）+ 详情（译文切换/自动抓取正文/翻译按钮） |
| 宏观 Macro | 四区快照 + 实时指数墙 + 陈旧度横幅 + Swift Charts 历史详情（五档区间） |
| 标的 Instruments | 搜索/筛选列表 + 详情（信息卡 + sparkline 区间切换） |
| 行情 Markets | 加密实时行情列表 + 二级模块入口（iOS 主 tab） |
| 板块 Sectors | GICS/申万切换 + 市场均值 + 轮动信号 + 相对强弱/动量排名 |
| 情绪 Sentiment | 多空总览 + 标的情绪列表 + 14 日迷你走势 |
| 学习 Learning | 推荐/收藏双 tab + 主题 chip 条 + 难度标签 + 左滑收藏 + 已读降权 |
| 组合 Portfolio | 自选 + 标的池 + 左滑移除（乐观更新+失败回滚）+ 空态引导 |
| 研究 Research | 研究笔记列表 + 类型筛选 + sheet 详情 |
| 我的 Settings | 用户信息卡 + 关于（版本/构建号）+ 登出确认 |

契约核对发现并处理了 10+ 处 web ts 类型与后端真实 schema 的漂移（MarketSnapshot 字段名、
change_pct 单位、情绪 instrument_code、market=a_share≠cn_a、板块小数×100、
/crypto 忽略 sort_by 等）——原生端一律以后端 Pydantic schema 为准。

**打开方式**：装 Xcode 16+ → 双击 `native/ADResearch/ADResearch.xcodeproj` → 选 scheme
⌘R（首次需选签名 Team）。详见 native/ADResearch/README.md。
验收：全部 59 个 .swift 过 `swiftc -parse` 双目标（macOS + arm64-ios17）零 error。
设计规范统一：AppTheme 语义 token（红涨绿跌）、骨架屏/LoadErrorView/EmptyStateView
三态、refreshable + ⌘R 刷新广播、ChangeText 等宽数字、动态字号。

## 五、生产事故：Tushare token 占位符（日线缺失根因）

用户报告「标的日线最近几日缺失」→ 子 agent 取证锁定：**生产 .env 的 TUSHARE_TOKEN
是 .env.example 占位符**（7/27 改 .env 时丢失，etl_log 首败 7/27 08:00 UTC
"您的token不对" 实锤）。影响：A股个股日线 7/27-7/31 缺 5 天 ×5521 行 + 估值同窗口 +
指标/评分停更。

**已闭环**：真 token 写回（备份 /root/.env.bak-20260803-tushare）→ 重建 backend →
回填日线+估值 7/27-8/3（每天 ~5520 行全 success）→ 指标重算 8/3（7096 codes）。
**第三次 .env 漂移事故**，建议 verify_post_deploy.sh 加占位符探测（待办）。
次要发现：TIINGO_API_KEY 未配（美股备用源单点风险）。

## 六、后续待办

1. 明早验证 06:30 digest 首次定时出报（etl_log job_name='daily_digest'）
2. PDF B4：重提完成（~8/5 晚）后验收 md 覆盖率 → dry-run → 删 PDF（-13.5GB）；
   铁律：删后绝不重跑旧日期 download 分片
3. 邮件渠道：需用户配 SMTP_*；TG：需用户 BotFather 建 bot
4. native 应用：用户装 Xcode 后真机编译验证；旧 ios/ADResearch/ 目录待用户确认删除
5. verify_post_deploy.sh 加 .env 占位符探测；TIINGO key 补配
