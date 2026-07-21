# AD-Research 视觉美化方案

## 设计审计与前瞻性改造建议

> 编制日期：2026-07-11 | 基于 4 维度深度研究（前沿趋势 × Fintech 对标 × 视觉审计 × 信息密度）  
> 方法论：3 个独立研究 agent 并行调研 50+ 来源，视觉审计 agent 逐文件标记 27 个具体问题
>
> **实现状态（2026-07-21 核实）**：P0 全部及 P1 主体已落地——主色已迁移蓝靛（`web/src/styles/theme.css` `--accent: #2563EB` / 暗色 `#60A5FA`，保留 `data-accent="vermilion"` 兼容旧朱红）；暗色重塑为 GitHub Dark 风格，CRT 扫描线改为 `data-crt="on"` 可选开关（默认关闭，设置项 `crtEffect`）；三档信息密度（`data-density`，默认 comfortable 42px）已实现；Inter/JetBrains Mono 经 `@fontsource` 自托管加载（`main.tsx`）；暗色文字对比度按 WCAG AA 修正。注意：2026-07-21 起默认主题为**暗色**（dark-first），与本方案编制时相反。P1-4 Bento Grid、P2（AI 面板融合、语义微动效、"数据之光"）未实现。

---

## 一、执行摘要

AD-Research 前端在经历了 7 个 Phase 的设计系统重构后，已建立起完整的 CSS token 体系和 38 个页面级样式表。但从专业设计师和投资研究平台的双重标准审视，当前设计存在 **5 个结构性缺陷** 和 **3 个可迅速拉开差距的战略机遇**。

### 核心诊断

**缺陷**：
1. **信息密度偏稀** — 列表页 52px 行高 vs 行业标准 32-40px，专业用户会感觉"数据不够"
2. **Light/Dark 是两套视觉人格，而非同一系统的两面** — Light 是 Notion 极简白，Dark 是黑客 CRT 终端绿
3. **朱红色（#E11D48）作为金融平台主强调色存在语义冲突** — 红色在投资语境天然关联"亏损/风险"
4. **字体系统名存实亡** — Inter 字体未加载（无 @font-face 声明），所有用户看到的都是系统回退字体
5. **暗色模式存在 WCAG AA 合规风险** — 部分文本对比度不足 4.5:1

**机遇**：
1. **信息密度分级** — 从"一刀切"到"用户可调 + 场景自适应"，这是专业平台 vs 消费级产品的分水岭
2. **AI 融合型布局** — 对话式 AI 面板 + 传统数据面板的混合界面，当前竞品正在这一维度上拉开差距
3. **克制而有情感的动效** — 当前动效几乎为零，而 2025-2026 年的设计共识是"语义性微动效传递信息"

---

## 二、当前设计深度诊断

### 2.1 色彩与对比度

| 问题 | 位置 | 严重程度 |
|------|------|----------|
| 朱红 accent 与金融亏损语义冲突 | `theme.css:24` — `--accent: #e11d48` | 🔴 高 |
| Dark 模式文字对比度：`--text-secondary: #888888` 在 `#0a0a0a` 背景上的对比度仅约 4.3:1，不满足 WCAG AA（正文需 4.5:1） | `theme.css:258` | 🔴 高 |
| light 主题 surface/elevated/base 三层的视觉区分度极弱（`#ffffff` / `#f7f7f8` / `#f4f4f5`） | `theme.css:14-16` | 🟡 中 |
| Dark 主题 CRT 扫描线覆盖整个视口，对专业续航投研人员造成持续的视觉噪音 | `global.css:1693-1723` | 🟡 中 |

**改建议**：
- 将主 accent 从朱红迁移到**蓝-靛色系**（如 `#2563EB` 或更沉稳的深蓝 `#1D4ED8`），与国际主流金融终端对齐
- 提亮 dark 模式文字色：`--text-secondary` 从 `#888888` → `#A0A0A0`
- 将 CRT 扫描线改为"用户可选开关"，默认关闭

### 2.2 字体排印

| 问题 | 位置 | 严重程度 |
|------|------|----------|
| Inter 字体声明存在但无 `@font-face`，所有用户实际看到的是系统回退（macOS: SF Pro, Windows: Segoe UI, 中文: PingFang SC / Microsoft YaHei） | `theme.css:136` | 🔴 高 |
| 标签字号 11px / 暗色 10px 过小，中文笔画在 11px 以下几乎不可读 | `theme.css:148, 342` | 🔴 高 |
| 数据数字使用了 `tabular-nums` class 但未全局强制，仍有表格列使用比例数字 | 多处列表页 | 🟡 中 |
| Dark 主题数据数字使用 monospace 字体 (`--font-mono`)，而 light 主题使用 sans-serif | `theme.css:144, 337` — dark 下 `--text-data-xl: 400 40px/1.1 var(--font-mono)` | 🟡 中 |

