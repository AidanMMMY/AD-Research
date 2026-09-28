# 2026-09-28 主次 LLM 自动切换链（MiniMax → GLM → Kimi）

> 触发：MiniMax token plan 周额度只够 2-3 天全站用量（8/20 耗尽后
> 全站 LLM 归零两天、digest 全降级）。用户另有 GLM / Kimi Coding
> Plan 订阅。要求：主挂了自动切下一个，plan 重置后自动切回。
> commit `3bbebc9`（未 push）。

## 一、架构

```
13 个消费方（digest/情绪/翻译/摘要/研报/AI对话…）
  → get_llm_provider()  →  FallbackProvider（同一 LLMProvider 接口）
      ├── minimax（主，token plan）
      ├── glm（兜底1，Coding Plan 订阅）
      └── kimi（兜底2，Coding Plan 订阅）
```

- 链顺序：`LLM_PROVIDER_CHAIN=minimax,glm,kimi`（默认）；旧
  `LLM_PROVIDER` 变量置首。**没配 key 的成员不进链**——链上没配
  GLM/Kimi key 时行为与改前完全一致（单 minimax）。
- 新 provider：`glm_provider.py`（默认 Coding Plan 端点
  `api/coding/paas/v4`，模型 `glm-4.6`）、`kimi_provider.py`
  （`api.moonshot.cn/v1`，`kimi-k2-0905-preview`），均可 env 覆盖。
  `strip_think_tags` 提到 `base.py` 共用；两家都不传 max_tokens
  （对齐 MiniMax/DeepSeek，防 digest 长文被默认 1024 截断）。

## 二、切换语义（关键设计决策）

| 错误 | 判定 | 行为 |
|---|---|---|
| 429 + quota 标记（2056/用量上限/quota/insufficient/balance） | 配额耗尽 | **切换** + Redis 冷却 |
| 402 余额不足 / 401 / 403 | 账单/key 失效 | **切换** + Redis 冷却 |
| 裸 429（分钟级限流） | 瞬时 | 原样抛回，调用方重试，**不切** |
| 5xx / 超时 / 断网 | 瞬时 | 原样抛回，**不切**（防备用被拖下水） |

- **冷却回主**：配额错误写 `llm:provider_down:{name}`（TTL
  `LLM_PROVIDER_COOLDOWN_SEC`，默认 6h），期间零浪费请求直走下一个；
  TTL 到期自动重试主——token plan 周期重置后无感切回。Redis 共享 =
  scheduler/celery/web 同状态；Redis 不可达降级进程内 map。
- **全链冷却中**：抛 `AllProvidersDownError`（带 429+quota 语义，
  上游分类逻辑能正确识别为配额问题走降级路径）。
- **全链无 key**：返回「AI 功能未配置」占位串（改前行为，消费方已有
  占位串特判）。
- **legacy 兼容**：默认链全没 key 时扫描所有已知 provider（只有
  DeepSeek key 的老开发机不回退）。

## 三、可观测

- `/health` → `check_llm_health()`：`chain_order` / `active_chain`
  （实际进链成员）/ `cooling_down` / `last_used_provider` /
  各家 `*_available`
- 每次切换 WARNING 日志（含原错误）；可接 site_watchdog

## 四、ECS 上线步骤

1. push 部署（等用户指令）
2. ECS `.env` 加：`GLM_API_KEY=`、`KIMI_API_KEY=`（用户从各自平台
   取；Coding Plan key 即可，GLM_BASE_URL/KIMI_BASE_URL 留空用默认）
3. 重建 backend 容器（redeploy.sh），`/health` 确认
   `active_chain: ["minimax","glm","kimi"]`
4. 验证切换：可临时把 GLM key 改错触发 401 → 看日志 failover +
   `cooling_down`；或等下次 MiniMax 自然耗尽观察
5. 若 GLM 按量付费 key（非 Coding Plan），`GLM_BASE_URL` 需改
   `https://open.bigmodel.cn/api/paas/v4`

## 五、口诀

1. **切换只认确定性配额错**（429+标记/402/401/403）；瞬时故障
   原样抛，别替调用方做决定。
2. **冷却写 Redis 不写 DB**——要的是 TTL 自动回主，不是永久黑名单。
3. **新 provider 三件套**：不传 max_tokens、剥 think 块、keyless
   返回占位串而非 raise（消费方靠占位串特判降级）。
4. 加新成员 = 写 provider 类 + 注册 `_PROVIDER_CLASSES` +
   `LLM_PROVIDER_CHAIN` 加名字，消费方永远零改动。

测试：`app/tests/test_llm_fallback.py` 20 用例；全量 1912 过。
相关：[[20260825 重要性门 token 治理]]（砍量 85%，与本链互补：
一个省 token、一个保可用性）、[[20260821 MiniMax 耗尽始末]]
