# iOS 原生 APP 可行性评估报告

> 2026-06-28 | 基于当前投研平台代码架构
>
> 最后核实更新：2026-07-21（后端认证/SSE/APNs/CORS 等"需改造"项多数已落地，见正文标注；iOS 工程已开工，位于 `ios/ADResearch/`，目前完成登录脚手架）

## 一、结论总览

| 问题 | 结论 |
|---|---|
| 是否可行？ | ✅ 完全可行 |
| 能否共用底座？ | ✅ 可以，iOS APP 直接调用现有 FastAPI REST API |
| 功能能否同步？ | ✅ 后端功能天然同步；UI/交互需要两端分别实现 |
| 工作量？ | iOS 原生开发 ≈ 重写整个前端；后端仅需小改 |

## 二、当前架构对 iOS APP 的友好度

### 后端（FastAPI）—— 很适合做底座

| 维度 | 现状 | iOS 适配度 |
|---|---|---|
| API 组织 | `/api/v1/` 下 40+ 个模块，RESTful | ⭐⭐⭐⭐⭐ |
| 数据模型 | SQLAlchemy + Pydantic Schema 完整 | ⭐⭐⭐⭐⭐ |
| 认证 | JWT Bearer + Refresh Token（30 天，rotation）+ 登出黑名单 + 设备管理（`app/api/v1/auth.py`，2026-07 已实现） | ⭐⭐⭐⭐ 已增强 |
| 实时通信 | SSE 已上线：`GET /api/v1/stream/prices?codes=...`（`app/api/v1/stream.py`，3s 推送） | ⭐⭐⭐⭐ 已实现 |
| 移动端推送 | APNs 已集成（`app/services/push_service.py`，需配置 `APNS_*` 环境变量） | ⭐⭐⭐ 已具备基础 |
| 报告导出 | HTML/Markdown 下载成熟 | ⭐⭐⭐⭐ 可扩展 PDF |

### 前端（React）—— 无法直接复用

| 维度 | 现状 | iOS 适配度 |
|---|---|---|
| 业务 API 封装 | `web/src/api/*.ts` 20 个模块集中 | ⭐⭐⭐⭐⭐ 可作为 Swift 接口参考 |
| 状态管理 | zustand + localStorage | ❌ 需改为 Swift Observable + Keychain |
| 数据获取 | React Query 79 处调用 | ❌ 需全部重写为 Combine/AsyncAwait |
| 图表 | ECharts + LightweightCharts | ❌ 需用 Swift Charts / DGCharts / TradingView |
| 响应式 | 刚做完移动端适配 | ✅ 设计稿可直接参考 |

## 三、三个实现方案对比

### 方案 A：原生 SwiftUI/UIKit iOS APP（体验最好，成本最高）

**改造内容：**
- iOS 端：完全重写，约 **22 个页面 × 平均 2-3 天 = 2-3 个月**
- 后端：认证增强（Refresh Token）、APNs 推送、实时行情 SSE/WebSocket
- 图表：Swift Charts（系统）+ DGCharts / TradingView Lightweight Charts

**适合：** 追求极致体验、有独立 iOS 团队、预算充足

**工作量估算：**

| 模块 | 人天 |
|---|---|
| iOS 工程搭建 + 网络层 + Keychain | 5-7 |
| 登录/认证/用户体系 | 3-5 |
| 首页 Dashboard + 统计卡片 | 5-7 |
| 标的列表/详情/K线 | 10-14 |
| 标的池管理（最复杂） | 10-12 |
| 筛选器/评分/报告 | 8-10 |
| 回测/策略/信号 | 8-10 |
| AI 聊天/研究笔记/情绪 | 8-10 |
| 推送/实时行情 | 5-7 |
| 测试/打磨 | 7-10 |
| **总计** | **~70-100 人天** |

### 方案 B：React Native / Flutter（成本中等，推荐）

**优势：**
- 复用现有前端团队的 React/TypeScript 能力（RN）
- 一套代码可同时覆盖 iOS + Android
- 业务逻辑（API 调用、状态管理）可高度复用
- 图表可用 WebView 嵌套 ECharts，或 native 图表库

