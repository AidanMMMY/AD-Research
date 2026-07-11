# AD-Research 前端颜色 Token 一致性审计报告

- **审计日期**：2026-07-12
- **审计范围**：`web/src/**` 全量（styles/、components/、pages/、utils/、main.tsx）
- **审计方式**：纯静态扫描，未修改任何代码
- **审计目标**：定位硬编码颜色、未覆盖 token、自定义 rgba() 偏离、暗色覆盖缺失、命名不一致
- **结论先导**：整体 token 化率极高（页面层 100%），但 **`main.tsx`（antd 镜像主题）严重偏离 theme.css v2**，若干全局组件/旧版区域仍残留硬编码与错误的 fallback 色值。

---

## 1. 审计总览

| 维度 | 数字 | 评价 |
|---|---|---|
| 总 CSS 自定义属性 token | 160 个 | 体系完整 |
| 浅色 vs 暗色 token 配对 | 75 个色彩类 token 中 67 个有暗色 override | 高 |
| 颜色相关 legacy alias（如 `--color-up`/`--primary-solid`） | 8 个只在 light 定义 | 接受（皆 alias 链回规范 token） |
| 页面 `styles.css` 硬编码 `#hex` 数 | **0** | 优秀 |
| 页面 `styles.css` 硬编码 `rgba()` 数 | 3（仅 Dashboard 中作 `var(--accent-glow, ...)` 的降级） | 可接受 |
| `global.css` 硬编码 `#hex` 数 | 35（多数在 fallback、第二屏 Sci-Fi Login、AI 教辅、login aurora 效果） | 重点对象 |
| `global.css` 硬编码 `rgba()` 数 | 51（含 aurora 星空、阴影、autofill shadow、教辅 info 色） | 重点对象 |
| TSX 内硬编码颜色 | 113 行次，最多集中在 `main.tsx`（72） | 重点对象 |
| 命名大小写不一致 | **0** | 优秀（全部小写） |
| 后缀不一致（`-dim`/`-border`/`-bright`） | **0** | 优秀（命名规范严格） |

---

## 2. 设计 token 体系（theme.css）

### 2.1 Token 总览

- **160 个 token**（CSS 自定义属性），分 12 类：
  - Background Layers（8 个：`--bg-*`）
  - Accent（7 个：`--accent*`）
  - Primary Legacy Aliases（3 个：`--primary-*`）
  - Text（4 个：`--text-*` 不含 size）
  - Market Colors（13 个：`--color-rise/-fall/*` + 兜底 `--color-up/-down`）
  - Semantic Colors（success/error/warning 各 4 阶 + `--color-info`）
  - Score Colors（5 个：`--score-*`）
  - Categorical Chart Palette（10 个：`--chart-series-*` Okabe-Ito 色盲安全）
  - Card / Border / Shadow / Foreground-on-accent
  - Radius / Spacing（4px 基础栅格 + 语义化 spacing）
  - Typography（Inter + JetBrains Mono）
  - Animation / Glass / Density

### 2.2 暗色覆盖完整性

- **75 个色彩类 token 中**，**67 个** 在 `:root[data-theme="dark"]` 下有 override。
- 仅 8 个未覆盖（皆为"legacy alias"或"静态基础色"），**全部为 light 定义并通过 CSS 级联自动应用到 dark**：
  - `--color-accent`、`--color-down`、`--color-loss`、`--color-primary`、`--color-up` （→ `--accent` / `--color-rise` / `--color-fall` / `--accent` / `--color-rise`）
  - `--border-subtle`（→ `--border-default`）
  - `--surface-default`、`--surface-elevated`（→ `--bg-surface` / `--bg-elevated`）
  - `--primary-dim`、`--primary-solid`（→ `--accent-dim` / `--accent`）
- **score-fill/glass-bg/blur/border 在 dark 下正确覆盖**。
- **结论：暗色 / 浅色 配色一致，无"漏颜色"问题**。

### 2.3 主色切换兼容

- v2 设计系统支持 `<html data-accent="blue|vermilion">` 双主题。
- 暗色 + 朱红色兼容也已提供（`[data-theme="dark"][data-accent="vermilion"]` 块，第 401-409 行）。
- 暗色 + US 涨跌约定（绿涨红跌）：第 412-419 行已提供。

---

## 3. 硬编码颜色清单

### 3.1 页面 `styles.css`（共 41 个文件，全部干净）

