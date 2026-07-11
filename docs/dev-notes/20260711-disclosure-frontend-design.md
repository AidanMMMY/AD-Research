# A 股披露公告全量获取方案

> 状态：设计阶段 | 2026-07-11

## 0. 现状摸底

### 当前能力

| 组件 | 现状 | 问题 |
|---|---|---|
| `cninfo_org_ids.json` | **40 条**（仅大市值测试用） | 脚本 `build_cninfo_org_id_map.py` 已写好，但从未在服务器执行 |
| `CninfoProvider` | 正常工作，2s pacing，~30 req/min | 单一 IP，无法并行加速 |
| `CninfoReportService` | 支持任意 universe 参数 | 目前被 hardcode 的 `get_hs300_cs500_universe()` 限制 |
| `CninfoReportsPipeline` | 每天 17:00 拉取 7 天窗口的定期报告 | 仅拉到 40 只有 org_id 的股票 |
| PDF 下载 + 文本提取 | pdfplumber/pypdf/pdfminer 三引擎 | 正常 |
| API 层 | list/coverage/detail/download/refresh | 正常 |
| 前端 | `/cninfo-reports` 页面 | 未挂在侧边栏 |

### 结论：已有基础设施完全可用，瓶颈在 org_id 覆盖 + 调度策略

---

## 1. 数据源分析

### Source 1: 巨潮资讯网 API（cninfo）⭐⭐⭐⭐⭐

- **端点**: `POST http://www.cninfo.com.cn/new/hisAnnouncement/query`
- **覆盖**: 全量 A 股 5407 只（需 org_id）
- **内容**: 定期报告（年报/半年报/Q1/Q3）+ 临时公告
- **格式**: JSON → PDF 下载链接
- **限速**: ~30 req/min，超限返回 503
- **优势**: 官方指定披露平台，覆盖面最全，已有完整 pipeline
- **劣势**: 单一 IP 受速率限制，全量拉取需数小时

### Source 2: 交易所公告页（SSE / SZSE）⭐⭐⭐

- **SSE**: `https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?COMPANY_CODE={code}`
- **SZSE**: `https://www.szse.cn/certificate/individual/index.html?code={code}`
- **内容**: HTML 页面 → 需解析提取公告列表 + PDF 链接
- **优势**: 官方一手来源，可交叉验证
- **劣势**: HTML 结构可能变化，需维护解析逻辑；无结构化 API

### Source 3: 公司官网 IR 页面 ⭐

- **覆盖**: ~600 家有独立 IR 网站（约 11%）
- **内容**: 各异，有些只放 PPT
- **优势**: 可能有额外材料（投资者演示、电话会纪要）
- **劣势**: 高度异构，自动化 ROI 极低；仅适合精选公司手动标注

### 策略：以 cninfo 为主力（全量定期报告 + 全量临时公告），交易所为补漏（cninfo 失败时的备用），IR 网站暂不自动化

---

## 2. 全量获取架构

### 2.1 Phase 0: 重建 org_id 映射表（前置条件）

```bash
# 在服务器上执行（一次性）
cd /opt/ad-research
python3 scripts/build_cninfo_org_id_map.py \
  --output app/data/static/cninfo_org_ids.json \
  --backup app/data/static/cninfo_org_ids.json.bak
```

脚本从 `http://www.cninfo.com.cn/new/data/szse_stock.json` 拉取全量 A 股 org_id（5407 条），按 `{ts_code: org_id}` 格式写入 JSON。

### 2.2 Phase 1: 全量定期报告首次回填（一次性大批量）

**目标**: 对全部 5407 只 A 股，拉取最近 5 年的定期报告（2022-2026）

**规模估算**:
- 5407 只 × 4 种类型（年报/半年/Q1/Q3）× 5 年 ≈ 108,140 条公告
- 每条公告 1 次 API 调用 ≈ 108,140 次请求
- 30 req/min → 60 小时串行

**并行策略（核心）**:

不是单进程跑 60 小时，而是拆分成多个独立 worker：

