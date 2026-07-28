# 晨报：2026-07-28 过夜任务全量汇报

> 时段：2026-07-27 16:30 ~ 2026-07-28 04:00（UTC+8 约 00:30 ~ 12:00）
> 主任务：/goal「不限语言搜罗全球高质量信息源，增加不少于 300 个资讯源，已完成能 push 的先 push」

---

## 一、头条：300 源目标 → 实际入库 652 源，全部部署上线

| 批次 | 源数 | 构成 | Commit |
|---|---|---|---|
| indie 独立源二批 | 144 | 英文博客 42 / 播客 37 / 中文博客 65 | `689acbc` |
| global_rss 多语批 | 125 | 央行研究 / 智库 / 法西韩日德媒体 / 工程博客 | `c2c5f8e` |
| 微信公众号二批 | 103 | 宏观 26 / 策略 22 / 行业 14 / 科技 29 / 商业 12 | `d4baa24` |
| gind 英文独立三批 | 104 | 自建站 Substack / Ghost / dev.to / 非营利新闻室 | `0a30fdd` |
| asen 亚洲英文批 | 176 | 亚洲英文财经 45 / 国际栏目 20 / 行业垂直 63 / 投资博客 36 | `0a30fdd` |
| **合计** | **652** | — | — |

**质量门**：所有源均经 ECS 实网逐个 curl 验证（HTTP 200 + 有效 RSS/Atom + 有实质正文 + 30 天内有更新）。累计实测候选 ~1,800 个 URL，淘汰 ~1,100 个（403 反爬 / 404 / 停更 / 正文过薄 / GFW 不可达），淘汰明细全部记录在各批次 runbook。

**首轮抓取已验证**（今晨 03:15-03:47）：四个新家族 etl_log 30 success / 0 failed，30 分钟落库 **1,981 篇**（asen 1,088 + global_rss 513 + gind 380）。16:00Z 以来全站新增 6,903 篇。

## 二、顺带修复的 4 个真 bug

1. **`market="global"` 前端隐形（P1）**：global_rss 批次 84 个源写了白名单外的 market 值，文章在前端默认视图完全不可见。已改码（→`us`），确认存量 0 行无需 SQL。由 gind agent 在自测时发现并跨批次告警。
2. **APScheduler 线程池饥饿（P1，健康审计发现）**：`max_workers=5` + 整点 wave 叠加 LLM 营销过滤/jina 无超时挂死 → 16 个小时级 job 连续 5h 丢 tick。修复：`57e644a` max_workers 5→10 + 全部 9 处小时级 trigger 加 `jitter=600` 错峰。若不修，今晚新增 62 个小时级 job 会把饥饿放大数倍。
3. **Atom/RSS 1.0 解析器缺陷（P2）**：日本媒体与工程博客的 Atom/RDF feed 取不到 title/link/正文。`c2c5f8e` 修复，同时治好了健康审计发现的 calculatedrisk「永远 0 文」。
4. **翻译 prompt 只懂英文**：扩为多语言（日/德/法/韩/西），MiniMax 三语真实 smoke 通过。

## 三、推送清单（6 笔，全部 CI 绿 + Deploy 绿）

`689acbc` indie 144 → `c2c5f8e` 多语 125+解析器 → `d4baa24` 微信二批 103 → `0a30fdd` gind/asen 280+market 修复 → `57e644a` 调度器饥饿修复。ECS 当前 `git_sha=57e644a`，/health ok。DeepSeek standby key 已随部署在 ECS 生效（MiniMax 仍为主链路，实测健康，无需切换）。

## 四、文档（全部 md+html 双份）

- `20260728-independent-sources-batch`（144 源证据表）
- `20260728-global-rss-batch`（125 源证据表）
- `20260728-wechat-batch2`（103 源 + 通道调研 + 运维手册）
- `20260728-global-indie-batch`（104 源 + 363 行淘汰明细）
- `20260728-asia-en-batch`（176 源 + 479 行淘汰明细）
- `20260728-source-health-audit`（健康审计全量报告 + 处置记录）

## 五、仍在跑的 3 个修复 agent（昨天你截图提的三个资讯问题）

- 英文资讯翻译 drain 验证（agent 6）
- MarketWatch 正文提取错误（agent 7）
- Investing 空正文（agent 8）

均为长任务，完成后我会验证 + commit + push，结果在下次汇报。

## 六、需要你知道 / 操作的事

| # | 事项 | 级别 | 需要谁 |
|---|---|---|---|
| 1 | **wewe-rss 8 个公众号冻结 ~24h**：微信读书扫码会话被微信踢掉（上次扫码只存活约 1 天），需重扫码恢复。建议后续把容器日志 `暂无可用读书账号` 接入告警 | P1 | **你扫码** |
| 2 | **翻译积压 4,189 篇**（48h 内非中文文章 title_zh 为空）：652 新源落地后翻译队列大增，news_translate_10m 会自动 drain，但需观察 24-48h；若积压不降，考虑调大 `news_translation_batch_size`。MiniMax 用量会明显上升 | P2 | 我观察 |
| 3 | **7 个指定公众号**（杨国英观察/叫小宋别叫总/投资界/墨子连山/半导体行业圈/金融时报/泽平宏观）：公共镜像均查无，需你提供每个号任意一篇文章链接，我用 wewe-rss tRPC 接入（泽平宏观另需重新 onboarding，现源 0 产出） | P2 | **你发链接** |
| 4 | **/data 磁盘 82%**（92G/118G）：清理方案已备好（builder prune ~12G + 备份轮换 + 悬空镜像，保护 alloyresearch-agent:latest），等你点头执行 | P2 | 你拍板 |
| 5 | **bestblogs 镜像依赖**：微信二批 100 源挂在 BestBlogs 公益自建 wechat2rss 实例上，可用性不受控；失效时按 runbook §5 切换 | P3 | 知悉 |
| 6 | **死镜像源替换**：一批 90 个公众号里约 5-8 个镜像侧停更（tiaodongjisuanqi/aptguancha/xiaohuojian 等），下轮换活跃号 | P3 | 我处理 |
| 7 | DeepSeek provider「假回复」之谜已解：不是 bug——provider 读 `os.environ` 而非 pydantic settings，本地裸跑 `poetry run` 不加载 .env 所致；真实 env 下 deepseek-v4-flash 实测正常 | 已闭环 | 知悉 |

## 七、过程备注

- 子 agent API 中断 4 次（集中在抓取海外站点的长任务），通过换措辞重派 + SendMessage 断点续跑全部救回，未丢进度。
- 跨 agent URL 冲突 2 起（9 个重叠 URL），由我仲裁对称去重，双方测试均含零重叠守卫。
- 多语言源分支（区域财经/央行机构取向）三次触发 API 错误后放弃，其覆盖已由 asen 176 源实质承接。