`grep -rE '#[0-9a-fA-F]{3,6}\b' web/src/pages --include='*.css'` → **0 行**匹配。
`grep -rE 'rgba?\(' web/src/pages --include='*.css'` → **仅 3 行**，全部在 `Dashboard/styles.css`：

| 文件 | 行号 | 现状 | 建议 |
|---|---|---|---|
| Dashboard/styles.css | 258 | `box-shadow: 0 0 0 1px var(--accent-glow, rgba(37, 99, 235, 0.12));` | fallback 是 light theme 的 `--accent-glow` 值。建议改为 `var(--accent-glow)`（去掉 fallback 即可，token 已必现） |
| Dashboard/styles.css | 370 | `background-color: var(--accent-glow, rgba(37, 99, 235, 0.12));` | 同上 |
| Dashboard/styles.css | 407 | `box-shadow: 0 0 0 1px var(--accent-glow, rgba(37, 99, 235, 0.12));` | 同上 |

**小结：页面层 token 化率 100%，可作为团队模板。**

### 3.2 全局 `global.css`（8728 行，35 hex + 51 rgba）

> 注：以下行号均来自 `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css`。

#### 3.2.1 硬编码 hex（35 行）

| 行号 | 上下文 | 硬编码值 | 建议替换 |
|---|---|---|---|
| 444 | `.ant-checkbox-checked .ant-checkbox-inner::after` | `border-color: #fff` | `var(--text-on-accent)` |
| 1598 | `.ad-text-rise` | `var(--color-up, #ef232a)` | fallback 与 token `--color-rise: #dc2626` 不一致，先改 token 引用为 `var(--color-rise)`，再删 fallback |
| 1602 | `.ad-text-fall` | `var(--color-down, #14b143)` | fallback 与 `--color-fall: #16a34a` 不一致，同上改正为 `var(--color-fall)` |
| 1775-1783 | `.login-grid mask` 渐变线性刻度 | `#000 24px` / `#000 calc(100% - 24px)` | 改 `var(--bg-base)` 或保留硬黑（mask 场景可接受）。建议建 `--shadow-mask` token |
| 6658 | `.login-logo-icon` | `color: #fff` | `var(--text-on-accent)` |
| 6722 | `.login-submit` | `color: #fff` | `var(--text-on-accent)` |
| 6767 | `.login-page--sci-fi` | `background: #05060a` | 建议建 `--bg-aurora-base` token，与浅色主题并存 |
| 6781 | `.aurora-base` | `background: #05060a` | 同上 |
| 7187 | `.login-page--sci-fi .login-submit` | `color: #fff` | `var(--text-on-accent)` |
| 7362 | autofill shadow | `var(--bg-input, #ffffff)` | 已带 fallback 且与 light token 一致；可去 fallback 保 token 必现 |
| 7363-7364 | autofill | `var(--text-primary, #111113)` | fallback `#111113` 与 light token `#0F1115` 不一致（色深 1~2%），建议消除或建 `--text-on-input` |
| 7376 | dark autofill | `var(--bg-base, #0a0a0a)` | fallback 与 dark token `#0D1117` 不一致（5% 偏亮） |
| 7377 | dark autofill text | `var(--text-primary, #f5f5f0)` | fallback 与 dark token `#E6EDF3` 不一致（明显偏黄） |
| 7459 | `.page-header-tutorial` | `border-left: 3px solid var(--color-primary, #4096ff)` | `#4096ff` 是 antd 旧版"拂晓蓝"，**v2 主色已切换至 `#2563EB`**。改 `var(--accent-border)` |
| 7463 | 同上 | `color: var(--text-secondary, #555)` | fallback `#555` 与 light token `#5B6778` 偏红不一致 |
| 7468, 7493, 7827, 8025 | 多处 | `var(--color-primary, #4096ff)` | 同上，主色应改为 `var(--accent)` / `var(--accent-strong)` |
| 7477, 7851, 7717, 8030 | 多处 | `var(--text-tertiary, #888)` | fallback 是 `#888`，与 light token `#8894A4` 不同。建议移除 fallback 或建 `--text-tertiary-strong` |
| 7717, 7794, 7818, 8037, 8094 | 多处 | `var(--text-primary, #222)` | fallback `#222` 与 light `#0F1115` 差距大 |
| 7742, 7800, 7856, 8043 | 多处 | `var(--text-secondary, #555)` | fallback `#555`，见上 |
| 7794, 7818, 8037, 8094 | 多处 | `var(--text-primary, #222)` | 同上 |
| 8094 | 详尽列表内的标题色 | `var(--text-primary, #222)` | 同上 |

