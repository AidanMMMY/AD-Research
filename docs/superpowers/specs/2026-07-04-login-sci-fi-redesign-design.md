# AD-Research 登录页科幻风格重设计

**日期：** 2026-07-04  
**状态：** 待实现  
**范围：** `web/src/pages/Login.tsx`、`web/src/components/AuroraBackground.tsx`、`web/src/styles/global.css`

---

## 1. 设计目标

将现有登录页从「浅色卡片 + 灰色表单」改造成具有科幻感的沉浸式登录入口，同时保留所有登录功能、错误处理和无障碍支持。

---

## 2. 用户决策（已确认）

| 维度 | 选择 | 说明 |
|---|---|---|
| 整体风格 | 极简未来 Minimal Sci-Fi | 克制、专业、不花哨 |
| 页面布局 | 全屏沉浸式 Immersive | 登录卡片像 HUD 悬浮在动态背景上 |
| 背景氛围 | 极光渐变 Aurora Gradient | 大面积柔和光晕缓慢流动 |
| 强调色 | 科幻青 Cyan Sci-Fi | `#00e5ff` → `#00b8d4` 渐变，与现有品牌蓝区分 |

---

## 3. 视觉设计

### 3.1 背景

- 底色：`#05060a`（近黑）
- 极光：多层径向渐变，青/蓝/紫混合，使用 CSS animation 缓慢位移和缩放（周期 12s）
- 点缀：稀疏星光（绝对定位小圆点）+ 细微扫描线/粒子连线
- 动效：背景持续缓慢流动，不抢表单注意力
- 无障碍：`prefers-reduced-motion: reduce` 时停止背景动画，改为静态渐变

### 3.2 登录卡片

- 位置：页面正中央
- 尺寸：最大宽度 420px，移动端 92vw
- 背景：`rgba(10, 12, 18, 0.55)` + `backdrop-filter: blur(24px)`
- 边框：1px `rgba(0, 255, 200, 0.12)`
- 阴影：`0 0 60px rgba(0, 255, 200, 0.08)`
- 四角：科技切角装饰（2px 青色半透明边框）
- 悬浮感：细微 `translateY` 呼吸动画（可选）

### 3.3 Logo 与标题

- Logo：保留 `StockOutlined`，外层改为深色玻璃质感容器 + 青色光晕
- 品牌名：`AD-Research`，白色，字重 600，letter-spacing 0.5px
- 副标题：「全市场数据分析与投研工具」，半透明白色

### 3.4 输入框

- 背景：`rgba(255, 255, 255, 0.04)`
- 边框：1px `rgba(255, 255, 255, 0.08)`
- 圆角：12px
- 图标：使用 Lucide/UserOutlined/LockOutlined 或自定义 SVG，颜色 `rgba(0, 255, 200, 0.7)`
- Placeholder：`rgba(255, 255, 255, 0.35)`
- Focus：边框变为青色，添加 `box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.15)`

### 3.5 登录按钮

- 背景：线性渐变 `#00e5ff` → `#00b8d4`
- 文字：深色 `#001214`，字重 600
- 圆角：12px
- 阴影：`0 0 24px rgba(0, 229, 255, 0.25)`
- Hover：亮度提升，轻微放大 `scale(1.02)`
- Loading：显示「登录中...」，禁用状态透明度 0.7

---

## 4. 动效规范

| 元素 | 动画 | 时长 | 说明 |
|---|---|---|---|
| 极光背景 | 缓慢位移/缩放 | 12s 循环 | CSS keyframes，仅 transform/opacity |
| 卡片入场 | fade + scale | 400ms | 页面加载时轻微上浮出现 |
| 输入框 focus | border-color + box-shadow | 200ms | 清晰反馈 |
| 按钮 hover | brightness + scale | 200ms | 不阻塞交互 |
| 错误提示 | shake 或 fade-in | 200ms | 保持可见 |

**无障碍：** 必须尊重 `prefers-reduced-motion`。

---

## 5. 组件拆分

### 5.1 新增 `AuroraBackground.tsx`

职责：渲染动态极光背景 + 稀疏星光 + 扫描线。

Props：
- `reducedMotion?: boolean` — 是否禁用动画

实现方式：优先纯 CSS（多层 div + 渐变 + animation），若性能不佳再考虑 Canvas。

### 5.2 改造 `Login.tsx`

职责：保留登录逻辑，更新布局和样式。

变更点：
- 引入 `AuroraBackground`
- 替换现有 `ParticleBackground` 和 `login-grid`/`login-vignette`
- 输入框和按钮样式更新为科幻青主题
- 保持现有错误处理逻辑不变

### 5.3 样式 `global.css`

在现有 `.login-*` 类基础上扩展暗色科幻样式，不删除旧类名以便回滚。

---

## 6. 技术约束

- 继续使用 React + TypeScript + CSS 变量/类
- 不新增重量级依赖
- 登录功能、API 调用、错误提示逻辑保持不变
- 图标统一使用项目现有图标库，mockup 中的 emoji 仅作示意
- 必须支持键盘导航和 focus 可见

---

## 7. 验证清单

- [ ] 登录成功/失败功能正常
- [ ] 输入框 focus 有青色光晕
- [ ] 按钮 loading 状态正常
- [ ] 移动端 375px 显示正常
- [ ] `prefers-reduced-motion` 下背景动画停止
- [ ] 键盘 Tab 顺序合理，focus ring 可见
- [ ] `cd web && npx tsc --noEmit` 无错误
- [ ] 本地 dev 页面可正常加载

---

## 8. 回滚方案

若效果不达预期，删除/注释 `AuroraBackground` 引用并恢复旧版 `login-page` 样式即可。