**改造内容：**
- 将 `web/src/api/*.ts` 迁移为 RN 的 API 层
- 复用 zustand 状态管理
- React Navigation 替代 react-router
- 图表：ECharts 可用 `react-native-echarts-pro`，K线可用 `react-native-wagmi-charts`

**工作量估算：** 约 **40-60 人天**（比纯原生少 40-50%）

### 方案 C：PWA / 继续优化 Web（成本最低）

**做法：**
- 不需要 iOS 原生开发
- 把当前 React 站点包装成 PWA，支持添加到主屏幕
- 继续优化移动端交互和性能
- 必要时用 Capacitor / Cordova 调用少量原生能力

**工作量估算：** 5-10 人天

**适合：** 快速验证、预算有限、用户粘性尚未证明

## 四、如果做原生 iOS，后端需要改造什么

### 必须做（MVP）

> 2026-07-21 核实：以下 5 项在后端均已落地（详见逐项标注）。

| 改造项 | 工作量 | 说明 |
|---|---|---|
| **Refresh Token 机制** | ✅ 已完成 | `POST /api/v1/auth/refresh`，30 天 opaque token（DB 存 SHA-256，rotation）；access token 仍为 1 天（`ACCESS_TOKEN_EXPIRE_MINUTES=1440`） |
| **Token 黑名单/登出** | ✅ 已完成 | `POST /api/v1/auth/logout`，Redis 存失效 jti |
| **设备绑定表** | ✅ 已完成 | `UserDevice` 模型 + `POST/GET/DELETE /api/v1/auth/devices` |
| **APNs 推送集成** | ✅ 已完成 | `app/services/push_service.py`（HTTP/2 API，sandbox/prod 切换） |
| **收紧 CORS** | ✅ 已完成 | 非 development 环境自动丢弃 `*`；未配置 `CORS_ORIGINS` 时不允许跨域（`app/config.py`） |

### 建议做（体验提升）

| 改造项 | 工作量 | 说明 |
|---|---|---|
| **SSE/WebSocket 行情推送** | ✅ 已完成（SSE） | `GET /api/v1/stream/prices?codes=...`，3s 间隔，5 分钟连接上限 |
| **API 分页统一** | 2-3 天 | 部分接口用 `limit`，部分用 `page/page_size` |
| **PDF 报告导出** | 2-3 天 | 移动端更适合 PDF 而不是 HTML |
| **图片/缩略图 API** | 2 天 | iOS 列表页性能优化 |

## 五、功能同步策略

### 可以天然同步的（只做后端）

只要新增功能通过 API 暴露，iOS 和 Web 共用：

- 数据模型变更（新字段、新表）
- 评分算法更新
- 筛选条件增加
- 报告模板
- 回测/策略逻辑
- AI 研究笔记生成逻辑
- 通知规则

### 需要两端分别实现的（UI/交互层）

| 功能 | Web 实现 | iOS 实现 |
|---|---|---|
| K 线图 | ECharts / LightweightCharts | Swift Charts / DGCharts / TradingView |
| 相关性热力图 | ECharts Heatmap | Swift 原生或 WebView |
| 复杂表单 | Ant Design Form | SwiftUI Form / UIKit |
| 拖拽排序 | react-dnd | UIKit 拖拽 |
| 手势交互 | 鼠标 hover | 长按、滑动、捏合 |
| 推送通知 | Web Push | APNs |

### 推荐的同步流程

```
新增功能
  ├── 后端 API（共用） ← 一次开发
  ├── Web 前端实现
  └── iOS 端实现
```

**关键建议：** 把后端作为 **Single Source of Truth**，所有业务逻辑下沉到后端。前端和 iOS 只做展示和交互。

## 六、推荐方案

如果你希望**长期维护、体验最好、用户愿意付费**，推荐：

> **React Native（方案 B）> 原生 Swift（方案 A）> PWA（方案 C）**

**理由：**
1. 你们前端已经是 React，RN 学习曲线低
2. 一套代码覆盖 iOS + Android
3. API 层、状态管理、业务逻辑高度复用
4. 图表问题可用 WebView 临时解决，后续逐步替换为原生图表
5. 功能同步效率最高

**如果一定要原生 iOS**，建议先做一个 **MVP**：
- 只做：登录、标的列表、标的详情（含 K线）、收藏、首页 Dashboard
- 大约 4-6 周可上线
- 验证用户价值后再补全其他模块
