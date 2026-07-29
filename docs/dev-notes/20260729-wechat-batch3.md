# 2026-07-29 微信公众号资讯源三批（22 源，实报）runbook

> 交付：`app/services/news/sources/wechat2rss_batch3.py`（自包含模块）
> 测试：`app/tests/news/test_wechat2rss_batch3.py`（17 通过 + 6 xfail，集成后 23 全绿）
> 集成：见 `docs/dev-notes/20260729-wechat-batch3-integration.md`（主会话串行应用）
> 本批新增 **22 个**公众号源：宏观/地缘 2 / 投资策略 2 / 行业研究 5 / 科技评论 6 / 商业深度 7。
> **目标 ≥40，实收 22**——两个公共镜像经三波开采后合格池枯竭，按纪律实报不凑数（§1/§4 有完整证据）。

---

## 1. 背景与通道调研（为什么只有 22）

任务要求 ≥40 个新公众号源（中文圈扩展第三批，"有独立思考精神的内容"）。
公众号无官方 RSS，只能走公共 wechat2rss 镜像。2026-07-29 全通道复查：

| 通道 | 状态 | 结论 |
|---|---|---|
| `wechat2rss.bestblogs.dev`（BestBlogs 自建公共实例，375 号 OPML） | ✅ 活 | 一/二批已用 102；剩余 260 中 ~240 为企业开发/AI 厂商 PR/体育/生活/设计/课程营销/搬运号。**本批主通道，实收 22** |
| `wechat2rss.xlab.app`（官方公共实例，395 号） | ✅ 活 | **7-29 重新抓取全量列表（/list/all.html），与 7-27 快照逐 hash 比对：零新增**；剩余 304 号≈290 安全研究 + 企业开发 + 死号/文学。合格池 = 0 |
| 其他公共 wechat2rss 实例 | ❌ 不存在 | web 检索 + GitHub 检索确认：生态为"官方实例 + 各自自建"，无第三个公开收录列表的实例 |
| feeddd.org / werss.app / CareerEngine | ❌ 死 | 同二批调研结论 |
| 瓦斯阅读 / 今天看啥 | ⚠️ 无公开 RSS | 同二批调研结论（后者登录墙） |
| wechatrss.waytomaster.com（2026 新服务） | ⚠️ 登录墙 | 免费限 2 号，无公开源目录，feed 为用户私有 |
| RSSHub `/newrank/wechat` | ⚠️ 不稳定 | 公共实例上常年报错（RSSHub#14049），且非任务指定通道 |
| ECS wewe-rss 自建（通道 B） | ❌ 仍死 | 微信读书 token 失效，需用户重新扫码（见二批 runbook §5.3），本批未使用 |

**结论**：镜像支持的合格号就这么多。"未被镜像收录的号不要硬塞"——22 是诚实上限。
缺口 18 个的补齐路径：① wewe-rss 通道 B 恢复（用户扫码）后按二批 runbook §5.3 增补；
② 向 xlab 提交收录请求（GitHub issue，收录标准见 wechat2rss.xlab.app/list/new）；
③ 等待 BestBlogs OPML 扩列后复查。

## 2. 筛选与实测流程

1. BestBlogs OPML（375，7-29 重新下载）+ xlab 全量列表（395，7-29 抓取 `/list/all.html`）取并集。
2. 排除已覆盖：一批 90（slug/名称/hash）、二批 103（slug/名称/URL/hash）、
   `wechat_maobidao`/`wechat_sixianggangyin`/`wechat_zeping`、wewe-rss 15 号
   （智谷趋势/远川研究所/沧海一土狗/付鹏的财经世界/李迅雷金融与投资/聪明投资者/北纬的日常/
   晚点LatePost/杨国英观察/叫小宋别叫总/投资界/墨子连山/半导体行业圈/金融时报/泽平宏观）。
3. 排除与平台直连源重复的号（华尔街见闻/财新/界面/36氪/虎嗅/财联社/雪球…）。
4. 排除官媒党政、企业官方 PR（含 AI 厂商号 DeepSeek/Kimi/智谱/通义/文心/混元/MiniMax/阶跃/Seed
   与企业研究院 腾讯研究院/阿里研究院/麦肯锡）、体育、文学生活、设计、纯开发工程、
   AI 工具教程/搬运号（本轮新增排除大类，~100 个）。
