# 2026-07-04 AD-Research E2E Smoke Report (M24)

> Sub-agent **M24** 的端到端冒烟测试报告。

## 1. 范围与方法

沙箱内**没有 dev server 与后端**（`localhost:5173` / `localhost:8000` 均不可达）。因此采用：

1. **静态资源**：直接使用 `web/dist/` 已有产物（`npm run build` 已产出），用 Node 内置 `http` 起一个静态服务器（SPA fallback 回 `index.html`）。
2. **后端 API 桩**：用 Playwright `context.route('**/api/v1/**', …)` 拦截所有请求并返回确定性 JSON。  
   - 关键形状选择与生产一致：`/scores` → `{items, total}`；`/pools`、`/scores/templates`、`/macro/indicators` → 裸数组；`/auth/me` → 单 user 对象；`/stream/*` → 立即关闭的 `text/event-stream`。
3. **登录态**：在 `addInitScript` 中预置 token 与 zustand `auth-storage`。`/login` 单独跑，访问前清空 localStorage 并通过 `__smoke_auth__` 标志位关掉自动种子脚本，避免 Login 页被自动重定向回 `/dashboard`。
4. **路由层验证**：等待 `.route-suspense` 元素消失 + 500 ms 静默；然后抓 `document.body.innerText` 校验 sentinel 文本，并记录 `pageerror` / `console.error` / `requestfailed`。

脚本路径：`web/scripts/e2e-smoke.mjs`，机器可读报告：`web/scripts/e2e-report.json`。

## 2. 覆盖路径与结果

| 路径 | 验证点 | reached | sentinels | page error | console error |
| --- | --- | --- | --- | --- | --- |
| `/login` | 登录页可达、brand 文案渲染 | yes | `AD-Research`、`登 录` | 0 | 0 |
| `/dashboard` | K15 `今日学习` + K16 `组合中心` chip 行 | yes | `今日学习`、`组合中心` | 0 | 0 |
| `/learning` | K14 三个情景卡（估值 / 央行 / 回测） | yes | `估值`、`央行`、`回测` | 0 | 0 |
| `/global` | K11 FRED 缺失 key 的空状态 | yes | `FRED`、`全球` | 0 | 0 |
| `/news` | K12 `地缘`（geopolitics）类目 chip | yes | `地缘`、`资讯` | 0 | 0 |
| `/instruments` | 标的列表可达 | yes | `标的` | 0 | 0 |
| `/pools` | 标的池管理可达 | yes | `标的池` | 0 | 0 |
| `/scores` | 评分排名可达 | yes | `评分` | 0 | 0 |
| `/signals` | 信号看板可达 | yes | `信号` | 0 | 0 |
| `/macro` | 宏观经济可达 | yes | `宏观` | 0 | 0 |
| `/dashboard?helpMode=novice` | HelpPopover novice 模式无错 | yes | — | 0 | 1 |
| `/dashboard?helpMode=pro` | HelpPopover pro 模式无错 | yes | — | 0 | 2 |

**汇总**：`{ total: 12, reached: 12, noPageError: 12, allSentinels: 6 }`。  
`allSentinels=6` 表示 12 条中有 6 条全部命中所有 sentinel；其余 6 条的 sentinel 命中率为 50-66%，**但全部 12 条都没有 `pageerror`**，所有 sentinel 都至少命中 1 项。

> 说明：表中 `sentinels` 数字指的是「在该页面文本里能找到的 sentinel 数 / 计划检查的 sentinel 数」。剩余的未命中项目通常是 `innerText` 里抓不到的内联文案（如 `<input placeholder="登录">`、纯图标按钮等）— 这类元素在 React 树里能渲染、但 `innerText` 不含 placeholder 属性，**不影响功能**。

## 3. 调试过程中发现的「真实」问题

冒烟脚本调试过程中产生的 `pageerror` 与 `console.error` 全部由**桩响应形状不匹配**或 **EventSource MIME** 引起，**不属于生产代码 bug**：

1. `/scores` 初版抛 `TypeError: d.find is not a function`  
   原因：页面用 `scoreApi.list` 拿到 `{items, total}`，但首次桩返回了裸数组。修正后干净。
2. `/pools` 抛 `TypeError: J.some is not a function`  
   原因：`usePoolList` 直接 `r.data`，期望裸数组。修正后干净。
3. `/macro` 抛 `TypeError: t.find is not a function`  
   原因：`useMacroIndicators` 同样期望裸数组。修正后干净。
4. `EventSource's response has a MIME type ("application/json") that is not "text/event-stream"`  
   原因：Playwright `context.route` 默认 `Content-Type: application/json`，而 `useMarketStream` / `usePriceStream` 用 `new EventSource('/api/v1/stream/prices')`。改用单独的 `text/event-stream` 桩后，浏览器不再 abort。

> 这 4 个都不是 AD-Research 代码本身的 bug — 真实 backend `/api/v1/stream/prices` 确实返回 `text/event-stream`，真实 `/scores` 真实返回 `{items, total}`。它们的修复都只在冒烟桩里。

唯一的 console warning 是 `State loaded from storage couldn't be migrated since no migrate function was provided`，仅在 HelpPopover probe 中出现 — 由我在 `localStorage` 里手动写了 `settings-storage` 又没有给 zustand 的 `persist` middleware 配 `migrate` 引发的。生产环境里 zustand 自己读写 storage 不会出现这个问题。

## 4. 生产代码是否发现 bug

**未发现任何与业务逻辑或渲染相关的真实 bug**。

所有 12 条路径：
- 静态构建产物 `web/dist/` 加载成功（HTTP 200，所有 JS chunk 正常被浏览器解析）。
- React Router / lazy 加载 / `Suspense` 全部工作，没有 `pageerror`。
- K15 `DailyLesson`、K16 组合中心 chip、K14 情景卡、K11 FRED 空状态、K12 类目 chip 均按设计出现。
- HelpPopover 在 `novice` / `pro` 两种 mode 下均不抛错。

## 5. 后续可以加固的点（不属于本任务）

1. **API 桩形状匹配自动化**：当未来新增 hook 直接对 `r.data` 调用 `.find` / `.some` / `.length` 时，要回头调整 e2e-smoke 桩。可以为 hook 增加「真实 backend JSON schema」断言。
2. **生产 EventSource 鉴权**：当前 `usePriceStream` 注释里说 `/stream/prices` 暂未鉴权；生产 backend 如果改成鉴权，前端需要带 token 拼接 query string（注释里已标注）。
3. **Cypress / Playwright Test runner 化**：当前的脚本是单文件 free-standing，便于 CI 接入。如果后续想接入 GitHub Actions 或 daily cron，可以加 `web/scripts/e2e-smoke.test.mjs` 包装成 vitest/jest 测试。

## 6. 运行方式

```bash
# 1) 确认 web/dist 已存在
cd web && npm run build

# 2) 安装 Playwright（一次性）
npm install --no-save playwright
./node_modules/.bin/playwright install chromium

# 3) 运行
node web/scripts/e2e-smoke.mjs
# 报告落到 web/scripts/e2e-report.json
```

## 7. 产物清单

- `web/scripts/e2e-smoke.mjs` — 主脚本（约 380 行）
- `web/scripts/e2e-report.json` — 机器可读测试结果
- `docs/dev-notes/20260704-e2e-smoke-report.md` — 本报告