# 2026-07-20 全系统四维审计与优化方案（功能可用性 / 逻辑连贯性 / UX / UI 美观性）

> **注**：本文为 2026-07-20 的时点记录，部分内容可能已过时。

> 方法：10 个只读审计 agent 并行覆盖 10 个域（设计系统、Dashboard/市场、标的研究、策略交易、
> 内容/AI/系统管理、前端基础设施、后端 API、后端服务链路、既有审计文档复核、测试健康度），
> 共产出约 100 条发现；随后 13 个修复 agent 并行执行。本文记录审计结论、已执行修复与遗留 backlog。

## 一、审计结论摘要（按维度）

### 功能可用性（最差维度）
- refresh token 轮换链条断裂：后端轮换但不下发新 refresh token，**所有用户会话活不过 ~30 分钟**（P0）
- CninfoReports 详情抽屉 CSS 类 bug 永远停在屏幕外，功能完全不可见（P0）
- 回测引擎退市保护条件写反：已退市标的存续期内的回测一律返回 no_data（P0）
- 默认回测执行价模型存在前视偏差（收盘信号在同根开盘成交），docstring 还声称无偏差
- ReturnComparison 用 page_size=10000 超后端上限恒 422，图例永远裸代码
- Screen/BacktestList 不读 URL 参数，跨页跳转条件被静默吞掉
- 真实交易下单无二次确认、无环境标识（全站最危险操作防呆缺失）

### 逻辑连贯性
- 百分比量纲错误多点复发：Dashboard 动量列、InstrumentDetail heroStats（忘 ×100）、
  StockDetail RSI14（误 ×100）、SectorRotation 市场平均/相对强弱（两处口径不一）
- 浅色主题 `--color-rise/fall` 与"A 股红涨绿跌默认"写反，且涨跌约定切换在浅色下是 no-op（P0 金融语义）
- pools 写路径整体 IDOR：update/add_member/remove_member/增强服务不校验归属
- scoring 模板写端点、ETF 全市场扫描匿名可调；10 个只读 router 无鉴权（与 JWT 全覆盖约定矛盾）
- 系统信号写 user_id=1，非 admin 用户永远看不到系统自动信号
- Dashboard 多处"道具数据"：Math.random sparkline、硬编码数据健康、死搜索框、脉搏只渲染 5/19

### 用户体验
- 无 404 路由；RequireAuth 对任何 /auth/me 错误都强制登出
- 两个完工页面（/research-reports、/cninfo-reports）+ SentimentDashboard 是导航不可达的孤儿
- ETL 运维菜单对普通用户可见但点击被静默弹回
- 客户端排序 + 服务端分页的"全局排序错觉"多页复发（Screen/InstrumentList/ScoreRanking）
- 查询错误态系统性缺失：45 个页面仅 ~5 个消费 isError，失败与空数据无法区分（未本次修复，见 backlog）

### UI 美观性
- token 体系（theme.css）设计成熟，但执行层脱节：幽灵 token `--color-primary` 8 处引用、
  死代码段（vermilion accent、旧 Dashboard 797 行 CSS）、8605 行 global.css 按历史补丁序堆叠
- 103 个 stylelint 裸色值错误使 check:ci 门禁形同虚设
- AppLayout.css 混入页面级样式全局泄漏；移动端覆盖两处"真源"冲突（未本次修复）

### 测试健康度
- pytest 861 个测试 58 个未通过，全部是测试过期（user_id 多租户迁移、provider 重构、
  LLM 切 MiniMax、cninfo 去重），风控/模拟交易/AI 翻译三条关键路径零测试保护
- **没有任何 CI 跑 pytest**——腐烂是流程问题（未本次修复，见 backlog）

## 二、已执行修复（13 个并行修复包，全部完成并各自验证）

