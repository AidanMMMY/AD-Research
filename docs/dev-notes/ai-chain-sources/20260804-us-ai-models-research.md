# 2026-08-04 美国 AI 产业链（模型层/研究层/VC 视角）资讯源搜罗

## 背景与方法

- 目标：为平台补充美国 AI 模型层/研究层/VC 视角上游信号源，服务中美 AI 全产业链投资研究。
- 排重基准：存量 1012 源（/tmp/adresearch-build/existing_sources.txt）。已排除 `arxiv_qfin`、`gind_lastweekai`（Last Week in AI）、`gind_lesswrong`、`indie_aisnakeoil`（AI Snake Oil）及下表"已排重"一节列出的全部存量源。
- 实测方法：每个 feed 用 `curl -sL -A "Mozilla/5.0 ..."` 实测，最多重试 3-4 次、间隔 2-3 秒（本环境有间歇性连接失败，000 一律复测确认）；判定标准 = HTTP 200 且前 500 字符含 `<rss`/`<feed`/`<?xml`。共实测 90+ 个 URL（含每个源的替代路径），下表只列最终结论。
- ✅ = 实测可抓；❌ = 多路径多 UA 重试后仍失败，注明原因。

## 排重发现（以下已在库，本批次不再重复收录）

| 存量 slug | 源 | 备注 |
|---|---|---|
| ofc_semianalysis | SemiAnalysis | AI 算力/半导体核心源，已在库 |
| gind_interconnects | Interconnects (Nathan Lambert) | 已在库 |
| indie_interconnected | Interconnected (Kevin Xu) | 已在库 |
| indie_oneusefulthing | One Useful Thing (Ethan Mollick) | 已在库 |
| indie_platformer | Platformer | 已在库 |
| indie_bigtechnology | Big Technology | 已在库 |
| indie_notboring / indie_generalist | Not Boring / The Generalist | 已在库 |
| gind_chinatalk | ChinaTalk | 已在库 |
| gind_eladgil | Elad Gil | 已在库 |
| gind_newcomer | Newcomer | 已在库 |
| gind_pragmaticengineer | Pragmatic Engineer | 已在库 |
| gind_bairblog | BAIR Blog | 已在库 |
| global_apple_ml | Apple ML Research | 已在库 |
| global_nvidia_blog / global_nvidia_dev | NVIDIA Blog | 已在库 |
| asen_thedecoder / asen_venturebeat | The Decoder / VentureBeat | 已在库 |
| ofc_techcrunch / global_theverge / global_arstechnica / global_technologyreview | 四大科技媒体 | 存量为全站 feed；下表中 AI 栏目精确版 feed 可作升级选项 |

## 候选总表（52 个，✅ 39 / ❌ 13）

