# AD-Research 前端重构 Phase 1 — 设计 Token + 浅色默认 + 退役 Print 主题

> **注**：本文为 2026-07-05 的时点记录，部分内容可能已过时（如默认主色已改为蓝靛 `#2563EB`、暗色已成默认主题、`global.css` 已拆分，以代码现状为准）。

**日期**：2026-07-05
**Phase**：1 / 7
**依据 plan**：`/Users/aidanliu/.claude/plans/sequential-jingling-ripple.md`
**Git status**：`feat(ui): phase 1 - design tokens + light clean default + retire print theme`

---

## 一、Phase 1 范围

> 不动业务页面（Dashboard / 列表 / 详情 / 工具页），只做"地基"：
> 1. 设计 token 表（CSS 变量）固化到 `theme.css`
> 2. 主题切换：浅色 Notion/Linear 风格为默认，dark（原 terminal）保留为可选，print 退役
> 3. `main.tsx` 通过 antd `ConfigProvider` 注入新 token
> 4. China/US 涨颜色约定用 `html[data-color-convention="…"]` 切换

后续 phase 2-6（共享组件改造、AppLayout 重写、Dashboard/列表/详情/工具页、admin、inline style 清理）会基于本 phase 的 token。

---

## 二、改动文件清单

| 文件 | 改动要点 |
|---|---|
| `web/src/styles/theme.css` | 重写 token 表：accent `#2e5bff` → `#E11D48`（rose-600 朱色）；新增 `--shadow-sm` / `--accent-active`；新增 `:root[data-color-convention="us"]` 切换红涨绿跌 ↔ 绿涨红跌；保留 `:root[data-theme="dark"]` 作为可选 dark；移除所有 print 相关变量；新增 `--row-height-dense/comfortable/spacious`（从 global.css 迁过来） |
| `web/src/hooks/useTheme.ts` | 类型 `'clean' \| 'dark'` → `'light' \| 'dark'`；`STORAGE_KEY` 保持 `ad-research-theme` 不变；增加 `LEGACY_ALIAS` 表把老值 `terminal` / `print` / `clean` 平滑迁到 `dark` / `light` / `light`；调用方拿到的永远是 `light`/`dark` |
| `web/src/main.tsx` | `useAntdTheme()` 把 `defaultAlgorithm` 分支的 `colorPrimary` 等改为 `#e11d48`；`colorPrimaryHover: #be123c`、`colorPrimaryActive: #9f1239`；`Alert` `colorInfoBg/Border` 改为朱色系（`#fff1f2`/`#fecdd3`）；Tab/Input/Select 的 active 色同步切换 |
| `web/src/components/AppLayout.tsx` | 增加 `useEffect`：把 `useSettingsStore.colorConvention` 同步到 `<html data-color-convention="…">`；两处 Segmented 主题选项 `value: 'clean'` → `value: 'light'` |
| `web/src/styles/global.css` | （本 phase 未改动，仍兼容使用 `var(--accent)` 等 token；Phase 6 时再做 inline-style 清理） |

未改动文件：
- `web/src/styles/global.css` 中的所有 antd override / 业务 class（Phase 2/4/5/6 阶段会改）
- 业务页面、路由、API 契约

---

## 三、设计 Token 表（Phase 1 版本）

### 颜色（light 默认）

| Token | 值 | 用途 |
|---|---|---|
| `--bg-base` | `#ffffff` | 主画布 |
| `--bg-elevated` | `#f7f7f8` | 侧边栏、header |
| `--bg-surface` | `#f4f4f5` | 次级填充 |
| `--bg-hover` | `rgba(0,0,0,0.03)` | 行/按钮 hover |
| `--bg-active` | `rgba(0,0,0,0.05)` | 按下态 |
| `--bg-input` | `#ffffff` | 输入框背景 |
| `--text-primary` | `#111113` | 标题、主数据 |
| `--text-secondary` | `#6b7280` | 正文 |
| `--text-tertiary` | `#9ca3af` | placeholder、meta |
| `--text-muted` | `#d1d5db` | 分割线、弱提示 |
| `--accent` | `#e11d48` | **主强调色（朱色 rose-600）** |
| `--accent-hover` | `#be123c` | hover |
| `--accent-active` | `#9f1239` | 按下态 |
| `--accent-dim` | `rgba(225,29,72,0.08)` | 柔和强调背景 |
| `--accent-border` | `rgba(225,29,72,0.20)` | 强调边框 |
| `--accent-glow` | `rgba(225,29,72,0.10)` | focus ring |
| `--card-bg` | `#ffffff` | 卡片背景 |
| `--card-border` | `#e5e7eb` | 卡片边框 |
| `--card-radius` | `12px` | 默认卡片半径 |
| `--border-default` | `#e5e7eb` | 默认边框 |
| `--border-strong` | `#d1d5db` | 强调边框 |
| `--border-hover` | `#d1d5db` | 边框 hover |
| `--color-rise` (china) | `#dc2626` | 红涨 |
| `--color-fall` (china) | `#16a34a` | 绿跌 |
| `--color-rise` (us) | `#16a34a` | 绿涨 |
| `--color-fall` (us) | `#dc2626` | 红跌 |
| `--color-success` | `#10b981` |  |
| `--color-error` | `#ef4444` |  |
| `--color-warning` | `#f59e0b` |  |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` | 新增 |
| `--shadow-md` | `0 4px 16px rgba(0,0,0,0.06)` |  |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.08)` |  |
| `--shadow-card` | `0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)` |  |
| `--shadow-card-hover` | `0 4px 12px rgba(0,0,0,0.06)` |  |
| `--text-on-accent` | `#ffffff` | 强调色上的文字 |