**改建议**：
- 通过 `@import` 或 `@font-face` 真正加载 Inter（Google Fonts CDN 或自托管）
- 最小正文字号提升至 12px（中文场景）/ 13px（英文场景）
- 全局强制所有表格数值列使用 `tabular-nums`
- 统一 light/dark 数据数字字体策略

### 2.3 信息密度（用户特别关注）

这是 AD-Research 当前最核心的结构性问题。

**现状**：
- 列表页表格默认 `size="large"`，行高约 52px
- Dashboard 卡片间距慷慨，一屏约 6-8 个信息块
- 详情页 KPI 数据卡占据大量垂直空间

**行业基准**：
| 平台 | 列表行高 | 一屏可见行数（1440px 视口） |
|------|----------|---------------------------|
| Bloomberg Terminal | ~28px | 40+ |
| TradingView Watchlist | ~32px | 25-30 |
| Koyfin | ~36px | 20-25 |
| 万得 Wind | ~30px | 35+ |
| **AD-Research 当前** | **~52px** | **~12-14** |

**诊断**：AD-Research 的信息密度比专业竞品低约 **50-70%**。同样的屏幕空间，Bloomberg 用户能看到 3 倍的数据行。

### 2.4 视觉层次与分组

**优点**：`ad-panel` 系统提供了统一的卡片化容器，`ad-metric-strip` 和 `ResponsiveGrid` 提供了结构化的布局模式。

**问题**：
- Panel 的 header 区域与 body 区域的视觉分隔仅靠一条 1px 的 hairline，在数据密集场景下层次感不足
- 阴影系统过于保守（`shadow-card: 0 1px 3px rgba(0,0,0,0.04)`），在白色卡片+白色背景场景下几乎看不见
- 缺少"焦点区域"的视觉设计语言——所有卡片视觉权重相同，用户视线没有明确的锚点

### 2.5 交互与反馈

**优点**：hover 状态统一使用 `var(--bg-hover)`，过渡动画统一使用 `var(--transition-fast)`。

**问题**：
- 动效几乎为零：没有页面过渡、没有数据刷新反馈、没有 KPI 变化的视觉提示
- 按钮的 active 状态视觉反馈不足（仅背景色变化 2-3%）
- 表格行点击前往详情，但可点击性 affordance 不够直观（仅 `cursor: pointer`）

### 2.6 情感与个性

**核心问题**：当前设计缺乏独特的视觉记忆点。

Light 主题 = 任何一个 SaaS 产品的模板化外观。  
Dark 主题 = 一个有 CRT 美学偏好的开发者的个人终端。

两者都没有传达"**专业投资研究平台**"的品牌气质。用户关闭浏览器后无法在记忆中唤起 AD-Research 的任何独特视觉元素。

---

## 三、2025-2026 设计趋势与竞品对标精华

### 3.1 五大趋势（简要）

| 趋势 | 描述 | 对 AD-Research 的适用性 |
|------|------|------------------------|
| **Dark-First 设计** | 60-70% 专业用户偏好暗色，不再是"可选主题"而是设计起点 | ⭐⭐⭐⭐⭐ 必须采纳 |
| **Bento Grid 布局** | 便当盒式非对称网格，组织信息密度同时保持呼吸感 | ⭐⭐⭐⭐⭐ 适合 Dashboard |
| **AI-Native 混合界面** | 对话式 AI + 传统面板并存，AI 不是另一标签页而是常驻助手 | ⭐⭐⭐⭐ 差异机会 |
| **Liquid Glass UI** | 运动响应式毛玻璃，替代静态 Glassmorphism | ⭐⭐⭐ 点缀使用 |
| **语义性微动效** | 动效不再是装饰，而是信息传递载体（变化提示、焦点引导） | ⭐⭐⭐⭐ 气质提升 |

### 3.2 竞品设计矩阵

| 维度 | Bloomberg | TradingView | Koyfin | Robinhood | Ramp |
|------|-----------|-------------|--------|-----------|------|
| 信息密度 | 极高 | 中高 | 中高 | 极低 | 中 |
| 色彩风格 | 琥珀+黑 复古 | 蓝+绿 Token 化 | 深蓝+灰 专业 | 霓虹绿+黑 潮流 | 霓虹黄+白 极简 |
| 字体系统 | Monospace 全局 | Trebuchet MS | Sans-serif 混用 | 定制 Phonic | Inter 独占 |
| 动效丰富度 | 零 | 低 | 低 | 极高 | 极低 |
| **AD-Research 应朝向** | 信息密度 | Token 化 | 模块化 | 情感设计 | 纪律约束 |