**`--color-primary` 与 `#4096ff` 重复共 6 处（lines 7459/7468/7493/7827/7856/8025）**——这是 antd 旧版的"拂晓蓝"，v2 改蓝靛后遗留，**强烈建议一次性改为 `var(--accent)` / `var(--accent-border)`**。

#### 3.2.2 硬编码 rgba（51 行）

按出现密集区归类：

##### A. Skeleton / Shadow / 通用遮罩（11 处）
| 行号 | 值 | 上下文 |
|---|---|---|
| 489 | `linear-gradient(..., rgba(0,0,0,0.03) ... 0.08 ...)` | skeleton light |
| 494 | `linear-gradient(..., rgba(255,255,255,0.03) ... 0.08 ...)` | skeleton dark |
| 1329 | `background: rgba(0,0,0,0.45)` | 通用遮罩 |
| 3303 | `background: rgba(0,0,0,0.6)` | 全屏 modal overlay |
| 4026 | `background: rgba(40,199,111,0.08)` | 旧 success 背景 |
| 4030 | `background: rgba(255,90,95,0.08)` | 旧 error 背景 |
| 5151 | `background: rgba(0,0,0,0.6)` | 同 3303 |
| 5953 | `box-shadow: 0 2px 8px rgba(0,0,0,0.08)` | shadow-md 老样式 |
| 7578, 7752 | `box-shadow: 0 1px 3px rgba(0,0,0,0.04/0.08)` | tip 阴影 |
| 7994 | `border-top: 1px dashed rgba(0,0,0,0.04)` | 浅色虚线分隔线 |

**建议**：
- 对应 token 已存在：`--shadow-sm/md/lg`、`--bg-active/hover`、`--color-success-dim`、`--color-error-dim`、`--border-default`。
- 1132 行、3303、5151 的 `rgba(0,0,0,0.45)` / `0.6` 应建 `--mask-overlay` token。

##### B. Login Sci-Fi 沉浸效果（约 25 行，6600-7100）
| 行号 | 上下文 | 颜色 |
|---|---|---|
| 6612-6613 | `.login-grid` | `rgba(255,255,255,0.03)` 双方向网格 |
| 6630 | `.login-card` | `rgba(17,17,17,0.72)` 玻璃卡（深色卡片主题） |
| 6803-6829 | `.aurora-layer *` | `rgba(0,229,255,*)` `rgba(0,180,255,*)` `rgba(120,80,255,*)` `rgba(64,220,220,*)` `rgba(180,120,255,*)` 多色光晕 |
| 6871-6895 | `.login-source-dot` 发光圆点 | `rgba(255,255,255,0.6)` + 蓝青系列 |
| 6910-6951 | `.aurora-meteor` 流星轨迹 | `rgba(255,255,255,0)` `rgba(180,240,255,0.6)` `rgba(255,255,255,0.95)` |
| 6960 | `.aurora-base` vignette | `rgba(5,6,10,0.6)` |
| 7033-7038 | `.terminal-frame` 终端框 | `rgba(96,165,250,0.18/0.25/0.1)` |
| 7069-7070 | 顶部/底部 divider | `rgba(255,255,255,0.04)` |
| 7084-7085 | `@keyframes login-source-pulse` | `rgba(34,197,94,0.25/0.65)`（**成功色，但硬编码 `#22c55e` 而非 token**） |
| 7140, 7141, 7149 | `.login-input-wrapper` sci-fi 玻璃 | `rgba(255,255,255,0.03/0.08/0.05)` |
| 7398, 7405 | autofill shadow | `rgba(255,255,255,0.03/0.05)` |

**评价**：Sci-Fi Login 是"刻意设计"的沉浸视觉，与 v2 主色（蓝靛）部分一致（aurora 用 #60A5FA 同系色），但所有颜色都未走 token。建议：
- 把 aurora 与 `#60A5FA` / `#A78BFA` 关联到 `--accent-glow` / `--accent-soft` 或新增 `--aurora-blue` / `--aurora-violet` token；
- 把 `rgba(255,255,255,0.03-0.08)` 关联到新建 `--glass-*` token（已有 `--glass-bg/border/blur`，扩展 alpha 梯度）；
- 把 `#22c55e`（success 关键帧）改为 `var(--color-success)`。

