# 2026-08-21 每日研报标题四端重复修复

> 触发：用户截图实锤——/digest 页面 hero 卡标题下方，正文区又渲染一遍
> `# 2026-08-17 每日综合研报` H1；邮件同样双标题。

## 根因

标题被存了两份：`daily_digest.title` 列一份，`content_md` 开头又被
`generator.py` 拼装了 `# {title}` H1。四个消费端都先单独渲染 title、
再渲染 content_md 全文 → **网页 / 邮件 / Telegram / macOS 原生端全部双标题**。

## 修复（三处）

1. **源头去重**（`app/services/digest/generator.py`）：拼装全文不再
   prepend `# {title}`，content_md 只含 6 个 `##` 章节；标题唯一来源
   是 title 列。
   ⚠️ **暗坑**：章节数校验原来是 `content_md.count("\n## ")`——去掉 H1
   后第一节 `##` 位于文档开头、前面没有 `\n`，会少计 1 → 每篇误判
   partial。已改为行首多行正则 `_SECTION_HEADING_RE = re.compile(r"^## ",
   re.MULTILINE)` 计数，并补了防退回测试
   （`test_first_section_heading_at_doc_start_counts`）。
2. **前端防御**（`web/src/pages/Digest/index.tsx` `splitContent`）：
   intro（首个 `##` 之前）里残留的一级标题行（`#` 开头）直接丢弃，
   双保险；章节正文内的 `#` 行不受影响。函数导出供 vitest。
3. **存量清洗**（`scripts/strip_digest_title_h1.py`）：剥掉历史
   daily_digest 行开头的 H1 + 后续空行。默认 dry-run（无参数），
   `--apply` 才写。**注意**：scripts/ 不进运行时镜像（三阶段构建只拷
   app/），需 docker cp 进容器；容器名是 `alloyresearch-backend`（品牌
   改造后不是 etf-backend）。已执行（2026-08-22，20/20 行各剥 21 字符）：
   ```
   scp scripts/strip_digest_title_h1.py ad-research:/tmp/
   ssh ad-research 'docker cp /tmp/strip_digest_title_h1.py alloyresearch-backend:/tmp/ \
     && docker exec -w /app -e PYTHONPATH=/app alloyresearch-backend \
     python3 /tmp/strip_digest_title_h1.py'          # dry-run
   # 确认行数后加 --apply
   ```

邮件 / TG / 原生端零改动——数据干净后重复自然消失。已发出的邮件无法
回收，不管。

## 验证

- 后端：digest 套件 42/42，全量 pytest 1881 passed / 2 skipped，ruff 绿
- 前端：digest vitest 8/8（新增 splitContent 3 单测 + 旧数据集成回归
  「标题只显示一次」），全量 vitest 83/83，check:ci 绿
- 清洗正则用 5 个边界用例本地验证（单 H1/多 H1/无空行/无 H1/纯 H1）

## 部署+清洗执行记录（2026-08-22）

- push `477abde` → CI 门禁 → deploy 全链绿，`/health` git_sha=477abde，
  七容器正常。
- 清洗 dry-run 20/20 行命中（各剥 21 字符），`--apply` 已执行；
  全部 content_md 现以 `## 一、隔夜全球要闻` 开头。
- **排查插曲——本地 GitHub API 未认证限流 60/hr 被我自己的轮询烧光**
  （短 SHA 查 check-runs 返回空还照样计数）。口诀：轮询 check-runs
  用完整 SHA；烧光后改从 ECS 侧 `/health` git_sha 盯部署，更直接。

## 顺藤摸出的新问题：MiniMax Token Plan 额度耗尽（用户动作）

清洗时发现 8/21、8/22 两天 digest 只有 278 字符 partial——六节 LLM
调用全灭、全是占位段（8/19、8/20 还 success）。容器内 live call 实锤：

```text
RateLimitError 429 - 已达到 Token Plan 用量上限：请升级 Token Plan
套餐或购买积分补充用量。 (2056)
```

即 MiniMax token plan 额度已尽（DeepSeek 402 也未充值），**全站 LLM
当前归零**：digest/情绪/摘要/翻译全部停摆。处置：

1. 用户升级 MiniMax 套餐或买积分（或给 DeepSeek 充值回滚
   `LLM_PROVIDER=deepseek`）。
2. 额度恢复后手动补报（不影响定时任务）：
   `run_daily_digest(date(2026,8,21))` + `date(2026,8,22)`，同 8-18
   的手法（upsert + redis_lock）。
3. 待观察：这两天 429 期间翻译/全文 attempts 是否被计数（设计是
   provider_unavailable 不计数，但 429 是调用中异常，需抽查撞顶行）。

## 口诀

- **存 content 的地方别再嵌标题**——标题是元数据列，渲染端各自负责；
  在内容里再写一遍，每加一个消费端就多一处重复。
- 数 markdown 标题用行首正则，不用 `count("\n## ")`（文档开头的第一个
  标题永远数不到）。

## 相关

- [[20260818 并行大修+部署链复活]]（digest think 块修复 be2e269）
- 20260803 每日AI综合研报上线（heading 校验初版教训）