### 实验室官方（15）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_openai_news | OpenAI News | https://openai.com/news | https://openai.com/news/rss.xml ✅ | en | 实验室 | 官方发布 | OpenAI 产品/模型发布第一手信号，直接影响整个 AI 应用与算力链估值 |
| ai_anthropic_news | Anthropic News | https://www.anthropic.com/news | ❌ 无官方 RSS（/news/rss.xml、/rss.xml、/engineering/rss.xml 均 404） | en | 实验室 | 官方发布 | Anthropic 动态需靠二手源（The Information/Zvi）覆盖 |
| ai_deepmind_blog | Google DeepMind Blog | https://deepmind.google/blog | https://deepmind.google/blog/rss.xml ✅ | en | 实验室 | 官方发布 | Gemini/DeepMind 模型与科学 AI 突破，Google AI 叙事核心 |
| ai_google_research | Google Research Blog | https://research.google/blog | https://research.google/blog/rss/ ✅ | en | 实验室 | 研究博客 | Google 基础研究管线，判断其技术储备与论文→产品转化率 |
| ai_google_ai_blog | Google AI (blog.google) | https://blog.google/technology/ai/ | https://blog.google/technology/ai/rss/ ✅ | en | 实验室 | 官方发布 | Google AI 产品化落地（搜索/云/消费端），比研究博客更贴近商业化 |
| ai_meta_ai_blog | Meta AI Blog | https://ai.meta.com/blog | ❌ 无 RSS（/blog/rss/、/blog/feed/、/blog/rss.xml 均 400） | en | 实验室 | 官方发布 | Llama 开源生态动态暂无法 RSS 覆盖，靠 The Verge AI/二手源 |
| ai_msft_research | Microsoft Research Blog | https://www.microsoft.com/en-us/research/blog | https://www.microsoft.com/en-us/research/feed/ ✅ | en | 实验室 | 研究博客 | 微软研究院+Phi 小模型动向，判断 MSFT AI 自研 vs OpenAI 依赖度 |
| ai_xai_news | xAI News | https://x.ai/news | ❌ 403 Cloudflare（/news/rss.xml、/feed.xml） | en | 实验室 | 官方发布 | xAI/Grok 无 RSS 且反爬，靠新闻聚合覆盖 |
| ai_mistral_news | Mistral AI News | https://mistral.ai/news | ❌ 404/无 RSS（多条路径均失败） | en | 实验室 | 官方发布 | Mistral（欧洲开源旗舰）需二手覆盖 |
| ai_cohere_blog | Cohere Blog | https://cohere.com/blog | ❌ 无 RSS（/blog/rss.xml 返回 HTML 页） | en | 实验室 | 官方发布 | Cohere 企业级 LLM 动态需二手覆盖 |
| ai_ai21_blog | AI21 Labs Blog | https://www.ai21.com/blog | ❌ 无 RSS（/feed/ 返回 HTML 页） | en | 实验室 | 官方发布 | AI21 动态需二手覆盖 |
| ai_amazon_science | Amazon Science | https://www.amazon.science | https://www.amazon.science/index.rss ✅ | en | 实验室 | 研究博客 | Amazon/AWS AI 研究与 Nova 模型动向，补充 AWS 自研芯片+模型叙事 |
| ai_ai2_blog | Allen Institute for AI (AI2) | https://allenai.org/blog | ❌ 403 Cloudflare（blog/rss.xml、/feed） | en | 实验室 | 研究博客 | OLMo 全开源模型动态暂无法 RSS 覆盖 |
| ai_eleutherai | EleutherAI Blog | https://blog.eleuther.ai | https://blog.eleuther.ai/index.xml ✅ | en | 实验室 | 研究博客 | 开源模型/可解释性研究前沿，开源生态健康度指标 |
| ai_databricks_blog | Databricks Blog | https://www.databricks.com/blog | https://www.databricks.com/feed ✅ | en | 实验室 | 企业技术博客 | DBRX/MosaicML 及企业数据+AI 平台化趋势，数据层投资信号 |

### 研究通讯（10）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_importai | Import AI (Jack Clark) | https://importai.substack.com | https://importai.substack.com/feed ✅ | en | 研究通讯 | 周刊·深度分析 | Anthropic 联合创始人亲写，前沿研究+政策+算力经济学解读，模型层最高质量单作者通讯之一 |
| ai_thesequence | The Sequence | https://thesequence.substack.com | https://thesequence.substack.com/feed ✅ | en | 研究通讯 | 日更·研究解读 | ML 研究/工程双栏目日更，快速跟踪论文产业化的执行层信号 |
| ai_bensbites | Ben's Bites | https://bensbites.com | https://bensbites.com/feed ✅ | en | 研究通讯 | 日更·AI 商业快讯 | AI 产品/融资/发布日更聚合，捕捉应用层早期公司信号 |
| ai_tldr_ai | TLDR AI | https://tldr.tech/ai | https://tldr.tech/api/rss/ai ✅ | en | 研究通讯 | 日更·摘要聚合 | 5 分钟日更头条，覆盖面广，适合作为新闻层兜底源 |
| ai_rundown_ai | The Rundown AI | https://www.therundown.ai | ❌ 403/404（/rss、/feed、/feed.xml 均被 CF 拦截） | en | 研究通讯 | 日更·聚合 | 流量大但无可用 feed，放弃 |
| ai_aheadofai | Ahead of AI (Sebastian Raschka) | https://magazine.sebastianraschka.com | https://magazine.sebastianraschka.com/feed ✅ | en | 研究通讯 | 月刊·技术深度 | LLM 架构/训练细节最扎实的技术月刊，判断技术路线可行性的专业视角 |
| ai_thegradient | The Gradient | https://thegradient.pub | https://thegradient.pub/rss/ ✅ | en | 研究通讯 | 长文·学术评论 | 学术界对 AI 趋势的长篇批判/综述，对冲炒作叙事的冷静视角 |
| ai_stanford_hai | Stanford HAI News | https://hai.stanford.edu/news | ❌ 无 RSS（/rss.xml、/news/rss.xml、/feed 均返回 HTML） | en | 研究通讯 | 研究院动态 | AI Index 报告发布方，无 feed 靠年度手动跟踪 |
| ai_mitnews_ai | MIT News - AI | https://news.mit.edu/topic/artificial-intelligence2 | https://news.mit.edu/rss/topic/artificial-intelligence2 ✅ | en | 研究通讯 | 学术新闻 | MIT 实验室成果官方报道，学术→产业转化的早期信号 |
| ai_deeplearning_batch | The Batch (DeepLearning.AI) | https://www.deeplearning.ai/the-batch/ | ❌ 404（/feed/、/the-batch/feed/、/rss.xml 均无） | en | 研究通讯 | 周刊 | Andrew Ng 周刊无公开 feed，放弃 |