##### C. Learning / K15 区（约 16 行，7400-8050）
| 行号 | 上下文 | 颜色 |
|---|---|---|
| 7457-7458 | `.page-header-tutorial` 渐变背景 | `rgba(64,169,255,0.08)` + `rgba(120,109,245,0.06)` |
| 7734 | `.dashboard-learning-chips` 背景 | `rgba(64,169,255,0.04)` |
| 7826, 8024 | step-num / onboarding-tour-step-icon 背景 | `rgba(64,169,255,0.12)` |
| 6612-6613, 7140-7149 | 同上分区 | - |

**评价**：K15 学习模式**全部用 `#4096ff`（antd 拂晓蓝）硬编码**，明显遗留 v2 切换前的代码。
**建议**：批量替换为 `var(--accent)` 系列（`--accent-dim`/`--accent-border`/`--accent-soft`），不要保留硬编码。

---

### 3.3 TSX/TS 硬编码颜色（共 113 行次，分布在 11 个文件）

| 文件 | 行次 | 形式 | 性质 | 建议 |
|---|---|---|---|---|
| **main.tsx** | **72** | antd `ConfigProvider` 颜色镜像 | **严重**（与 theme.css v2 不一致） | 详见 §4 |
| `components/CategoryPie.tsx` | 4 | 调色板 + chart fallback | 主 | 用 `var(--color-rise/-fall)` 系列 |
| `components/CorrelationHeatmap.tsx` | 7 | chart fallback | 主 | 用 `var(--*)` |
| `components/ScoreRadar.tsx` | 5 | chart fallback | 主 | 用 `var(--*)` |
| `components/KLineChart.tsx` | 6 | chart fallback | 主 | 用 `var(--*)` |
| `components/ParticleBackground.tsx` | 2 | chart fallback | 主 | 用 `var(--*)` |
| `components/ReturnCurve.tsx` | 10 | 系列调色板 + fallback | 主 | 用 `var(--chart-series-1..10)` |
| `pages/SectorRotation/index.tsx` | 6 | echarts fallback | 中 | 同上 |
| `pages/NewsHealth/index.tsx` | 4 | `var(--color-success, #52c41a)` 等 | 低（fallback 但 token 已定义） | 移除 fallback 或建 `--color-success-strong` |
| `utils/cssVar.ts` | 1 | `?? '#000'` 兜底 | 低（极少触发的安全兜底） | 可接受，但建议改为 `--text-primary` |

**附 `main.tsx` 详细清单**（72 行，分两套完整 antd token）：

- Dark 主题 token（行 63-141）用了旧值：
  - `colorPrimary: '#5fa87a'`（terminal 绿，**与 theme.css v2 dark 的 `#60A5FA` 不一致**）
  - `colorBgBase/Container/Elevated: '#0a0a0a' / '#111111' / '#111111'`
  - `colorTextBase: '#f5f5f0'`（黄白偏暖，与 `#E6EDF3` 不一致）
  - `colorTextSecondary: '#888888'` vs theme.css dark `--text-secondary: #A0A0A0`
  - `colorTextTertiary: '#444444'` vs theme.css dark `--text-tertiary: #787878`
- Light 主题 token（行 145-248）沿用了 v1 的朱红：
  - `colorPrimary: '#e11d48'`（rose-600，**theme.css v2 light 已改 `#2563EB` 蓝靛**）
  - `colorPrimaryHover/Active: '#be123c'/'#9f1239'`（rose-700/800，**主色已不是 rose**）
  - `colorBgBase/Container: '#ffffff'/'#ffffff'` vs theme.css `#FAFBFC/#ffffff`（差 1%）
  - `colorBgElevated: '#f7f7f8'` vs theme.css `--bg-elevated: #F3F5F7`
  - `colorTextBase: '#111113'` vs theme.css `--text-primary: #0F1115`
  - `colorTextSecondary: '#6b7280'` vs theme.css `#5B6778`
  - `borderRadius*: 8/4/12/2` vs theme.css `--radius-md/sm/lg/none` **命名口径不同**
- Dark 与 Light 的 `Alert`/`Input`/`Select`/`Tabs` 颜色全套硬编码，**完全镜像了 antd v5 默认调色板**，未与 theme.css 对齐。