5. 对候选与"名称未知"号共 45 个从 ECS 实际抓 feed 看标题样本 + pubDate + content:encoded。
6. 达标线：HTTP 200 + items>0 + 有正文 + 最新条目 ≤30 天 + 非标题党/软文密度低/非同机构重复。
   28 个进入终验，6 个淘汰（§4），最终 **22 源**。

## 3. 22 源清单（slug / 名称 / 分类 / 镜像 / 实测状态）

实测时间 2026-07-29（ECS 发起 `curl --max-time 20`）；全部 HTTP 200、10 条 item、
`content:encoded` 全文、30 天内有更新。镜像全部 = bestblogs。

| source | 名称 | 分类 | 最新文章 | 备注 |
|---|---|---|---|---|
| `wechat_diqiuzhishiju` | 地球知识局 | 宏观/地缘 | 28 Jul 2026 | 地缘经济、资源产业地理 |
| `wechat_nanfengchuang` | 南风窗 | 宏观/政经 | 29 Jul 2026 | 政经评论深度媒体 |
| `wechat_lxiansheng` | L先生说 | 投资策略 | 23 Jul 2026 | 思维方法、认知升级 |
| `wechat_xinmuweibi` | 心木微笔 | 投资策略 | 23 Jul 2026 | A股/港股投资随笔（CXO、科技板块判断） |
| `wechat_dalirushan` | 大力如山 | 行业研究 | 27 Jul 2026 | 投行/金融职场行业内幕 |
| `wechat_xingqiuyanjiusuo` | 星球研究所 | 行业研究 | 25 Jul 2026 | 能源/基建/城市产业地理（补新能源覆盖） |
| `wechat_feifanchanyan` | 非凡产研 | 行业研究 | 29 Jul 2026 | AI 产业研究（VC 研究系，同峰瑞/高瓴先例） |
| `wechat_youxiputao` | 游戏葡萄 | 行业研究 | 28 Jul 2026 | 游戏产业分析（A股传媒板块相关） |
| `wechat_houlang` | 后浪研究所 | 行业研究 | 28 Jul 2026 | 年轻人消费趋势（补消费覆盖，如老铺黄金重估） |
| `wechat_xiaozhongxiaoxi` | 小众消息 | 科技评论 | 27 Jul 2026 | 互联网/产品独立评论 |
| `wechat_zpotentials` | Z Potentials | 科技评论 | 29 Jul 2026 | AI 创业者深度访谈 |
| `wechat_wangjiwei` | 王吉伟 | 科技评论 | 29 Jul 2026 | Agentic AI / 企业智能化行业观察 |
| `wechat_kuaidaoqingyi` | 快刀青衣 | 科技评论 | 29 Jul 2026 | AI 落地独立观察（WAIC 笔记等） |
| `wechat_zhishifenzi` | 知识分子 | 科技评论 | 29 Jul 2026 | 科学政策/AI 产业评论（饶毅系，独立声音） |
| `wechat_ailianjinshu` | AI炼金术 | 科技评论 | 17 Jul 2026 | AI 行业随笔思考 |
| `wechat_guigu101` | 硅谷101 | 商业深度 | 29 Jul 2026 | 硅谷科技商业深度报道 |
| `wechat_luanfanshu` | 乱翻书 | 商业深度 | 16 Jul 2026 | 互联网公司商业分析（潘乱） |
| `wechat_nanfangzhoumo` | 南方周末 | 商业深度 | 29 Jul 2026 | 深度调查报道 |
| `wechat_sanlian` | 三联生活周刊 | 商业深度 | 29 Jul 2026 | 社会/商业深度报道 |
| `wechat_xinwenzhoukan` | 中国新闻周刊 | 商业深度 | 29 Jul 2026 | 新闻深度报道 |
| `wechat_sixiangshichang` | 澎湃思想市场 | 商业深度 | 29 Jul 2026 | 思想/社会经济评论 |
| `wechat_ssircn` | 斯坦福社会创新评论 | 商业深度 | 28 Jul 2026 | SSIR 中文版，社会创新/ESG |