### 论文（5）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_arxiv_csai | arXiv cs.AI | https://arxiv.org/list/cs.AI/recent | https://arxiv.org/rss/cs.AI ✅ | en | 论文 | 日更·新文摘要 | AI 基础方法论文日更，技术趋势最上游信号 |
| ai_arxiv_cslg | arXiv cs.LG | https://arxiv.org/list/cs.LG/recent | https://arxiv.org/rss/cs.LG ✅ | en | 论文 | 日更·新文摘要 | ML 核心理论/训练方法，判断技术代际更替 |
| ai_arxiv_cscl | arXiv cs.CL | https://arxiv.org/list/cs.CL/recent | https://arxiv.org/rss/cs.CL ✅ | en | 论文 | 日更·新文摘要 | LLM/NLP 主战场，模型能力进展最直接的论文流 |
| ai_arxiv_cscv | arXiv cs.CV | https://arxiv.org/list/cs.CV/recent | https://arxiv.org/rss/cs.CV ✅ | en | 论文 | 日更·新文摘要 | 视觉/多模态/世界模型进展，关联自动驾驶与机器人链 |
| ai_arxiv_csma | arXiv cs.MA | https://arxiv.org/list/cs.MA/recent | https://arxiv.org/rss/cs.MA ✅ | en | 论文 | 日更·新文摘要 | 多智能体系统，Agent 商业化叙事的技术验证源 |

### 社区（8）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_huggingface_blog | Hugging Face Blog | https://huggingface.co/blog | https://huggingface.co/blog/feed.xml ✅ | en | 社区 | 官方博客 | 开源模型生态中枢，开源 vs 闭源竞争格局的晴雨表 |
| ai_latentspace | Latent Space (swyx & Alessio) | https://www.latent.space | https://www.latent.space/feed ✅ | en | 社区 | 博客+播客文字稿 | AI 工程师社区核心媒体，Agent/推理 infra 趋势与 AIE 大会生态信号 |
| ai_swyx | swyx (Shawn Wang) | https://www.swyx.io | https://www.swyx.io/rss.xml ✅ | en | 社区 | 个人博客 | "AI Engineer" 概念提出者，应用工程层趋势判断 |
| ai_thezvi | Don't Worry About the Vase (Zvi) | https://thezvi.substack.com | https://thezvi.substack.com/feed ✅ | en | 社区 | 周刊·全景评论 | 每周 AI 全景扫描（含市场/政策/能力进展），信息密度最高的二手整合源 |
| ai_dwarkesh | Dwarkesh Podcast | https://www.dwarkesh.com | https://www.dwarkesh.com/feed ✅ | en | 社区 | 播客·深度访谈 | 前沿实验室 CEO/核心研究者长访谈，管理层思路与算力规划的一手口径 |
| ai_simonwillison | Simon Willison's Weblog | https://simonwillison.net | https://simonwillison.net/atom/everything/ ✅ | en | 社区 | 个人博客·日更 | LLM 工具链最快的手测点评，新模型发布小时级实测反馈 |
| ai_chiphuyen | Chip Huyen Blog | https://huyenchip.com | https://huyenchip.com/feed.xml ✅ | en | 社区 | 个人博客·长文 | ML 系统设计/AI 工程落地权威，企业 AI 采纳节奏判断 |
| ai_lilianweng | Lil'Log (Lilian Weng) | https://lilianweng.github.io | https://lilianweng.github.io/index.xml ✅ | en | 社区 | 个人博客·深度综述 | 前 OpenAI 安全负责人，Agent/推理方向权威综述，更新少但篇篇重磅 |