---

## 四、美化方案（按优先级排列）

### P0 — 基础设施修复（立即执行，低风险）

#### P0-1：真正加载字体

```css
/* 在 index.html 或 main.tsx 中添加 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

/* 或自托管，性能更好 */
```

**效果**：跨平台字体统一，macOS 和 Windows 用户看到相同的视觉体验。

#### P0-2：强制 tabular-nums

```css
/* 全局覆盖 Ant Design 表格数值列 */
.ant-table-tbody > tr > td {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
```

**效果**：零成本、零视觉变化，但数字列对齐精度提升一个量级。

#### P0-3：提升 dark 模式的文字对比度

```css
:root[data-theme="dark"] {
  --text-secondary: #a0a0a0;  /* 从 #888888 提亮 */
  --text-tertiary: #787878;   /* 从 #808080 调整 */
  --text-muted: #606060;      /* 从 #7a7a7a 调整 */
}
```

#### P0-4：最小字号提升

```css
:root {
  --text-label: 600 12px/1.2 var(--font-sans);   /* 从 11px 提升 */
  --text-small: 500 13px/1.4 var(--font-sans);   /* 从 12px 提升 */
}
:root[data-theme="dark"] {
  --text-label: 500 12px/1.2 var(--font-sans);   /* 从 10px 提升 */
  --text-small: 500 13px/1.4 var(--font-sans);   /* 从 11px 提升 */
}
```

---

### P1 — 设计系统升级（中期，需逐步迁移）

#### P1-1：色彩系统重构 — 从朱红到蓝靛

这是本次美化方案中**最重要的单次变更**，需要审慎推进。

**为什么改**：
- 全球主流金融终端（Bloomberg、TradingView、万得、FactSet）无一使用红色系作为主 accent
- 红色在投资语境中已被"亏损/风险/警告"占据语义空间
- 蓝色传达"信任、精确、冷静"——正是量化研究和专业投资的需求
- 蓝-橙色组合是 Okabe-Ito 色盲安全色板的基础，提升无障碍性

**新配色方案**：

```
亮色主题（Light）：
  --accent:           #2563EB  (Blue-600, 沉稳专业蓝)
  --accent-hover:     #1D4ED8  (Blue-700)
  --accent-dim:       rgba(37, 99, 235, 0.08)
  --accent-border:    rgba(37, 99, 235, 0.20)

暗色主题（Dark）：
  --accent:           #60A5FA  (Blue-400, 暗色下提亮防刺眼)
  --accent-hover:     #93BBFD  (Blue-300)
  --accent-dim:       rgba(96, 165, 250, 0.12)
  --accent-border:    rgba(96, 165, 250, 0.25)
```

**迁移策略**：通过增加一个新的 `data-accent` 属性控制，默认使用蓝色，保留 `data-accent="vermilion"` 兼容旧用户。

```css
:root, :root[data-accent="blue"] {
  --accent: #2563EB;
  --accent-hover: #1D4ED8;
  /* ... */
}
:root[data-accent="vermilion"] {
  --accent: #E11D48;  /* 保留旧朱红色 */
  /* ... */
}
```

#### P1-2：暗色模式重塑 — 从 CRT 终端到专业暗色

**目标**：将 dark 模式从"黑客终端美学"转变为"专业投研工作站暗色设计"。

**具体措施**：

1. **CRT 扫描线默认关闭**：改为用户设置中的开关项（`ui_crt_scanlines: false`）

2. **暗色表面层级重新设计**：
```css
:root[data-theme="dark"] {
  --bg-base:     #0D1117;  /* GitHub 暗色基准（比纯黑 #000 更舒适） */
  --bg-elevated: #161B22;  /* 侧栏、header */
  --bg-surface:  #1C2128;  /* 卡片、面板 */
  --card-bg:     #1C2128;
  --card-border: #30363D;
  --border-default: #30363D;
  --border-strong: #484F58;
}
```

这个方案参考了 GitHub Dark、TradingView Dark、和 Bloomberg 新一代 UX 的共识——**暗色不是"反转亮色"，而是独立的色彩体系**。

3. **暗色模式强调色改为去饱和蓝**（见 P1-1）

#### P1-3：信息密度系统 — 用户可调的三档密度

这是回应用户"信息密度怎么设计最合理"的核心方案。