批次划分（`_BATCH_SIZE = 8`）：`w3a` = 前 8（宏观 2 + 策略 2 + 行业 4），
`w3b` = 次 8（行业 1 + 科技 6 + 商业 1），`w3c` = 末 6（商业 6）。
job：`news_wechat3_w3[a-c]_60m`，每小时一批，`IntervalTrigger(minutes=60, jitter=600)` 错峰。

## 4. 淘汰记录（终验 6 + 探针 22 + xlab 10）

### 4.1 进入终验但淘汰（6）

| 名称 | 拟分类 | 镜像 | 淘汰原因 |
|---|---|---|---|
| 心智工具箱 | 投资策略 | bestblogs | 停更：最新文 2026-06-02（57 天） |
| iamsujie | 商业深度 | bestblogs | 停更：最新文 2026-06-26（33 天） |
| 语言即世界 | 科技评论 | bestblogs | 停更：最新文 2026-05-11（79 天）；内容本是优质 AI 人物访谈，可惜 |
| AI科技评论 | 科技评论 | bestblogs | 同机构重复（雷峰网子品牌，二批已收雷峰网）+ 招聘/会议软文混入 |
| 硅基观察Pro | 行业研究 | bestblogs | 标题党化（"一年暴涨100倍""美国有钱人已经先跑了"），触碰营销号红线 |
| 丁香医生 | 行业研究(医药) | bestblogs | 软文密度高（洗发水带货文等），且为消费健康科普而非医药行业研究 |

### 4.2 探针后候选阶段淘汰（22，采样标题判定）

浮之静/土猛的员外/花叔/沃垠AI/袋鼠帝AI客栈/卡尔的AI沃茨/阿真Irene/秋芝2046/小互AI/艾逗笔（AI 工具教程或实测号，搬运/营销属性）、
AGENT橘（个人杂记）、强少来了（开发周刊）、言午（AI 创业杂谈，偏工程）、AI闲谈（AI Infra 纯技术）、
罗西的思考（RL 源码笔记）、新周刊（生活方式）、利维坦（文化随笔）、AI炼金术*、心木微笔*、后浪研究所*、
知识分子*、语言即世界*（* = 探针后进入终验，见 §3/§4.1）。

### 4.3 xlab 未知号探针（10，全军覆没）

记月/灾难控制局/securitainment/Medi0cr1ty/小陈的Life/分类乐色桶/凌晨一点零三分（安全研究，off-topic 或停更）、
我需要的是坚持（个人博客，停更 2025-01）、biao（诗歌）、At The End（文学）。

### 4.4 候选阶段即排除的大类（~200）

安全研究号 ~290（xlab）、企业开发号（阿里技术/腾讯技术工程/字节技术…）、AI 厂商官方号
（DeepSeek/Kimi/智谱/通义/文心/混元/MiniMax/阶跃/字节Seed/Xiaomi MiMo/Dify/Jina AI/魔搭…）、
企业研究院 PR（腾讯研究院/阿里研究院/麦肯锡/阿里研究院）、官媒党政（人民日报/新华社/央视/环球时报/
南京发布/网信中国/公安部网安局…）、平台直连重复（华尔街见闻/财新/界面/36氪/虎嗅/财联社/雪球/凤凰网/
澎湃新闻/界面新闻）、同机构重复（高瓴时间-高瓴创投、山行AI-山行资本、晚点再听LaterCast-晚点LatePost）、
体育（苏群/杨毅/体坛周报…）、文学生活（莫言/十点读书/看理想/一条/每日豆瓣…）、设计（优设/设计癖…）、
课程营销（罗辑思维/得到/帆书/混沌学园/洞见）、聚合搬运（知乎日报/AIBase基地/AI寒武纪/大模型智能/
Web3天空之城/区块链头条/水木人工智能学堂/通往AGI之路）、心理学（武志红/KnowYourself/NOV心理）、
二批已淘汰复核（老钱说钱/孟岩/刘言飞语/43 Talks/晚点对话/科技美学/毛有话说——维持原判，未复收）。

## 5. 运维手册

### 5.1 日常健康