### VC 与产业分析（8）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_a16z | a16z | https://a16z.com | ❌ 无 RSS（/feed/、/feed、/feed.xml、a16zcrypto.com/feed 均 404） | en | VC | 机构观点 | a16z 已全面下线 RSS，靠其 Substack 系作者或二手引用 |
| ai_sequoia | Sequoia Capital | https://www.sequoiacap.com | https://www.sequoiacap.com/feed/ ✅ | en | VC | 机构观点 | Sequoia 的 AI 投资 thesis（如 AI Ascent 内容），顶级 VC 风向标 |
| ai_bvp_atlas | Bessemer (Atlas) | https://www.bvp.com/atlas | ❌ 404（/feed、/atlas/feed、/rss） | en | VC | 机构观点 | BVP 无公开 feed，Cloud/AI 报告靠手动跟踪 |
| ai_epoch_ai | Epoch AI (Gradient Updates) | https://epoch.ai | https://epochai.substack.com/feed ✅ | en | VC/研究 | 数据研究通讯 | 算力/训练成本/模型规模趋势最权威数据源，AI capex 与算力链投资必读 |
| ai_exponentialview | Exponential View (Azeem Azhar) | https://www.exponentialview.co | https://www.exponentialview.co/feed ✅ | en | VC/评论 | 周刊·宏观分析 | AI 与能源/经济/地缘交叉的宏观框架，产业链顶层叙事 |
| ai_usv | Union Square Ventures | https://www.usv.com | https://www.usv.com/feed ✅ | en | VC | 机构博客 | 老牌 VC 对 AI 应用层/网络的早期判断，更新频率低 |
| ai_cerebralvalley | Cerebral Valley | https://cerebralvalley.substack.com | https://cerebralvalley.substack.com/feed ✅ | en | VC/社区 | 周刊·生态报道 | 旧金山 AI 创业生态一线报道（融资/产品/聚会），早期项目发现源 |
| ai_greylock | Greylock | https://greylock.com | ❌ /feed/ 返回 HTML | en | VC | 机构观点 | 无公开 feed，放弃 |

### 深度评论与媒体（6）

| source_slug | 显示名 | 站点 URL | RSS URL（实测） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ai_stratechery | Stratechery (Ben Thompson) | https://stratechery.com | https://stratechery.com/feed/ ✅ | en | 评论 | 付费周刊·战略分析 | 科技战略分析标杆，大厂 AI 竞争/商业模式判断框架，投资决策高层输入 |
| ai_theinformation | The Information | https://www.theinformation.com | https://www.theinformation.com/feed ✅ | en | 评论 | 付费科技媒体 | AI 融资/人事/算力交易爆料最强媒体，标题层免费可抓、正文付费 |
| ai_techcrunch_ai | TechCrunch AI 栏目 | https://techcrunch.com/category/artificial-intelligence/ | https://techcrunch.com/category/artificial-intelligence/feed/ ✅ | en | 评论 | 科技媒体·AI 栏目 | 融资/发布快讯主力；注意存量 ofc_techcrunch 为全站 feed，二选一（建议升级为此栏目版） |
| ai_theverge_ai | The Verge AI 栏目 | https://www.theverge.com/ai-artificial-intelligence | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml ✅ | en | 评论 | 科技媒体·AI 栏目 | 消费级 AI 产品动态最快；存量 global_theverge 为全站 feed，二选一 |
| ai_arstechnica_ai | Ars Technica AI 栏目 | https://arstechnica.com/ai/ | https://arstechnica.com/ai/feed/ ✅ | en | 评论 | 科技媒体·AI 栏目 | 技术向深度报道+政策法律跟踪；存量 global_arstechnica 为全站 feed，二选一 |
| ai_mittr_ai | MIT Technology Review - AI | https://www.technologyreview.com/topic/artificial-intelligence/ | https://www.technologyreview.com/topic/artificial-intelligence/feed ✅ | en | 评论 | 科技媒体·AI 栏目 | 技术成熟度与监管的冷静报道；存量 global_technologyreview 为全站 feed，二选一 |