**设计原则**：不是所有页面都适合同一密度。提供 **Compact / Comfortable / Spacious** 三档，不同页面类型有不同默认值。

| 页面类型 | 默认密度 | Compact（32px行高） | Comfortable（42px行高） | Spacious（56px行高） |
|----------|---------|-------------------|----------------------|---------------------|
| **列表页** | Compact | 最大数据可见 | 适中 | 宽松 |
| **Dashboard** | Comfortable | 更紧凑网格 | 标准呼吸感 | 大卡片模式 |
| **详情页** | Comfortable | 紧凑信息呈现 | 标准间距 | 阅读友好 |
| **AI 对话** | Spacious | - | 标准 | 对话舒适 |
| **筛选器** | Compact | 更多筛选可见 | 标准 | - |

**技术实现**：

```css
/* 通过 <html data-density="compact|comfortable|spacious"> 控制 */

/* Compact 模式 */
:root[data-density="compact"] {
  --table-row-height: 32px;
  --table-cell-py: 6px;
  --table-cell-px: 10px;
  --card-padding: var(--space-3);
  --stat-card-value-size: var(--text-data-md-size);
  --section-gap: var(--space-3);
}

/* Comfortable 模式（默认） */
:root[data-density="comfortable"] {
  --table-row-height: 42px;
  --table-cell-py: 10px;
  --table-cell-px: var(--space-4);
  --card-padding: var(--space-4);
  --stat-card-value-size: var(--text-data-lg-size);
  --section-gap: var(--space-5);
}

/* Spacious 模式 */
:root[data-density="spacious"] {
  --table-row-height: 56px;
  --table-cell-py: 14px;
  --table-cell-px: var(--space-5);
  --card-padding: var(--space-5);
  --stat-card-value-size: var(--text-data-xl-size);
  --section-gap: var(--space-6);
}
```

**切换控件**：在 Header 右侧添加密度切换（和当前的涨跌色彩切换并列），或放入设置菜单。

#### P1-4：Bento Grid Dashboard 布局

**当前**：Dashboard 使用 4 列 `ResponsiveGrid`，所有卡片均等权重。

**方案**：采用便当盒（Bento Box）式非对称网格，让最重要的信息占据更大的视觉面积。

```
┌─────────────────────┬──────────┬──────────┐
│                     │ 市场概览  │ 今日评分  │
│   KPI 关键指标      │ 标普500   │ 最高/最低 │
│   4 个大数字卡      │ 纳指100   │ 热门自选  │
│                     │           │           │
├──────────┬──────────┼──────────┴──────────┤
│ 持仓盈亏  │ 行业轮动  │                    │
│ 今日+%   │ 热力图    │  最新研究报告/AI摘要 │
│          │          │                    │
├──────────┴──────────┼──────────┬──────────┤
│                     │ 新闻热点  │ 宏观经济  │
│  自选股迷你行情表    │ 最新5条  │ 指标速览  │
│                     │          │          │
└─────────────────────┴──────────┴──────────┘
```

**技术实现**：使用 CSS Grid 的 `grid-template-areas` + `span` 实现不等宽布局，每个卡片用 `ResponsiveGrid` variant 控制跨列数。

---

### P2 — 体验升级（长期，需设计验证）

#### P2-1：AI 对话式面板融合

当前 AIChat 是独立页面。建议将 AI 助手作为**常驻右侧抽屉/侧面板**，在浏览数据的同时可以随时提问。

参考：FinChat Copilot（顶部常驻）、AlphaSense Generative Search（@文档选择 + 三种推理深度）、Yahoo AlphaSpace（自然语言 → 自动构建视图）。

#### P2-2：语义性微动效系统

```css
/* 数据刷新过渡 */
@keyframes value-update {
  0%   { background: var(--accent-dim); }
  100% { background: transparent; }
}
.value-flash {
  animation: value-update 600ms ease-out;
}

/* KPI 阈值告警 */
@keyframes threshold-alert {
  0%, 100% { box-shadow: 0 0 0 0 var(--accent-dim); }
  50%      { box-shadow: 0 0 0 4px var(--accent-dim); }
}
.threshold-alert {
  animation: threshold-alert 2s ease-in-out 3;
}

/* 数值变化方向指示 */
.value-up   { color: var(--color-rise); transition: color 600ms; }
.value-down { color: var(--color-fall); transition: color 600ms; }
```

**原则**（参考 Ramp 的动效纪律）：
- 所有动效 ≤ 200ms
- 仅操作 `transform` 和 `opacity`
- 尊重 `prefers-reduced-motion`

#### P2-3：暗色模式下的 Liquid Glass 点缀

