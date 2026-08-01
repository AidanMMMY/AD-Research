# 2026-08-01 预置标的池删除守卫修复 runbook

## 背景

用户（Aidan，role=user）在标的池页删除「行业轮动池」(id=4) 被 403：
"系统预置标的池（id=4）不可删除，请新建一个自定义池代替"。

## 现状结论

- **守卫位置**：`app/services/pool_service.py` `delete_pool` /
  `_assert_write_access` —— `pool.user_id IS NULL` 且非 admin →
  `PermissionError("system_pool")`；`app/api/v1/pools.py` 映射为 403 中文文案。
- **预置池模型**：没有 `is_preset` 字段。`user_id IS NULL` 即"系统预置/全局共享池"，
  由 `scripts/seed_all_demo_data.py` 一次性种入（宽基指数池/科技成长池/稳健防御池/行业轮动池），
  **不是**每用户一份。生产库实测 8 个用户（admin + 7 个普通用户），池 1-5 全部 NULL-owner 共享。
- **守卫意图（M21-3 防 IDOR）**：普通用户不能改/删别人和全局共享的数据——合理，保留。

## 依赖方审计（删除影响面）

| 引用方 | 位置 | 依赖类型 | 处理 |
|---|---|---|---|
| 周报 job `run_weekly_pool_reports` | `app/core/scheduler.py` | **硬依赖（有 bug）**：原查询未过滤 `deleted_at`，软删池每周日仍生成孤儿周报 | 已修：查询加 `deleted_at.is_(None)` |
| `ReportService.generate_pool_report` | `app/services/report_service.py` | 软依赖：池不存在抛 ValueError，job 内 per-pool try/except 吞掉 | 无需改 |
| `report_metadata.pool_id` FK CASCADE | `app/models/scoring.py` | 仅硬删除触发；软删除保留历史报告 | 无需改（历史报告有意保留） |
| 板块轮动 / 评分模板 / 筛选 | — | 均不引用 pool id，无 is_preset 查询 | 无依赖 |

## 修复方案

全局共享池 → **仅管理员可删**（平台 8 个真实用户，普通用户删共享池会破坏他人数据）。
管理员删除路径原本就通，本次补的是删除的正确性与 UX：

1. `pool_service.delete_pool`：删除时级联软删 `PoolMember.removed_at` +
   `PoolWeight.removed_at`（历史报告保留）。
2. 周报 job 过滤 `deleted_at`，已删池不再产生孤儿周报。
3. 403 文案改准：全局共享池仅管理员可删（不再说"请新建自定义池代替"这种误导话）。
4. 前端 `PoolList`：`Pool.user_id == null` 判定预置共享池——
   普通用户看到禁用的删除按钮 + tooltip 说明；管理员看到二次确认
   "删除后对所有用户不可见且不可恢复"。

**用户操作**：用 admin 账号登录即可删除 4 个预置池；删除是软删除（`deleted_at`），
误删可 SQL 恢复（`UPDATE etf_pools SET deleted_at=NULL WHERE id=4`，
成员/权重同理清 `removed_at`）。

## 改动文件

- `app/services/pool_service.py` — 级联软删 + 权限矩阵 docstring
- `app/api/v1/pools.py` — 删除 403 文案
- `app/core/scheduler.py` — 周报 job 过滤已删池
- `app/tests/services/test_pool_service.py` — 级联/权限矩阵 4 个新用例
- `app/tests/test_pool.py` — 周报 job 跳过已删池 + 单池失败不炸
- `web/src/types/pool.ts` — `Pool.user_id?: number | null`
- `web/src/pages/PoolList/index.tsx` — 预置池删除 UX 区分

## 测试

- 后端 `pytest app/tests`：1316 passed；7 个 `test_futures_pipeline.py` 失败为
  **既有失败**（stash 验证干净树上同样 7 连败，与本次无关）。
- 前端 `npm run check:ci`（lint:css + tsc + vite build）全绿。
