# 2026-08-05 首页/研报故障全面排查 + /data 满盘全栈停摆复盘

> 一晚三连：两个存量 P0、一个契约漂移、一个我引入的热修 bug、一次磁盘满盘全栈停摆。
> 全部修复并部署，最终验证全绿。修复人 Claude（Aidan 报告「首页无法显示、研报无法加载全文」触发）。

## TL;DR

| # | 问题 | 根因 | 修复 | commit |
|---|---|---|---|---|
| 1 | 首页 KPI 永久转圈 | `/stats/overview/{metric}` 每个端点跑全量 8 条 COUNT（etf_score 115 万行 / etf_indicator 1613 万行），4 卡并行=32 条重查询互抢，单请求 12-13s | per-metric 单查 + 60s 进程内 TTL 缓存 + indicator_count 改 reltuples 估算 | `2040b86` `5fdbb6a` |
| 2 | `/fund-flow/sector` 必 500 | `_parse_sort` 从列名映射取「字典首列」，`main_net_inflow` 恒返回 IndividualFundFlow 的列 → missing FROM-clause | 按调用方 model 解析列，未知列兜底本表 trade_date；+6 回归测试 | `2040b86` |
| 3 | 原生 App 研报全文加载失败 | 后端 `sections_json` 不下发 `retries` 且 status 值为 `"success"`（不在 Swift 枚举内）→ 严格解码整篇失败 | retries 改可选 + 枚举补 success + 降级角标判定显式化；DMG 重打 | `b9d43d2` |
| 4 | `/stats/overview/etf-count` 500（热修当天引入） | 我误用 `ETFInfo.id`——主键是 `code`(String)，该端点此前零测试覆盖 | 改 `ETFInfo.code` + 7 条 overview 回归测试 | `3296d2e` |
| 5 | **全栈停摆 ~10 分钟** | 一天 6 次部署 = 16GB 旧镜像 + 49GB build cache 顶满 /data（100%）→ postgres PANIC `No space left on device` 崩溃循环，4 容器 Created 起不来 | 急救清 35GB（旧镜像 21G + build cache 14G）；update.sh 加部署后自动清理（保留 current+latest，best-effort） | `de17fe5` |

## 关键时间线（CST）

- 22:0x 用户报告：首页无法显示 + 研报无法加载全文（恰逢 11 commits 部署窗口，症状被放大）
- 22:3x 探测定位 #1 #2；23:0x 定位 #3（sections_json 契约漂移）
- 23:2x push `2040b86` 后引入 #4，30 分钟内热修 `3296d2e`
- 23:5x push `5fdbb6a` 部署中 **/data 顶满 100%** → postgres PANIC 崩溃循环，全栈 4 容器 Created
- 00:0x 清 35GB → postgres 重启恢复 → compose 拉起四服务 → 外网 200
- 00:1x reextract_cninfo_md 重 fire（任务在混乱中丢失）→ push `de17fe5`（update.sh 自动清理）

## 排障口诀（这次验证有效的路径）

1. **"首页无法显示"先打 API 不看页面**：`curl -w '%{http_code} %{time_total}s'` 逐端点过一遍，慢/500 立现
2. **Swift 端「加载失败」优先怀疑契约漂移**：后端 JSON 与 Codable 模型逐字段对（缺字段/枚举值超出都是整体解码失败，不是字段级降级）；契约以后端实际返回为准，不看 web ts 类型
3. **docker ps 只剩 infra 容器 = 应用层全灭**：`docker ps -a` 看 Created 态 + `docker logs postgres --tail` 找 PANIC；`No space left` → 先清镜像再 restart postgres（它会自己跑完 recovery）
4. **磁盘占用三兄弟**：`docker system df`（Images/Build Cache/Volumes）+ `df -h /data`；每天多次 push 时旧镜像是第一嫌犯（每个 2.67GB）

## 加固清单（本次落地）

- [x] stats overview：per-metric 单查 + 60s 缓存 + 巨表 reltuples 估算（冷启 19.9s → 1.4s）
- [x] `_parse_sort` model 感知 + 6 回归测试；stats overview 7 回归测试（原零覆盖）
- [x] 原生 DigestModels 契约对齐后端实际（retries 可选 / success 枚举）
- [x] update.sh 部署后自动清旧镜像 + 72h build cache（`de17fe5`）
- [x] 新 DMG 已重打（含 #3 修复）：`~/Desktop/AlloyResearch-0.4.0-macOS-arm64.dmg`

## 遗留

- [ ] `/stats/overview` 多 uvicorn worker 下进程内缓存命中率有限（二刷 2.4s），可改 Redis 共享缓存（低优）
- [ ] 用户需重装 DMG 验证研报全文；web 端 DigestSection status 类型与后端 `"success"` 不一致（仅角标语义，非致命，下轮对齐）
- [ ] 昨日 push 的 5 个 commit 触发 5 次部署，reextract_cninfo_md 每次被 redeliver 从头跑——长任务与高频部署的冲突需要调度层面解（如 reextract 支持断点 offset 持久化）