### 字体

- `--font-sans`: `Inter, "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif`
- `--font-display`: `DM Sans, Inter, …`（页面大标题，**本 phase 未引入外部字体**）
- `--font-mono`: `JetBrains Mono, "SF Mono", "Fira Code", "Cascadia Code", monospace`

> **决策**：本 phase 不引外部字体（避免污染 162KB 之外的 bundle size），全部走 system stack。后续 phase 评估加 `Inter` / `DM Sans` 自托管。

### 字号

| Token | Size / Weight / Line-height |
|---|---|
| `--text-h1` | 500 32px/1.2 |
| `--text-h2` | 600 24px/1.25 |
| `--text-h3` | 500 18px/1.35 |
| `--text-data-xl` | 400 36px/1.1 |
| `--text-data-lg` | 400 24px/1.2 |
| `--text-data-md` | 500 16px/1.3 |
| `--text-body` | 400 14px/1.6 |
| `--text-small` | 500 12px/1.4 |
| `--text-label` | 600 11px/1.2 |
| `--text-code` | 400 13px/1.4 (mono) |

每个 size 还配了一个 `--text-*-size` 别名（仅 px）方便给 antd `fontSize` 属性用。

### 间距

- `--space-1: 4px`、`--space-1-5: 6px`、`--space-2: 8px`、`--space-3: 12px`、`--space-4: 16px`
- `--space-5: 20px`（light 主题，**Phase 1 决策**：比之前的 24px 更紧凑的 SaaS 节奏）
- `--space-6: 32px`、`--space-7: 40px`、`--space-8: 48px`、`--space-9: 64px`
- 兼容别名：`--space-xs/sm/md/lg/xl`

### 圆角

`--radius-sm: 4px`、`--radius-md: 8px`、`--radius-lg: 10px`、`--radius-xl: 12px`（light 默认卡 12px）、`--radius-2xl: 16px`

### 阴影

`--shadow-sm/md/lg` + `--shadow-card`、`--shadow-card-hover`（保留原值，仅新增 `shadow-sm`）

---

## 四、Dark 主题（保留为可选）

`:root[data-theme="dark"]` 完全保留原 terminal 配色：

- `--accent: #5fa87a`（terminal 绿）
- `--bg-base: #0a0a0a`、`--bg-elevated: #111111`
- `--color-rise: #c96b6b`、`--color-fall: #5fa87a`
- `--space-5: 24px`、`--radius-xl: 14px`
- 字号偏 mono 化（数据值字体使用 `var(--font-mono)`）

切换由 `<Segmented>` 触发 → `useTheme.setTheme('light' | 'dark')` → 写入 `data-theme` 属性 → `useAntdTheme()` 监听到 `themechange` 事件并重新构建 antd token。

---

## 五、China/US 涨颜色约定

新增 CSS 选择器切换：

```css
/* 默认 china: 红涨绿跌 (--color-rise: #dc2626 / --color-fall: #16a34a) — 由 :root 提供 */
:root[data-color-convention="us"] {
  --color-rise: #16a34a;
  --color-rise-dim: rgba(22, 163, 74, 0.08);
  --color-rise-border: rgba(22, 163, 74, 0.20);
  --color-fall: #dc2626;
  --color-fall-dim: rgba(220, 38, 38, 0.08);
  --color-fall-border: rgba(220, 38, 38, 0.20);
}
:root[data-theme="dark"][data-color-convention="us"] {
  --color-rise: #5fa87a;
  --color-fall: #c96b6b;
  /* ...对应 dim/border */
}
```

`AppLayout` 在 mount 时 + `colorConvention` 变更时把 `data-color-convention` 写到 `<html>`，CSS 变量随之重排，业务组件无需感知。

---

## 六、主题切换逻辑说明

### 初始化顺序（避免闪白/闪黑）

1. `main.tsx` 顶部同步执行 `getInitialTheme()` → 读取 `localStorage['ad-research-theme']`
2. 立即 `document.documentElement.setAttribute('data-theme', …)` —— 在 React 挂载前 CSS 已经生效
3. `useAntdTheme()` 第一次渲染时读同一个 `data-theme` 属性，构建 antd ConfigProvider

### 用户切换

1. 用户在 header 点 `<Segmented>` → `setTheme('light' | 'dark')`
2. `useTheme` 内 `useEffect` 触发：
   - `<html data-theme>` 立即更新（CSS 同步刷新）
   - 写 localStorage
   - 派发 `themechange` CustomEvent
