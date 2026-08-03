# cninfo PDF → Markdown 提取管线升级 runbook（B2）

> 2026-08-03 上线。背景：cninfo 定期报告 PDF 共 11,663 个 / 14.0GB（/data 88% 已用的 14%）。
> 旧提取链（pdfplumber 级联）文本层覆盖 99.9%，但表格列结构全丢、图表全丢、12.7% 撞 200k 字符截断，
> 「准确完整 md」信心低。用户拍板方案 A：**先升级管线 → 全量重提 → 验收 → 再删 PDF**（净省 ~13.5GB）。

## 1. 引擎选型（B1 benchmark 实证）

在 ECS 真实语料上对比 pdfplumber（现状）vs pymupdf4llm：

| 指标 | pdfplumber 级联（旧） | pymupdf4llm（新） |
|---|---|---|
| 无边框财务报表 → md 表格 | 列结构全丢 | **完美还原**（实证） |
| 速度 | — | 0.344s/页 |
| 图表 | 全丢 | 全丢（PDF 图表是矢量图，无文本层方案可解） |
| 截断 | 200k 字符保险丝 | **无截断**（2M 上限，仅防失控） |

全量规模：1,010,721 页 → `-c 2` 约 47h，`-c 4` 约 24h。
代价：+271MB 依赖（onnxruntime ML 版面分析），单进程峰值 ~1.1GB RAM。
3/11,660 PDF 打不开（损坏），fallback 到旧链提取。
已知噪音：`<mark>/<u>/<br>` HTML 标签（已在 service 层剥除）；跨页表格会被切成两段 md 表（可接受）。

**许可证**：PyMuPDF 系 AGPL-3.0。本仓库在 GitHub 公开，满足 §13 源码提供义务（pyproject 已注记）。

## 2. 变更清单

- `pyproject.toml` / `poetry.lock`：`pymupdf4llm = "^1.28"`
- 迁移 `c4d6e8f0a2b4`（down=`b7d9f1h3j5l7`）：`cninfo_reports` +`extracted_format` String(16)（text/md，NULL=旧数据）、+`md_path` String(1024)（相对 MD_DIR）
- `app/services/cninfo_report_service.py`：
  - `_DEFAULT_MD_DIR` = env `CNINFO_MD_DIR`，默认 `/data/alloy-research/cninfo_md`
  - `extract_markdown()`：pymupdf4llm 主链 + 旧链 fallback + HTML 噪音剥除
  - `extract_text_for_report(report_id, fmt="md")`：写 `{MD_DIR}/{stock_code}/{announcement_id}.md`，DB `extracted_text` 仍是主存储（`_MAX_MD_LEN=2_000_000` 保险丝）
- `app/tasks/cninfo_pdf.py`：+`reextract_cninfo_md(offset, limit, batch_sleep=0)` 分片任务
  - 选取 `file_path NOT NULL AND (extracted_format IS NULL OR ='text')`，按 id 排序
  - 文件已不在盘上 → skipped；单行异常不杀分片
- `deploy/aliyun-ecs/docker-compose.yml`：`CNINFO_MD_DIR` env + `cninfo_md` volume（仅 celery-worker-cninfo）
- `scripts/delete_extracted_cninfo_pdfs.py`：删除脚本（默认 dry-run，`--execute` 才真删；置 NULL file_path/file_size，保留 adjunct_url；500 行一批 commit）
- `app/tests/test_cninfo_markdown.py`：10 测试

## 3. 执行手册（B3 全量重提）

```bash
ssh ad-research
# 先跑 1 个 5000 行分片验证计数器与落盘：
docker exec -d alloyresearch-celery-worker-cninfo bash -c \
  'celery -A app.core.celery_app call app.tasks.cninfo_pdf.reextract_cninfo_md \
   --args="[0, 5000]" > /tmp/reextract_shard0.log 2>&1'
# 观察 /tmp/reextract_shard0.log 与 etl_log，确认 extracted/skipped/failed 合理后，
# 全量（11,643 行有 file_path）：offset 5000 起剩余分片，或直接一个 20000 limit：
docker exec -d alloyresearch-celery-worker-cninfo bash -c \
  'celery -A app.core.celery_app call app.tasks.cninfo_pdf.reextract_cninfo_md \
   --args="[5000, 20000]" > /tmp/reextract_rest.log 2>&1'
```

- 预计 24-47h（`-c 2` 与下载任务共享 worker；想加速可临时把 celery-worker-cninfo 调 `-c 4`，内存上限要同步放宽）
- 进度：`docker exec alloyresearch-celery-worker-cninfo tail -f /tmp/reextract_rest.log`（每 50 行打 ETA）
- 抽查：`docker exec alloyresearch-celery-worker-cninfo head -50 /data/alloy-research/cninfo_md/600519/<announcement_id>.md`

## 4. 删除 PDF（B4，重提验收后）

```bash
# 验收：md 覆盖率
docker exec alloyresearch-postgres psql -U etf -d ad_research -c \
  "SELECT extracted_format, count(*) FROM cninfo_reports WHERE file_path IS NOT NULL GROUP BY 1;"
# dry-run 先看会删哪些：
docker exec alloyresearch-celery-worker-cninfo python scripts/delete_extracted_cninfo_pdfs.py
# 真删：
docker exec -d alloyresearch-celery-worker-cninfo bash -c \
  'python scripts/delete_extracted_cninfo_pdfs.py --execute > /tmp/delete_pdfs.log 2>&1'
```

**警告（两条铁律）**：
1. 删除后 `file_path=NULL` 的行会命中下载任务 `only_pending` 查询——**绝不能再跑旧 start_date 的
   download_cninfo_pdfs 分片**，否则会把 14GB 全部重新下载回来。如需补新报告，只用近日期窗口。
2. 删除脚本必须在 **celery-worker-cninfo 容器**内跑（唯一挂 cninfo_pdfs volume 的容器）。

## 5. 验收记录

- 本地：pytest 1643 passed（含 test_cninfo_markdown 10 条）
- B3/B4 结果：待补（重提完成后回填本节）