- 3 个 job：`news_wechat3_w3[a-c]_60m`，每小时一批（jitter 600s），健康面板"公众号三批 X 组"。
- 单源缺文排查：`SELECT * FROM etl_log WHERE job_name='news_wechat3_w3a_60m' ORDER BY start_time DESC;`

### 5.2 镜像失效

- 本批 22 源全部挂在 bestblogs 单镜像上——**单点风险高于一/二批**。
  整域失效时本批 3 个 job 会同时 failed；处置顺序：
  1. `curl -s -o /dev/null -w "%{http_code}" https://wechat2rss.bestblogs.dev/feed/<hash>.xml` 确认单 feed 还是整域；
  2. 单 feed 失效 → 从 `WECHAT3_FEEDS` 删行（批次自动收缩）；
  3. 整域失效 → 一二三四批同时受影响，按二批 runbook §5.2 统一处置。
- 爬虫失败即 WARNING + 跳过，禁止运行时重试放大。

### 5.3 缺口补齐路径（≥40 未达成的后续）

1. **wewe-rss 通道 B 恢复**（用户操作，见二批 runbook §5.3）：恢复后可增补镜像未收录的号
   （宏观私募/量化/FICC 类独立号多在镜像外）。
2. **向 xlab 提交收录**：`github.com/ttttmr/wechat2rss` issue 推荐，收录标准见其站 /list/new。
3. **BestBlogs OPML 扩列复查**：`github.com/ginobefun/BestBlogs` watch opml 目录。
4. 下轮若重启，先用本 runbook §1 的通道表快速复核，别重复调研。

### 5.4 营销过滤器

本批 job 复用 `WechatMarketingFilter`（LLM 24h 缓存）。周刊媒体号（三联/南周/新闻周刊/澎湃）
偶有推广文会被 LLM 判 `not is_knowledge` 拒掉，`rejected_marketing` 计数体现在 etl_log。
心木微笔/乱翻书等个人号误杀率应接近零；若某源误杀严重，记录后可考虑挪独立白名单 job（暂未实现）。

## 6. 决策日志

| 决策 | 理由 |
|---|---|
| 实报 22 不凑数 | 任务纪律明确；两个镜像合格池确实枯竭（§1 证据） |
| 收录深度媒体周刊（南周/三联/新闻周刊/南风窗/澎湃思想市场） | 商业/时政深度报道符合"独立思考"；非党政喉舌类官媒；先例：二批已收财经杂志/经济观察报/第一财经 |
| 收录 VC/产研号（非凡产研） | 先例：二批已收峰瑞/高瓴/经纬/真格/红杉/山行 |
| 收录游戏葡萄/后浪研究所 | 本轮任务点名补消费/此前覆盖少的领域；游戏=传媒板块、后浪=消费趋势 |
| 排除 AI 工具教程号（~20 个） | 搬运/教程/营销属性，非"独立思考的宏观/行业/商业内容"；二批已收够 AI 评论头部号 |
| 排除丁香医生 | 医药是本轮目标领域，但其为消费健康科普+软文密度高，非行业研究 |
| 批次 `_BATCH_SIZE=8`（3 批） | 22 源 ÷ ≤10/批 → 3 批；键 `w3a-w3c`，job 前缀 `wechat3_`，与一/二批命名空间隔离 |
| `WECHAT3_BATCH_JOBS` 定义在模块内 | 表与 job 元数据同源，scheduler_jobs 只 import 物化，避免两处维护漂移 |
| scheduler 用 `jitter=600` | 任务要求；也给镜像错峰减压（一/二批不 retroactive 改） |
| 保留营销过滤器 | 本批含周刊媒体号，软文概率高于独立号 |

## 7. 文件清单

| 文件 | 说明 |
|---|---|
| `app/services/news/sources/wechat2rss_batch3.py` | 22 源表 + 3 批次 + WECHAT3_BATCH_JOBS + `Wechat2RssBatch3Crawler` |
| `app/tests/news/test_wechat2rss_batch3.py` | 表完整性/格式/零重叠（含二批）/爬虫 mock/集成接线（xfail 待集成） |
| `docs/dev-notes/20260729-wechat-batch3-integration.md` | 三文件精确补丁（scheduler_jobs/scheduler/news） |
| `docs/dev-notes/20260729-wechat-batch3.md`(+`.html`) | 本 runbook |
