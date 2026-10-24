# 挑剔用户实测生产站评审（2026-10-25）

> 视角：第一次接触 AlloyResearch 的独立评测人，对标 Linear/Stripe 级产品标准。
> 对象：https://www.alloyresearch.net 生产站，全部只读探测（curl 计时/头部/一次性失败登录）。
> 说明：原派子 agent 因工具残缺中止，本评审由主会话亲自执行全部探测。
> 关联：[可用性/UX 全面审计](20261025-usability-ux-audit.md)（代码侧 6.9/10）、[Aurora Horizon 视觉重塑](../web/src/styles/global/aurora.css)

## 总分：2.9/5（实施本报告修补后预估 3.8/5，安全头上线后 4.3/5）

一句话结论：**跳转与静态资源工程纪律是 A 级，品牌呈现与安全头是不及格项**——像一个引擎精心调校但没装车标的跑车。

## 实测明细

| # | 维度 | 评分 | 实测证据 | 对标差距 |
|---|---|---|---|---|
| 1 | 跳转链 | 5/5 | `http://`→`https://www`、裸域→www 全部 301 单跳直达 200 | Linear/Stripe 同级 |
| 2 | 首页元信息 | 1/5 → **已修** | 零 description/OG/theme-color；`/favicon.ico` 是 **0 字节空文件**；`/favicon.svg`、`/apple-touch-icon.png`、`/manifest.json` 返回 1065B 的 SPA 兜底 HTML（假 200） | Stripe 有完整 OG 卡片；本项目分享到任何 IM 都是无图标无摘要的白卡 |
| 3 | 静态资源 | 4/5 | `cache-control: public, max-age=31536000, immutable` + ETag + gzip ✅ | 缺 brotli（nginx 模块层面） |
| 4 | TTFB | 3/5 | 5 连测 0.67–0.71s，抖动极小 | 海外/本机视角可接受；Stripe ≈0.1–0.3s。大陆用户视角未测（ECS 出口线路决定） |
| 5 | 安全响应头 | 1/5 | 无 HSTS、无 X-Frame-Options、无 X-Content-Type-Options、无 Referrer-Policy、无 CSP | Stripe/Linear 四件套齐备 |
| 6 | 登录错误文案 | 3/5 | 401 `{"detail":"Invalid credentials"}`——语义正确但英文生硬；未认证 API 403 正确 | 中文产品的第一句人机对话应说中文、且不指责用户 |
| 7 | SPA 404 | 3/5 | `/no-such-page` → 200 + SPA 壳（由前端 404 路由接管，可接受） | 需确认前端 404 页存在且有回首页出口 |
| 8 | 新用户视角 | 2/5 | 注册关闭（已知项：待 SMTP 后开放）；忘记密码入口本轮已从「联系管理员」改为邮箱自助重置 | 挑剔用户会问：这产品给谁用？为什么值得注册？登录页需要一句价值主张 |

## 最伤体验 Top5（按伤害排序）

1. **安全头全缺**——点击劫持/嗅探防御为零（nginx 四件套草案见附录，待批准部署）
2. **品牌呈现缺失**（✅ 已实施：favicon 三件 + meta/OG 全套）
3. **登录错误英文生硬**——待办，需与认证域联动的 detail 中文化
4. **og:image 缺失**——待办：需要一张 1200×630 品牌卡（Aurora Horizon 母题正好可用）
5. **无 brotli**——nginx 层待办，文本资源再省 ~15-20%

## 已实施（本评审直接落地）

| 文件 | 改动 |
|---|---|
| `web/public/favicon.svg` | 新增：Aurora Horizon 品牌图标（深空底+熔金日弧+极光青地平线，与 Dashboard 晨昏线同母题） |
| `web/public/favicon.ico` | 替换 0 字节空文件为 16/32/48 多尺寸 |
| `web/public/apple-touch-icon.png` | 新增 180px |
| `web/index.html` | description/theme-color/icon 声明/og:title/description/type/url/site_name |

## 附录：nginx 安全头草案（待用户批准后进 deploy/aliyun-ecs/nginx.conf）

```nginx
# 在 server 块（443）追加；always 保证非 2xx 也带
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
# CSP 需先盘点 inline script/style 与 API 域，二期再上，避免一刀切搞挂 SPA
# brotli（若模块可用）：brotli on; brotli_types text/css application/javascript application/json image/svg+xml;
```

## 方法备注

- TTFB 用 `curl -w time_starttransfer` 连测 5 次；失败登录仅 1 次（不存在用户名），未触限流
- `/favicon.svg` 等「假 200」判据：响应体 1065B 与 SPA index.html 一致而非对应 MIME
- 未验证项：大陆视角 TTFB、真实浏览器渲染表现（本机无截屏能力）