```
                    ┌─ 调度器 ─┐
                    │  (offset) │
                    └────┬──────┘
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    Worker 1       Worker 2       Worker N
    (0-500)        (501-1000)     (N*500-...)
           │             │             │
           ▼             ▼             ▼
    CninfoProvider CninfoProvider CninfoProvider
    (独立 DB sess)  (独立 DB sess)  (独立 DB sess)
```

**关键设计**:
- 每个 worker 处理 500 只股票的独立 batch
- Worker 之间通过 PostgreSQL 行锁自动去重（`ON CONFLICT (announcement_id)`）
- 每个 worker 自己的 `_MIN_INTERVAL=2s` → 30 req/min
- 10 个并发 worker → 总体 ~300 req/min（可能触发 cninfo 全局限速，需实测调优）
- 安全起点：3-5 个并发 worker，逐步加量
- 通过命令行 `--offset` `--limit` 参数控制每个 worker 的股票范围

**新增脚本** `scripts/backfill_cninfo_reports.py`:

```python
"""
Usage:
  # Worker 1: stocks 0-499
  python scripts/backfill_cninfo_reports.py --offset 0 --limit 500

  # Worker 2: stocks 500-999
  python scripts/backfill_cninfo_reports.py --offset 500 --limit 500
"""
```

每个 worker:
1. 从 `cninfo_org_ids.json` 读取全量代码，slice `[offset:offset+limit]`
2. 对每个代码调用 `CninfoReportService.fetch_for_stock()`，日期范围 2022-01-01 ~ today
3. 自动 upsert 到 `cninfo_reports`（幂等）
4. 完成后打印统计：成功/跳过/失败 数

**调度方式**:
```bash
# 同时在服务器上启动 5 个 worker
for i in 0 500 1000 1500 2000; do
  nohup python3 scripts/backfill_cninfo_reports.py --offset $i --limit 500 &
done
```

### 2.3 Phase 1b: PDF 下载 + 文本提取（异步队列）

报告元数据入库后，PDF 下载和文本提取是独立步骤：

**当前机制**: 按需下载（用户点击详情时触发 `download_pdf`）
**改为**: 后台批量队列

```
cninfo_reports (extraction_status = 'pending')
       │
       ▼
  PDF Download Worker (批量下载 PDF)
       │  └─ extraction_status → 'downloaded'
       ▼
  Text Extraction Worker (批量提取文本)
       │  └─ extraction_status → 'extracted'
       ▼
  cninfo_reports (extraction_status = 'extracted')
       │
       ▼
  AI 分析可用
```

新增脚本 `scripts/batch_download_extract.py`:

```python
"""
1. SELECT * FROM cninfo_reports WHERE extraction_status = 'pending'
2. 按 ts_code 顺序处理（优先大市值）
3. download_pdf → extract_text_for_report
4. 单进程，不限速（PDF 下载走 static.cninfo.com.cn，不限速）
"""
```

**存储预估**:
- PDF: ~1MB/份 × 108K 份 ≈ 108GB（实际更少，很多 Q1/Q3 报告很短）
- 文本: ~200KB/份（截断 200K chars）× 108K ≈ 21GB
- 建议先回填最近 5 年定期报告，再逐步扩展更早期

### 2.4 Phase 2: 临时公告补充

cninfo API 也返回临时公告（非定期报告），当前 `fetch_periodic_reports` 只拉 4 种定期报告类型。

**扩展**: `CninfoProvider` 新增 `fetch_all_announcements()` 不加 `category` 过滤，拉取全部公告类型：

```python
def fetch_all_announcements(self, org_id, start_date, end_date):
    """Fetch ALL announcements (not just periodic reports)."""
    # POST 时不带 category 参数，或遍历 cninfo 的全部 category
    # 包括：category_ndbg_szsh (年报), category_bndbg_szsh (半年),
    #       category_yjdbg_szsh (Q1), category_sjdbg_szsh (Q3),
    #       以及临时公告类别
```

cninfo 的 category 列表需要实测确认，但基本思路是遍历所有已知 category 或空 category 获取全部。

**优先级**: 定期报告回填完成后启动，仅拉最近 1 年临时公告（量太大，全量无必要）

