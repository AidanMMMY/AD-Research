# 学习中心 P1：文章级收藏（稍后读）+ 已读标记（2026-08-02）

## 背景

学习中心 8-02 上线知识库 Tab 后，分析文档 §2.3 把"收藏/已读"列为 P1。
本次实现文章级、用户级两种状态：收藏（稍后读）+ 已读。

## 表结构：`user_article_state`

迁移 `x5y7z9a1b3c5`（down_revision = `w4x6y8z0a2b4`），模型
`app/models/user_article_state.py`：

| 列 | 类型 | 说明 |
|---|---|---|
| user_id | int FK → users.id CASCADE | 复合 PK 之一 |
| article_id | int FK → news_article.id CASCADE | 复合 PK 之一 |
| bookmarked_at | timestamptz NULL | NULL=未收藏；取消收藏置 NULL 不删行（保留已读） |
| read_at | timestamptz NULL | 首次已读时间；重复标记不刷新 |
| created_at / updated_at | timestamptz | server_default now() |

索引：复合 PK (user_id, article_id) + `ix_user_article_state_article_id`
（feed 按 article_id 等值 LEFT JOIN 用）。

设计决策：
- 状态不写进 `news_article`（全局共享爬虫表，行跨用户复用）。
- 用时间戳而非布尔位：收藏列表按 bookmarked_at DESC 排序，read_at
  保留"首次阅读时间"供后续行为分析。
- 取消收藏置 NULL 不删行，已读标记不被冲掉。
- 迁移往返已在本地 postgres 验证（upgrade → \d → downgrade →
  to_regclass NULL → 再 upgrade，单 head x5y7z9a1b3c5）。

## API 契约（均挂 /api/v1/learning，JWT 必登录）

- `POST /learning/articles/{id}/bookmark` → `{article_id, bookmarked, bookmarked_at}`
  切换语义；幂等性在"状态"上——响应 bookmarked 恒等于调用后真实状态。
  文章不存在 404。
- `POST /learning/articles/{id}/read` → `{article_id, read: true, read_at}`
  幂等；重复调用不改写首次时间戳。文章不存在 404。
- `GET /learning/bookmarks?page=&page_size=` → 与 feed 同构
  `{items, page, page_size, total, total_pages}`，只含当前用户
  bookmarked_at 非空的文章，bookmarked_at DESC；meta 用 OUTER JOIN，
  未打标源文章 content_type/topic 为 null（收藏不限于打标源）。
- `GET /learning/feed` 每项追加 `bookmarked` / `read` 布尔
  （LEFT JOIN user_article_state，无状态行为 false；别的用户的状态
  不泄漏）。

## 前端交互

- `NewsCard` 新增可选 props：`showBookmark`（只在知识库语境传 true，
  /news 页不传不渲染）、`onToggleBookmark`。书签按钮在 meta 行右侧，
  已收藏实心高亮（--color-warning-bright），click stopPropagation
  不触发卡片打开。`read=true` 时标题降透明度
  （`.ad-news-card__title--read`, opacity 0.55）。
- `NewsDetailDrawer` 新增可选 `onRead`：article 由 null → 非空时
  回调一次；/news 页不传，无额外请求。
- `/learning` 新增第三个 Tab「我的收藏」（`MyBookmarks.tsx`）：
  收藏列表 + 点书签=取消收藏（乐观移除）+ 打开详情自动已读。
- 乐观更新集中在 `pages/Learning/useArticleState.ts`
  （`useArticleStateActions`）：直接改 react-query 缓存
  （`['learning-feed']` 全部 topic 变体 + `['learning-bookmarks']`），
  API 失败 invalidate 回滚。已读短路：已 read 不再发请求。

## 改动文件

后端：
- `app/models/user_article_state.py`（新）
- `alembic/versions/x5y7z9a1b3c5_add_user_article_state.py`（新）
- `alembic/env.py`（import 新模型）
- `app/api/v1/learning.py`（feed 加状态布尔 + 3 个新端点）
- `app/tests/news/test_learning_article_state.py`（新，26 测试）
- `app/tests/news/test_learning_feed.py`（_FakeUser 补 id=1）

前端：
- `web/src/types/news.ts`（NewsArticle 加可选 bookmarked/read）
- `web/src/api/learning.ts`（3 个新 API + 响应类型）
- `web/src/components/NewsCard.tsx` / `NewsCard.css`
- `web/src/components/NewsDetailDrawer.tsx`（onRead）
- `web/src/pages/Learning/KnowledgeFeed.tsx`（接线）
- `web/src/pages/Learning/MyBookmarks.tsx`（新）
- `web/src/pages/Learning/useArticleState.ts`（新）
- `web/src/pages/Learning/index.tsx`（第三个 Tab）
- `web/tests/news-card-bookmark.test.tsx`（新，5 测试）

## 测试结果

- 后端全量 `pytest app/tests`：1572 passed（含新增 26 项：模型 CRUD、
  迁移链/表结构防漂移、bookmark 切换幂等、read 幂等不刷新时间戳、
  feed 布尔标注 + 跨用户不泄漏、bookmarks 只含自己/排序/取消消失/
  未打标源可收藏/分页、未登录 401/403）。
- 前端 `npm run test`（vitest）：35 passed（含 NewsCard 5 项新测试）。
- `npm run check:ci`（stylelint + tsc + vite build）：全绿。