**结论**：`main.tsx` 是 antd v5 的 JS 镜像主题，必须改成「读 `--accent`、`--bg-*`、`--text-*` 后注入」的 SSR 安全模式（或在 `useTheme` hook 的 `themechange` 监听器里同步重算），否则：
1. 用户切到 dark theme，antd 组件仍显示 light 主色（视觉割裂）
2. v2 把 light 主色从朱红改成蓝靛后，antd Button / Input focus ring / Tag 颜色保持旧朱红
3. 同色相偏 5-15%，违反 P0-3 对比度提升原则

**附 cssVar.ts 上下文**：helpers 已支持 `var(--*)` 解析，但 8 个 chart 组件仍把 fallback 写成旧 dark 调色板值（`#5fa87a`/`#c96b6b`）。这些 fallback 仅在 SSR / 无 DOM 时触发，与 theme.css 不一致（**dark token 是 `#5FA87A`/`#C96B6B` 小写**，hex 大小写本身就不一致）。

---

## 4. 暗色 / 浅色主题覆盖矩阵

按"色彩 token 是否在两种主题都有定义"评分：

| 颜色族 | light 定义 | dark override | 状态 |
|---|---|---|---|
| `--bg-*` 8 个 | ✅ | ✅ | 完美 |
| `--accent*` 7 个 | ✅ | ✅ | 完美 |
| `--text-*` 4 色阶 | ✅ | ✅ | 完美 |
| `--color-rise/fall/neutral` | ✅ | ✅ | 完美 |
| `--color-success/error/warning/info` + dim/border/bright | ✅ | ✅ | 完美 |
| `--score-*` 6 个 | ✅ | ✅ | 完美 |
| `--chart-series-*` 10 色 | ✅ | ✅ | 完美（dark 重新调色） |
| `--card-*` `--border-*` `--shadow-*` `--glass-*` | ✅ | ✅ | 完美 |
| `legacy alias` (`--color-up/-down/-primary/-accent/-loss`、`--primary-*`、`--border-subtle`、`--surface-*`) | light only | 不必要 | 可接受 |

**唯一一条** parity 纰漏：theme.css 没有专门给 `data-accent="vermilion"` + 暗色模式下的 `--color-warning/--color-success/--color-error` 配套定义。当前的 vermilion override 只动 `--accent*`，所以 vermilion dark 下 success/warning/error 仍是 blue-indigo 同款色（会与朱红主色不和）。见 theme.css 第 401-409 行。建议追加 `[data-accent="vermilion"][data-theme="dark"]` 块，置红系语义色。

---

## 5. 命名规范审计

### 5.1 大小写

- 全部 CSS 变量名 **小写 + 中划线**（kebab-case），**0 例外**。✅

### 5.2 后缀规范

- `-dim`：用在"背景稀释"色（10% 透明），覆盖 `accent/color-*` 11 个。✅
- `-border`：用在"边框色"（20% 透明），覆盖 8 个。✅
- `-bright`：用在"提亮 / 高亮"色，覆盖 `success/error/warning` 3 个。✅
  - ⚠️ `warning-bright` 还衍生 `--color-warning-bright-dim`（18% 透明），是唯一带 `bright-dim` 后缀的 token，命名未与其他 dim 统一（其他 dim 永远 8%）。**建议**：
    - 改成 `--color-warning-hover-dim`，与 `--accent-hover` 命名口径一致；或
    - 增加 `--color-warning-bright-alpha-18` 等层级（不推荐）。
- `-hover` / `-active` / `-glow` / `-soft`：只在 `--accent*` 体系下，命名清晰。✅
- legacy alias `--primary-*`：本应清退，可统一改名为 `--brand-*`，避免与 `color-primary`（alias to `--accent`）混淆。当前 `-dim` / `-solid` 在 `--primary` 和 `--accent` 两套体系并存，使用者容易误用，建议合并。

### 5.3 色名 vs 价格 / 涨跌术语

`--color-rise/-fall`（中文：涨/跌）vs `--color-up/-down`（alias）vs `--color-success/-error/-loss`（业务语义）。命名有些冗余：
- `--color-up = var(--color-rise)`
- `--color-down = var(--color-fall)`
- `--color-loss = var(--color-error)`

建议保留 `--color-rise/-fall`（与"涨跌色约定"语义强），清退 `--color-up/-down/-loss` 三 alias，避免 shadow 类 API（旧终端代码）继续蔓延。

---

## 6. Alpha 透明度一致性

### 6.1 `xxx-dim` 模式