3. `main.tsx` 的 `useAntdTheme()` 监听 `themechange` → `setMode` → 重新构建 antd theme 对象

### 老用户迁移

`useTheme.ts` 的 `LEGACY_ALIAS` 表：

| 老 localStorage 值 | 迁移到 |
|---|---|
| `terminal` | `dark` |
| `print` | `light`（**print 已退役**） |
| `clean` | `light` |
| `light` | `light` |
| `dark` | `dark` |

→ 老用户开 app 那一刻就被无痛迁到新值，无需任何 UI 操作。

---

## 七、如何本地验证

```bash
cd web
npx tsc --noEmit                    # 0 errors
npm run build                       # 产出 dist/ 成功
npm run dev                         # 默认 light 朱色主题
```

切换流程验证：

1. 开 dev server 进首页 → 应该是浅色、朱色强调（导航栏 logo 是 rose-600，按钮 hover/active 跟随）
2. 右上点"月亮"图标 → 整体切到 dark terminal 风（背景黑、强调变 terminal 绿），无闪白
3. 点"太阳"切回 → 切回 light 朱色，无闪黑
4. 切换"红涨绿跌 ↔ 绿涨红跌" → 列表里正负值颜色立即翻转，跟随 token 切换
5. 缩放浏览器到 1280 / 768 / 375 → 响应式 padding/字号正确

---

## 八、Phase 1 验证结果（本次实施）

| 检查项 | 结果 |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errors |
| `npm run build` | ✅ 成功，5.06s 产出 dist/ |
| 默认 light 朱色主题 | ✅ `<html data-theme="light">`、`--accent: #e11d48` 已生效 |
| 主题切换（light ↔ dark）无闪白/闪黑 | ✅ 切换在 React 渲染前完成（main.tsx 顶部同步 setAttribute） |
| 老 localStorage print 值迁移到 light | ✅ `LEGACY_ALIAS` 表兜底 |
| antd ConfigProvider 跟 token 一致 | ✅ `colorPrimary/PrimaryHover/PrimaryActive`、Tabs inkBar、Input/Select active 全部朱色系 |
| color convention hook 工作 | ✅ `<html data-color-convention="china|us">` 写好后，CSS 变量自动切换 |
| global.css 兼容性 | ✅ 全部现有 class 仍引用 `var(--accent)`/`var(--color-rise)` 等 token，无破坏 |

### grep 审计（print 退役确认）

```
$ grep -rn "'print'\|\"print\"\|data-theme=\"print\"" web/src
web/src/hooks/useTheme.ts:7: *   - 早期: 'terminal' | 'print' (两套实验性主题)
web/src/hooks/useTheme.ts:47: * Print theme is retired — calling `setTheme('print')` is a no-op
```

→ 仅剩 `useTheme.ts` 内的两处文档注释解释迁移历史；**无任何 `'print'` 字符串字面量出现在实际代码中**（代码里只有迁移处理逻辑）。

`data-theme="print"` 全局 grep：**0 命中**。

`value: 'clean'` JSX 全局 grep：**0 命中**（两处 segmented 都已改为 `'light'`）。

`#2e5bff`（旧蓝主色）全局 grep：CSS 文件 0 命中；`main.tsx` 中也未出现（已替换为朱色系）。

---

## 九、已知未完成项（留给 phase 2-6）

- **Phase 2**：共享组件改造 + 新增组件（`PageShell` / `FilterToolbar` / `ResponsiveGrid` / `ContentCard` / `EmptyState` / `SectionHeading` 已存在但需统一成 Phase 1 token；`Panel` / `PageHeader` / `StatCard` / `ReturnTag` / `ThemeTag` / `InstrumentCodeTag` / `TickerTape` 需按 plan 调整）
- **Phase 3**：AppLayout 重写（sidebar 折叠态 / header sticky / 移动端 drawer），目前保留了原版
- **Phase 4-5**：业务页面（Dashboard / 列表 / 详情 / 工具 / AI / 策略 / 交易页）
- **Phase 6**：Admin 页 + inline style 清理收尾（约 78 个文件）
- **Phase 7**：截图、a11y、关键页面回归

本 phase 没改业务页面 —— 因此 `global.css` 里仍有大量旧样式 / inline style 残留，对应 Phase 6 清理。

字体策略：当前用 system stack，**未引外部字体**。后续 phase 评估 Inter 自托管 + DM Sans 大标题。

`--color-up` / `--color-down` 是 `global.css` 里个别遗留 legacy 别名（出现在 `.ad-text-rise` / `.ad-text-fall`），指向 `#ef232a` / `#14b143`。Phase 6 会改用 `var(--color-rise)` / `var(--color-fall)` 收敛掉。

---

## 十、回滚预案

如整体效果不达预期：

```bash
git revert HEAD     # 撤销本 commit
# 或
git reset --hard <phase0-commit>     # 切回 main
```

`localStorage` 的 `ad-research-theme` 老值会自动按 `LEGACY_ALIAS` 表迁回，用户无感。

print 主题若需要恢复，可从 `git log` 找到 pre-phase-1 的 `theme.css` commit，恢复 `[data-theme="print"]` 块。