### 2.5 Phase 3: 交易所公告页补漏（可选，P2）

当 cninfo 对某只股票返回空结果时，尝试 SSE/SZSE 公告页：

```
cninfo 返回 0 条 → 标记 verification_status='cninfo_empty'
                       │
                       ▼
               ExchangeScraper.fetch_for_code(code)
                       │
                       ▼
               解析 HTML → 提取 PDF 链接 → 下载 → upsert
```

Exchange scraper 使用 `requests` + `BeautifulSoup`，单独模块 `app/data/providers/exchange_disclosure_provider.py`。

**不追求全覆盖**，仅用于补漏 cninfo 失败的情况。

---

## 3. 数据模型（无需改动）

现有 `CninfoReport` 表已足够通用：

| 字段 | 用途 |
|---|---|
| `announcement_id` | 巨潮公告 ID（唯一键，幂等 upsert） |
| `adjunct_type` | annual/semi/q1/q3/other（临时公告用 other） |
| `is_periodic` | 区分定期报告 vs 临时公告 |
| `extraction_status` | pending/downloaded/extracted/failed |
| `extracted_text` | 截断 200K chars 的全文 |
| `source` | cninfo（后续可扩展 sse/szse） |

**不需要新建表**。`DisclosureRoute` 表仍保留作为元数据索引（渠道链接）。

---

## 4. 定时增量更新

### 现有调度
- 每天 17:00（A 股收盘后）执行 `CninfoReportsPipeline`
- 拉取最近 7 天新发布的定期报告

### 修改点
- Universe 从 `get_hs300_cs500_universe()` 改为直接读取 `cninfo_org_ids.json` 的全部 5407 只
- 日增量只需拉 7 天窗口，每只股票可能只有 0-2 条新公告
- 5407 × 平均 0.5 条 × 2s pacing ≈ 1.5 小时
- 可接受，不需要并行

---

## 5. 前端展示（方案不变，参见原设计文档）

- `/disclosures` 统一入口（CninfoReports + SECFilings + 披露渠道库 三 Tab）
- 股票详情页新增"披露公告"区块
- DisclosureRoute API 补齐

---

## 6. 实施路线图

| Phase | 内容 | 预计时间 | 方式 |
|---|---|---|---|
| **Phase 0** | 服务器执行 `build_cninfo_org_id_map.py`，org_id 40→5407 | 5 分钟 | 单命令 |
| **Phase 1a** | 全量定期报告回填（5 年 × 5407 只） | 8-12 小时（5 worker 并行） | 多 worker 脚本 |
| **Phase 1b** | PDF 批量下载 + 文本提取 | 24-48 小时（取决于 PDF 下载带宽） | 单进程队列 |
| **Phase 2** | 临时公告 API 拉取（最近 1 年） | 8-12 小时 | 多 worker |
| **Phase 3** | 日增量 pipeline 扩展到全量 | 1 小时 | 修改 scheduler |
| **Phase 4** | 交易所补漏 scraper（可选） | 2-3 天 | 单独开发 |
| **Phase 5** | 前端 `/disclosures` 整合 | 1-2 天 | 前端开发 |

## 7. 新增文件清单

| 文件 | 用途 |
|---|---|
| `scripts/backfill_cninfo_reports.py` | 全量回填脚本（按 offset/limit 分片） |
| `scripts/batch_download_extract.py` | 批量 PDF 下载 + 文本提取 |
| `app/data/providers/exchange_disclosure_provider.py` | SSE/SZSE 公告页 scraper（Phase 4） |
| `app/api/v1/disclosure_routes.py` | DisclosureRoute API |

## 8. 成本与风险

- **磁盘**: PDF 存储估算 50-100GB（首轮），需监控 `/data` 使用率（当前 93%）
- **网络**: cninfo API 无认证、无费用，仅需遵守速率限制
- **法律**: cninfo 是公开披露平台，数据为法定公开信息，无版权风险
- **cninfo 反爬**: 当前 30 req/min 策略已验证稳定 6 个月+，多 worker 需逐步加量测试