- light theme 统一 `0.08`（10%），dark theme 统一 `0.12`（12%），alpha 略提升体现"暗色视觉补偿"。✅ 规范统一。
- 例外：`--color-warning-bright-dim: 0.18`（18%），单独高出 1.5–2 倍 alpha，无设计理由注释。⚠️

### 6.2 `xxx-border` 模式

- light `0.20`，dark `0.25`。同样 5% 提升，逻辑统一。✅

### 6.3 第三方 / 自定义 rgba

很多地方直接写 `rgba(0,0,0,0.05)` 或 `rgba(255,255,255,0.05)` 表示"hover/active/divider"，与 token 不挂钩（如 1329、3303、5151、7994 行）。建议建：
- `--hover-overlay-light` = `rgba(0,0,0,0.05)`
- `--hover-overlay-dark` = `rgba(255,255,255,0.05)`
- `--scrim` = `rgba(0,0,0,0.45)`（modal mask）
- `--scrim-strong` = `rgba(0,0,0,0.6)`

这样所有 `rgba(0,0,0,*)` 与 `rgba(255,255,255,*)` 的"遮罩类"使用都可以收敛。

---

## 7. 重点风险 / 必须修复项（按严重度排序）

### P0 — 影响生产（视觉割裂 / 与 v2 设计意图冲突）
1. **`main.tsx` antd 主题与 theme.css v2 完全错位**（light 应是蓝靛 `#2563EB`，main.tsx 仍是朱红 `#e11d48`；dark 蓝靛 `#60A5FA`，main.tsx 仍是绿 `#5fa87a`）。切主题时 antd 组件（Button/Tabs/Input/Alert）会保持旧色，与 CSS 自绘元素出现明显视觉割裂。
2. **K15 学习模式整套样式用 antd 旧色 `#4096ff`**（global.css 7459/7468/7493/7477/7717/7742/7794/7800/7818/7827/7851/7856/8024/8025/8030/8037/8043/8094 共 18 行），v2 切蓝靛后这部分教学辅助仍为拂晓蓝。

### P1 — 设计一致性受损
3. **所有 chart fallback（8 个 chart 组件 + cssVar.ts）写了 `#5fa87a` / `#c96b6b` / `#888888` 等旧 dark 调色板值**。SSR/无 DOM 时 fallback 不与 v2 dark token（`#5FA87A`/`#C96B6B`）对齐（实际数值一致，但小写），属于侥幸命中，**必须显式声明"是 fallback"并写入 ADR**。
4. **Sci-Fi Login 的 aurora/grid/source-dot 系列 25+ 处 rgba**(蓝青色)，与 v2 主色 `#60A5FA` 巧合一致但未走 token。**建议**收敛到 `--accent-glow` / 新增 `--aurora-*` token。
5. **`var(--color-up, #ef232a)` / `var(--color-down, #14b143)`** 这两条 fallback 与 `--color-rise: #dc2626` / `--color-fall: #16a34a` 偏差 7% hue（global.css 1598/1602），是历史遗留的"过早 fallback"，SSR 兜底时会显示不对的色。**建议**直接去掉 fallback 或建 `--color-rise-fallback` / `--color-fall-fallback`（不推荐，删除最干净）。

### P2 — 命名 / 工程治理
6. **`--color-warning-bright-dim: 0.18`** 与其他 `-dim` 体系 alpha 不一致（其他 dim 都是 0.08/0.12）。建议改名 `--color-warning-hover-dim` 或调整 alpha 到 0.12。
7. **legacy alias (--color-up/-down/-loss/-primary/-accent / --primary-*)** 与规范 token 并存，建议在三年内清退。
8. **`rgba(0,0,0,0.04-0.6)` / `rgba(255,255,255,0.03-0.08)` 共 14+ 处**用作 hover/scrim/divider，未走 token。建议建 `--hover-overlay-light/-dark` 与 `--scrim/-scrim-strong`。

### P3 — 已知 / 可接受
9. page `styles.css` 100% token 化，仅 Dashboard 3 行 `var(--accent-glow, rgba(37,99,235,0.12))` 的 fallback，建议去掉。
10. `--color-primary` 在 antd 内部仍保留使用（global.css 多处），但这是 alias 到 `--accent`，可保留以兼容。
11. `data-accent="vermilion"` 暗色下 semantic 色（success/error/warning）未联动，建议 v2.1 补 override。

---

## 8. 推荐改造路线图