仅在 Header 和关键悬浮面板上应用，不作为全局风格。

```css
.app-layout__header {
  background: rgba(13, 17, 23, 0.80);  /* GitHub Dark base + 透明度 */
  backdrop-filter: blur(12px) saturate(120%);
  border-bottom: 1px solid rgba(48, 54, 61, 0.6);
}
```

#### P2-4：独特的品牌视觉记忆点

建议创建一个独特的品牌元素——**"数据之光"（Data Glow）**：

设计一个顶部全局数据更新指示器，以小脉冲光点表示数据源连接状态和最后更新时间。它微小但不被忽视，成为 AD-Research 的标志性视觉特征。

```
左上角 Logo 旁：
🟢 数据更新于 09:32:15  ·  tushare ✅  fred ✅  xueqiu ✅
```

---

## 五、设计 Token 升级总览

### 5.1 新增 Token

```css
:root {
  /* ---- 新增：暗色表面层级（Dark-first 设计）---- */
  --surface-0: #ffffff;        /* light: 根背景 */
  --surface-1: #f7f7f8;       /* light: 卡片/侧栏 */
  --surface-2: #f4f4f5;       /* light: 悬浮面板 */
  --surface-3: #ebebec;       /* light: 模态框 */

  /* ---- 新增：信息密度变量 ---- */
  --density-row-height: 42px;
  --density-cell-py: 10px;
  --density-cell-px: 16px;
  --density-card-padding: 16px;
  --density-section-gap: 20px;

  /* ---- 新增：Liquid Glass ---- */
  --glass-bg: rgba(255, 255, 255, 0.06);
  --glass-border: rgba(255, 255, 255, 0.08);
  --glass-blur: blur(12px);
}

:root[data-theme="dark"] {
  --surface-0: #0D1117;
  --surface-1: #161B22;
  --surface-2: #1C2128;
  --surface-3: #30363D;
}
```

### 5.2 调整 Token

参见 P0-4 和 P0-3 中的具体数值。

### 5.3 移除

- `theme.css:173-185` 中的部分 legacy 兼容别名（`--color-accent`、`--color-primary` 等），改用直接引用 `var(--accent)`
- CRT 扫描线效果改为用户可选开关（`data-crt="on"`）

---

## 六、实施路线图

| 阶段 | 内容 | 预计工时 | 风险 |
|------|------|---------|------|
| **第1周** | P0-1~P0-4 基础设施修复 | 1-2天 | 极低 |
| **第2周** | P1-1 色彩迁移（蓝靛方案 + 保留朱红兼容） | 2-3天 | 中（需全局回归测试） |
| **第3周** | P1-2 暗色模式重塑 | 1-2天 | 低 |
| **第4周** | P1-3 信息密度系统 | 2-3天 | 中（需测试各页面） |
| **第5-6周** | P1-4 Bento Grid Dashboard | 3-4天 | 中（需设计验证） |
| **第7周+** | P2 动效/Glass/AI融合 | 持续迭代 | 低 |

---

## 七、关键决策点（需用户确认）

1. **主强调色迁移**：是否同意从朱红（#E11D48）切换到蓝色系（#2563EB light / #60A5FA dark）？如果不完全放弃，是否接受通过 `data-accent` 双轨兼容？

2. **暗色模式重塑**：是否接受将 CRT 扫描线和暗角效果改为可选开关（默认关闭），并将暗色配色从 `#0a0a0a` 终端黑迁移到 GitHub Dark 式的 `#0D1117`？

3. **信息密度默认值**：列表页默认从 `size="large"`（52px）下调到 Compact（32px）还是 Comfortable（42px）？

4. **字体加载**：通过 Google Fonts CDN 还是自托管 Inter + JetBrains Mono？

5. **品牌记忆点**：对"数据之光"（左上角数据源状态指示器）的设计方向是否感兴趣？

---

## 八、不做的事情

以下是被研究证实**不适合**投资研究平台的流行趋势：

- ❌ **Neubrutalism**：粗黑边框+硬阴影在数据密集场景下过于喧闹
- ❌ **纯黑背景**：#000 在 OLED 上对比度过高，长时间使用加速视觉疲劳
- ❌ **极简主义过度**：不能因为"好看"牺牲信息密度——专业用户需要数据，不需要留白
- ❌ **装饰性动效**：不服务于信息传递的动效一律不要
- ❌ **AI 生成的紫色渐变+Inter 字体组合**：已被行业过度使用，"AI Slop" 审美疲劳

---

*报告编制：AD-Research 设计审计 | 2026-07-11 | 基于 4 个并行研究 agent 的调研成果*
