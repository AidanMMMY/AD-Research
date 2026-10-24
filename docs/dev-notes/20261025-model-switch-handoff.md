# 编码助手模型切换与会话交接 Runbook

> 日期：2026-10-25
> 适用对象：Claude Code / VSCode 中协助开发 AlloyResearch 的编码助手
> 不适用范围：平台业务侧 MiniMax→GLM→Kimi provider 链；两者不要混改配置

## 1. 为什么需要外置交接

模型标称上下文上限、宿主实际会话窗口和自动压缩触发线不是同一个概念。即使模型支持大上下文，Claude Code 也可能为系统提示、工具定义、工具结果和后续输出预留空间而提前压缩。压缩摘要是有损的工作线索，不应成为唯一事实源。

本项目按以下分层保存事实：

1. Git 工作树、commit 与测试：当前代码和可验证结果。
2. `docs/dev-notes/`：实现、排障和决策的事实源。
3. `~/Documents/AlloyResearch-KB`：runbook、口诀和长期经验的策展层。
4. 助手 memory：用户偏好与事实源指针，不替代代码和文档。

## 2. 本次切换基线

- 分支：`main`。
- 功能基线 commit：`ee22869`（首登强制改密与统一密码策略）。
- 同批已有文档 commit：`6b765a3`（知识库指针）、`d10e770`（非 Web 端与平台瘦身评估）。
- 本文件是交接索引；远端是否同步、部署是否成功，必须在新会话现场查询，不能由本文预先断言。
- 切换时先确认工作树是否干净；若有新改动，以实际 `git status` 和 `git diff` 为准，不要强行恢复到本文时点。

### 已完成的本地验证

- 后端：1951 passed，2 skipped。
- Web：本次改动文件 ESLint 零 warning；stylelint、TypeScript、Vite build 通过；19 个测试文件、96 tests 通过。
- Python：ruff、black 通过；Alembic 单一 head `b3c5d7e9f1a2`。
- 旧 iOS：standalone 认证契约/密码策略测试与全源码 `swiftc -parse` 通过。
- native：standalone 认证契约/密码策略测试、全源码 `swiftc -parse`、完整 macOS 应用源码 CLT `swiftc` 编译通过。
- 全仓 Web `npm run lint` 仍有未改动文件的既有 warning，不得宣称全仓 ESLint 已清零。

### 尚未验证或明确保留的边界

- 未做完整 `xcodebuild`、iOS SDK 编译、模拟器/真机 UI 或真实后端联调。
- 生产创建用户→登录→强制改密→新 refresh token 刷新→普通 API 恢复访问，需要部署后验收；push 不等于部署成功。
- 正常自助改密未引入 session version，其他会话已签发的旧 access token 保留既有最长 15 分钟有效期；极端并发 refresh 竞态不在本次范围。
- native 保留离线恢复策略，但普通在线 API 仍由后端 403 强制门控。
- 平台瘦身报告只是建议，未授权不得删除旧客户端、research/agent 或停止生产服务。

详细实现见 [首登强制改密与统一密码策略](20261024-first-login-password-policy.md)，范围治理见 [非 Web 端与平台瘦身综合评估](20261025-platform-slimming-review.md)。

## 3. 推荐切换步骤

1. 在任务边界切换，不在修到一半、测试失败原因未明或部署状态未知时切换。
2. 确认 commit 已包含代码、迁移、测试和 md/html 文档；记录实际 SHA，而非只记分支名。
3. 切换编码助手模型后，优先开一个干净的新会话，避免继续携带长会话和多次压缩摘要。
4. 新会话先只做现场重建和基线核对，再给小范围任务；不要一开始就让它跨模块重构。
5. 不因为换模型而重跑所有已验证工作；但如果实际代码与基线不同，必须重新验证受影响范围。

## 4. 新会话固定恢复提示

将下面整段发给新模型：

```text
你在 AlloyResearch 仓库工作。先不要修改代码，也不要 push。

请先读取：
1. AGENTS.md
2. docs/dev-notes/20261025-model-switch-handoff.md
3. docs/dev-notes/20261024-first-login-password-policy.md
4. 如任务涉及架构范围，再读 docs/dev-notes/20261025-platform-slimming-review.md
5. 排障时先查 ~/Documents/AlloyResearch-KB/20-Runbooks/_index.md 和 60-Lessons/

然后实际执行并核对 git status --short --branch、git log -5 --oneline --decorate，
必要时查看 git diff。请用中文汇报：当前真实停点、与交接文档的差异、已有验证证据、
尚未验证项和你建议的最小下一步。不要把历史摘要当成当前事实，不要声称未亲自验证的测试或部署已通过。
后续没有我的明确命令不得 push。
```

## 5. 切换后的防漂移规则

- 新模型引用文件、配置或命令前，先确认其在当前工作树存在；文档可能有时点性。
- 修改行为先补能复现问题的测试，提交前独立查看 staged diff，并运行受影响测试。
- agent 的报告只是线索，主会话必须核对 diff 和验证结果。
- 发现文档与代码冲突时，以当前代码、数据库迁移链和可复现结果为依据，同时修正文档。
- 不把一次性明文密码、真实密钥或个人凭据写进交接文档、memory、vault 或提交。
- 回滚优先针对具体 commit 做可审计的 `git revert`；不要在共享 `main` 上擅自 reset 或 force push。