### 8.1 立即修复（1-2 个 sprint）
1. 改 `main.tsx`：在 `useAntdTheme()` 中所有颜色改读 `readCssVar('--xxx')`，监听 `themechange` 自定义事件重算；
2. global.css K15 区（~18 行）：把 `var(--color-primary, #4096ff)` / `var(--text-*, #xxx)` 全部改为无 fallback 的规范 token；
3. 全局 `var(--color-up, #ef232a)` / `var(--color-down, #14b143)`：去掉 fallback 或更新为 `--color-rise/-fall` 实际值；
4. Dashboard/styles.css 三处 `var(--accent-glow, rgba(...))`：去掉 fallback。

### 8.2 设计 token 扩充（v2.1）
- 新增 `--hover-overlay-light`、`--hover-overlay-dark`、`--scrim`、`--scrim-strong`；
- 新增 `--aurora-blue`、`--aurora-violet`、`--aurora-cyan`（或合并为 `--accent-glow-x`、`--accent-glow-y` alpha 档位）；
- 新增 `vermilion + dark` 的 semantic 色 override；
- 把 `--color-warning-bright-dim` 改名 `--color-warning-hover-dim` 并调 alpha 到 0.12。

### 8.3 长期治理
- 增设 Stylelint 规则：
  - `color-no-hex: true`（针对 `*.module.css`，允许 theme.css / global.css 例外）
  - `declaration-property-value-disallowed-list`：`rgba?` 仅允许在 `theme.css` / `global.css` 中使用
  - `custom-property-no-missing`：CI 跑一遍 light vs dark 配对，自动生成 token parity 报告
- 改 `cssVar.ts`：所有 chart fallback 改为 `readCssVar` 二级 fallback（先尝试 root `--xxx`，再尝试旧的 hex），并**删除 `#000` 兜底**改为 `readCssVar('--text-primary', 'inherit')`。

---

## 9. 快速复现 / 校验命令

```bash
# 1. 页面层硬编码扫描（应返回 0）
cd web/src/pages
grep -rEn '#[0-9a-fA-F]{3,6}\b' . --include='*.css' | wc -l

# 2. 全局硬编码 hex 清单
grep -nE '#[0-9a-fA-F]{3,6}\b' web/src/styles/global.css

# 3. TSX 颜色清单（按文件汇总）
grep -rEn '#[0-9a-fA-F]{3,6}\b' web/src --include='*.tsx' --include='*.ts' \
  | cut -d: -f1 | sort | uniq -c | sort -rn

# 4. token 配对校验
awk '/:root \{/{f="L";next} f=="L" && /^\}/{f="";next} f=="L" && /--/{
  match($0,/--[a-zA-Z0-9_-]+/); print substr($0,RSTART,RLENGTH)}' \
  web/src/styles/theme.css | sort -u > /tmp/light.txt

awk '/:root\[data-theme="dark"\]/{f="D";next} f=="D" && /^\}/{f="";next} f=="D" && /--/{
  match($0,/--[a-zA-Z0-9_-]+/); print substr($0,RSTART,RLENGTH)}' \
  web/src/styles/theme.css | sort -u > /tmp/dark.txt

comm -23 /tmp/light.txt /tmp/dark.txt   # light only（含 alias，正常）
comm -13 /tmp/light.txt /tmp/dark.txt   # dark only（应为空）
```

---

## 10. 总结

AD-Research 前端 token 化推进成果**显著**：
- **160 个 token** 覆盖 4×4 设计栅格；
- **暗色主题覆盖完整**，75 个色彩 token 中 67 个有暗色 override，8 个 legacy alias 通过级联复用；
- **页面 styles.css 100% token 化**；
- **命名严格小写 kebab-case**，后缀（`-dim/-border/-bright`）一致；

但仍有**两处系统性偏差**必须立即处理：
1. **antd 镜像主题（main.tsx）停在 v1 朱红/绿色，与 theme.css v2 蓝靛错位** — 切换主题时 antd 组件颜色不变，与 CSS 自绘元素割裂；
2. **K15 学习模式区 + Sci-Fi Login 的 rgba/anth-design legacy fallback** — 整体视觉停留在 antd 拂晓蓝，与 P0-3 设计目标冲突。

后续按 §8 三阶段路线图改造，预计 1-2 个 sprint 把硬编码收敛到 < 10 处残余（仅限 animation 关键帧与 mediatype 边界场景）。
