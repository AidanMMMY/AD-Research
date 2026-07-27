# cninfo 资讯出现"未来时间"（7-28 0点）根因与修复

日期：2026-07-27
状态：代码已修（未 commit）；存量数据修复 SQL 待审批执行；需重新部署 backend

## 现象

资讯版块 cninfo 来源的上市公司报告显示"7月28日 0点"，而当天才 7 月 27 日——未来时间。

## 根因

**不是时区转换 bug，也不是 epoch 秒/毫秒单位错误。**

巨潮 `announcementTime` 字段是**日期粒度**的：晚间挂网的公告会被盖成**下一披露日北京时间 0 点**的 epoch 毫秒。

实测（2026-07-27 22:34 北京）POST `hisAnnouncement/query` 返回：

```
announcementTime = 1785168000000 = 2026-07-27T16:00:00Z = 2026-07-28 00:00:00 +08:00
```

爬虫 `app/services/news/sources/cninfo.py` 的 `_ms_to_dt()` 转换完全正确（16:00Z 正是北京午夜），前端 UTC→Asia/Shanghai 显示也正确——问题是**源数据本身就是一个"未来时刻"**，原样入库后资讯流出现未来日期。

## 修复

`app/services/news/sources/cninfo.py` `_parse_payload()`（约 163-172 行）：
未来时间戳钳制（clamp）到抓取时刻 `now`：

```python
parsed_at = _ms_to_dt(ann_time_ms)
now = datetime.now(tz=timezone.utc)
published_at = min(parsed_at, now) if parsed_at is not None else now
```

测试：`app/tests/news/test_news.py::test_cninfo_clamps_future_announcement_date`
（未来 ms → 钳到 now 窗口内；历史 ms → 原样保留）。`app/tests/news/` 全套 359 passed。

## 存量数据（ECS 实测）

- `news_article` cninfo 共 192 行；其中 167 行是北京午夜戳（`16:00:00Z`）
- **14 行当前在未来**（全部 = 2026-07-27 16:00:00Z）
- **57 行 `published_at > fetched_at`**（物理上不可能：抓取时公告尚未"发布"）

修复 SQL（**未执行**，待总管/用户审批）：

```sql
-- 推荐：把所有"晚于抓取时间"的 cninfo 行钳到抓取时刻（57 行）
UPDATE news_article
SET published_at = fetched_at
WHERE source = 'cninfo' AND published_at > fetched_at;

-- 若只想最小修当前未来的 14 行：
UPDATE news_article
SET published_at = fetched_at
WHERE source = 'cninfo' AND published_at > now();
```

## 部署

改动在 crawler 代码路径（`run_cninfo_crawl` 每 10 分钟跑），需重新部署 backend 后生效；不部署则每晚 16:00Z 后仍会产生新的未来时间行。