## Top 20 必接（优先级排序）

1. **ai_openai_news** — OpenAI 官方发布，模型层最强单点信号
2. **ai_deepmind_blog** — Google DeepMind 官方，Gemini 进展一手口径
3. **ai_msft_research** — 微软研究院，MSFT 自研 AI 动向
4. **ai_google_research** — Google 基础研究管线
5. **ai_importai** — Jack Clark 周刊，模型层+政策+算力经济学最高质量单作者源
6. **ai_thezvi** — 每周 AI 全景扫描，含市场与政策维度的整合二手源
7. **ai_stratechery** — 大厂 AI 战略与商业模式分析标杆
8. **ai_theinformation** — AI 融资/算力交易/人事爆料最强（标题可抓）
9. **ai_epoch_ai** — 算力与训练成本数据研究，AI capex/算力链投资核心数据源
10. **ai_arxiv_cscl** — LLM 论文日更主战场
11. **ai_arxiv_cslg** — ML 方法论文日更
12. **ai_arxiv_csai** — AI 基础论文日更
13. **ai_huggingface_blog** — 开源模型生态晴雨表
14. **ai_latentspace** — AI 工程师社区与 Agent/infra 趋势
15. **ai_simonwillison** — 新模型小时级实测点评
16. **ai_aheadofai** — LLM 技术路线最扎实月刊
17. **ai_thesequence** — ML 研究/工程日更双栏目
18. **ai_sequoia** — 顶级 VC AI thesis 风向标
19. **ai_cerebralvalley** — SF AI 创业生态一线融资/项目信号
20. **ai_dwarkesh** — 前沿实验室 CEO 长访谈，管理层思路一手口径

备选梯队（第二批次）：ai_google_ai_blog、ai_amazon_science、ai_eleutherai、ai_databricks_blog、ai_exponentialview、ai_bensbites、ai_tldr_ai、ai_chiphuyen、ai_lilianweng、ai_mitnews_ai、ai_thegradient、ai_swyx、ai_usv、ai_arxiv_cscv、ai_arxiv_csma，以及四个媒体 AI 栏目版（需与存量全站 feed 二选一替换：ai_techcrunch_ai / ai_theverge_ai / ai_arstechnica_ai / ai_mittr_ai）。

## 失败源处置建议

- Anthropic / Meta AI / xAI / Mistral / Cohere / AI21 / AI2 均无可用 RSS（404 或 Cloudflare 403）。这些实验室动态可靠存量二手源覆盖：ai_thezvi、ai_theinformation、ai_simonwillison、ai_theverge_ai 都会第一时间跟进；若必须一手，后续可用网页快照/Jina 抓取方式（参考存量 investing 类源的抓取方案），不建议本批次阻塞。
- a16z / BVP / Greylock / Stanford HAI / DeepLearning.AI / Rundown AI 无公开 feed，VC 观点靠 ai_sequoia / ai_exponentialview / ai_cerebralvalley 覆盖。

## 接入注意

- arXiv 五个 feed 日更量大（cs.LG/cs.CL 每日数十篇），建议接入时配关键词过滤或低频抓取，避免新闻流被论文刷屏。
- The Information feed 正文付费，只能拿到标题+摘要，建议标记 `paywall` 供前端展示。
- Substack 系（importai/thezvi/epochai/cerebralvalley/exponentialview）feed 稳定，但注意并发抓取限流。
- 四个媒体 AI 栏目 feed 与存量全站 feed 存在内容重叠，接入前需决策替换或并存去重。