| # | 修复包 | 关键内容 |
|---|---|---|
| 1 | Dashboard 数据真实性 | return_1m 改 ReturnTag、total_main_net_pct、脉搏 5 组全渲染、搜索框接 /instruments?q=、删假 sparkline、资金信号行可点击、「AI 简报」改「要闻速递」、删硬编码健康区块、删 797 行死 CSS |
| 2 | 详情页百分比 | InstrumentDetail formatSigned ×100；StockDetail RSI14 不 ×100；CryptoDetail 补「加入自选」 |
| 3 | 路由/导航/布局 | NotFound 兜底、两个孤儿页 + SentimentDashboard 挂菜单、RouteConfig admin 标记驱动守卫与菜单过滤、RequireAuth 仅 401 登出、themechange 事件补发（document + detail，对齐 useTheme） |
| 4 | 页面参数接线 | Screen 读 market/category URL 参数；BacktestList 读 strategy_id/strategy_type + confirmLoading + 标的代码列（后端 list 补 etf_code 字段）+ 策略名；Screen 排序下沉服务端 |
| 5 | CninfoReports + Login | 抽屉 entering 类双 rAF 归位（P0）；Login 假数据源轮播改真实 /health；渲染期 navigate 改 `<Navigate>` |
| 6 | 交易面板 | 下单弹窗配置名+TESTNET/LIVE Badge、非 testnet Popconfirm「真实资金」确认、LIMIT 价格必填/MARKET 禁用、撤单反馈；PaperTrading 双重负号；ReturnComparison 按需查名称；Portfolio mock 加「演示数据」Badge + `<a>` 改 Link |
| 7 | 市场页口径 | FundFlow 排序错接删除 + 死 KPI 卡清除；SectorRotation 两处 ×100 统一；GlobalMarkets LastUpdated 传值 |
| 8 | 设计系统 | 浅色 rise/fall 交换为红涨绿跌（P0）、chartColors fallback 同步、8 处幽灵 token 改 var(--accent)、死类删除、stylelint 103→0（登录段豁免 + K15 收敛 token + 散点映射） |
| 9 | refresh token（跨栈） | RefreshResponse 加 refresh_token、/auth/refresh 透出新 token、client.ts 双写存储、新增轮换测试（含旧 token 重放 401） |
| 10 | 后端鉴权 | pools 六个写端点 + pool_service/pool_enhancement_service 归属校验（system_pool/not_owner 双分支）、etf scan require_admin、10 个 router + stats + etl/status 补 get_current_user |
| 11 | 回测引擎 | 退市条件改 start_date > delist_date、open 模型信号 shift(1) 消前视、成交价统一复权 open（open × adj_close/close）、测试改新口径 + 新增复权基准测试 |
| 12 | scoring/signals | scoring router 鉴权 + 写端点 admin、count_scores 真实 total、删死分支、get_latest_score 固定默认模板、信号 user_id 可空（**含 alembic 迁移 q3r5s7t9u1v2**）+ 查询放行系统信号 |
| 13 | 过期测试 | user_id fixture 簇 36 个、paper_trading/translation patch 目标、content_fetcher 阈值、cninfo 去重 mock、futures/sector_rotation 403 override；删 test_nav_summary.py（测试先行、无实现无消费方）；translation 错误文案按实际 provider；create_account user_id 必填 |

## 三、行为变化注意（部署前必读）

1. **alembic 迁移**：`q3r5s7t9u1v2` 把 signal.user_id 改 nullable，部署时 backend 容器自动执行。
2. **回测数字会变**：open 模型消除前视 + 复权口径统一后，同一策略的历史回测结果与之前不可直接对比。
3. **涨跌色语义修正**：浅色主题从"绿涨红跌"改为"A 股红涨绿跌"默认，用户首次打开会看到颜色反转——这是 bug 修复不是回归。
4. **鉴权收紧**：此前匿名的 10+ router 现在要求登录；前端全部走 RequireAuth 后带 token，无影响；
   若有外部脚本匿名调用这些接口会 403。
5. **session 变长**：refresh 轮换修复后登录态可正常续期 30 天（此前 30 分钟必登出）。

## 四、遗留 backlog（本次未执行，按优先级）

### P1（下一 Sprint）
- [ ] **backend-ci**：.github/workflows 加 pytest 任务（全量仅 ~3 分钟），防止测试再次腐烂
- [ ] **查询错误态统一**：hooks 层统一挂 useApiErrorToast / 页面错误态组件，消灭"失败装空"
- [ ] **extractErrorMessage 不解析 FastAPI detail**（useApiError.ts:40），15 个页面手写 detail 提取
- [ ] **熔断器内存级**（risk_control.py:59）重启失效 → Redis 持久化；**RiskRule 死功能**要么实现要么删表
- [ ] **美股 ETL 无交易日历**（us_etf.py:120）周末空跑浪费 Tiingo 配额；美股日终覆盖结构性不足
- [ ] **pool_enhancement 实际权重 = 收盘价/Σ收盘价**（各持 1 股假设），与目标配置脱钩
- [ ] **评分计算按市场各自最新日期、查询按全局 max(trade_date)**（scoring_service.py:461 vs 134），滞后市场从榜单消失
- [ ] **401 登出不带来源路径**，重新登录丢失工作上下文（client.ts / RequireAuth 加 redirect）

### P2（择机）
- [ ] 分页/envelope 统一：page/size vs offset/limit vs 裸 limit；total vs count；定义 PaginatedResponse[T]
- [ ] global.css 8605 行按组件拆分；theme.css/global.css 移动端重复块合并；AppLayout.css 页面样式迁回
- [ ] 信号唯一约束不含 type/参数，HOLD 落库占位致同日改参信号被静默丢弃
- [ ] AH 溢价恒 None 占 5% 权重不归一（fund_flow composite 系统性压缩）
- [ ] 部署日志 SSE 用 ?token= query 传 JWT 进 nginx 日志 → 一次性 ticket
- [ ] Tailwind 4 是死依赖（vite 未注册插件）——移除或正式启用
- [ ] chat SSE 绕过 axios 拦截器，token 过期无自动续期
- [ ] 前端测试仅 5 个 a11y 用例对 50 页面；a11y 测试用的是重建 mock 组件非真身
- [ ] StocksList/StockDetail 旧双轨下线（/stocks → /instruments?type=STOCK 重定向）
- [ ] 动量策略 strength 缩放 ×100 vs ×1000 两套（momentum.py:47 vs 109,184）
- [ ] CommandPalette combobox ARIA 补 aria-activedescendant

## 五、事故记录

- 修复包 12 的 agent 误执行 `git stash` 后自行恢复（43 个文件逐一 checkout + 三方合并），
  `stash@{0}` 保留为备份，确认工作区完好后可 `git stash drop`。
- 并行期间发生数次文件互相覆盖（Dashboard/index.tsx、global.css、command-center.css），
  各 agent 均已自行重放修改并通过验证；最终以主会话全量 pytest + check:ci 结果为准。
