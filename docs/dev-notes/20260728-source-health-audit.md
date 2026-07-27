# 资讯源健康审计报告（2026-07-28 凌晨）

> 审计范围：2026-07-21 以来新增源（重点 100 公众号源 + 独立英文源），ECS 只读。
> 审计时间：2026-07-27 23:35 ~ 2026-07-28 02:00 CST。
> 处置状态见文末「处置记录」（本文件 md/html 双份，html 自包含）。

## ① 总览

| 通道 | 源数 | 调度健康 | 产出健康 | 判定 |
|---|---|---|---|---|
| wewe-rss 自建（zhigu/yuanchuan/canghai/fupeng/lixunlei/congming/beiwei/latepost） | 8 | ✅ 15m job 每 15 分钟 success | ❌ 全部冻结约 22h | **异常（上游账号失效）** |
| wechat2rss 单 feed（maobidao/sixianggangyin） | 2 | ⚠️ 连续 17 次 failed 后代码已修，修复后尚未跑成一轮 | 各 20 篇，冻结约 7h | 异常（待自愈验证） |
| wechat2rss 批量 9 组（a..i） | 90 | ✅ 至 12:56 UTC 全部 success；最近 2 个小时级 tick 疑似被 misfire 丢弃 | 15 源当日有新文；若干源为死镜像 | 半异常 |
| 独立英文源（13 个 job） | 13 | 30m 6 源修复后已 success；60m 6 源 + quantpedia 同受 tick 饥饿影响 | 11/13 有文章；calculatedrisk 永远 0 文 | 2 个真异常 |
| 前端可见性 | — | — | ✅ 默认过滤下全部可见 | 正常 |

## ② 异常源清单与根因

| 源/job | 现象 | 根因 |
|---|---|---|
| **8 个 wewe-rss 源** | DB 最新 fetched_at 停在 2026-07-27 03:02 CST；15m job 空转 | wewe-rss 容器更新 cron 连续报 `暂无可用读书账号`（7-26 21:35 UTC 起）——**微信读书扫码会话被微信侧踢掉**，需人工重扫码 |
| **wechat_maobidao / wechat_sixianggangyin** | 连续 17 次 failed：`rss_simple has no attribute 'WechatMaobidaoCrawler'` | 当晚 backend 镜像是旧版 rss_simple.py；重建后类已存在，欠一轮 tick 自愈 |
| **16 个小时级 job 集体丢 tick** | 12:56 UTC 起 5h 无运行记录 | **APScheduler ThreadPoolExecutor(max_workers=5) + misfire 300s**：9-11 条僵尸 running（LLM 营销过滤/jina 无超时挂死）占满线程池，整点 wave（17+ 个 5m/10m job）挤占后小时级 job 被 coalesce 丢弃 |
| **calculatedrisk** | 上线以来 success 6 次但 0 文章 | 302 跳 FeedBurner 返回 **Atom**，解析器只取裸 `title` → 每条 skip |
| **quantpedia** | 8 次运行全 failed（同 attribute bug），0 篇 | 容器内实测解析正常，欠一轮 tick 自愈 |
| **wechat2rss 死镜像源** | tiaodongjisuanqi 最新 2020-05、aptguancha 2018-09、xiaohuojian 2020-11、sushiba 2023-02、djzhaji 2022-06 | 镜像侧停更，管道正常，注册时灌入旧文后无增量 |
| apricitas | 最新文 2026-05-03 | 作者停更，非我方故障 |

## ③ 健康确认（好消息）

- **100 个 wechat_* 源全部有文章，无"注册但 0 文"**；9 个批次 job 连续 18-21 次 success，合计写入 1180 条。
- 镜像通道当日仍在产出：jisilu 最新 7-27 21:56 CST、xisailuo 19:00 CST；15 源 fetched_at 为当日。
- wewe-rss 服务面正常（容器 Up，feed 返回 30 条缓存，只是内容冻结）。
- 30m 英文源修复已验证：wolfstreet/calculatedrisk/marginalrevolution 已 success；ritholtz 最新文 7-27 13:00 UTC 入库。
- 前端默认视图无过滤风险（market=cn_a / language=zh / event_category=NULL 直达）。

## ④ 处置记录（2026-07-28 凌晨主会话执行）

| 项 | 处置 | 状态 |
|---|---|---|
| 小时级 job tick 饥饿（P1） | `scheduler.py`：max_workers 5→10 + 全部 9 处小时级 trigger 加 `jitter=600`（10 分钟窗口错峰）。当晚新增 62 个小时级批次 job 使该修复成为必需 | ✅ 已修复并推送 |
| calculatedrisk Atom 解析（P2） | `rss_common.py` Atom 命名空间回退（title/summary/content/updated）已随 c2c5f8e 部署，下个 30m tick 自愈 | ✅ 已修复待自愈 |
| maobidao/sixianggangyin/quantpedia | 代码已修，等 tick 自愈 | ⏳ 观察 |
| wewe-rss 8 源（P1） | **需用户重扫微信读书二维码**；本次会话仅存活约 1 天，建议把容器日志 `暂无可用读书账号` 纳入告警 | ⏳ 待用户 |
| 死镜像源（P3） | tiaodongjisuanqi/aptguancha/xiaohuojian/djzhaji/sushiba 等从 `WECHAT2RSS_FEEDS` 移除或换活跃号 | ⏳ 下轮 |
| apricitas | 保留监控，停更超 2 个月可换源 | ⏳ 观察 |

## ⑤ 后续防御建议

1. LLM 营销过滤 / jina 全文抓取加硬超时（防线程池被慢调用长期占用）。
2. etl_log 僵尸 running 清理：backend 启动时把 start_time 早于启动时刻的 running 行标记 failed（本次重启已自然清理线程，但状态行残留）。
3. 公众号死源定期巡检：连续 30 天无增量且镜像 feed 最新文 >90 天 → 自动降频或剔除。
