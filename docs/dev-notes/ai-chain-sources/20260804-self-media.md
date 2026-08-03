# 中美 AI 全产业链自媒体资讯源搜罗（2026-08-04）

- 目标：为用户关注的中美 AI 投资机会补充自媒体深度分析源（公众号/Newsletter/播客/YouTube/知乎）
- 排重基准：`/tmp/adresearch-build/existing_sources.txt`（1012 个存量源，已逐一 grep 排重）
- 实测标准：`curl -sL --max-time 15~25`，HTTP 200 且前 500 字符含 `<rss`/`<feed`/`<?xml`
- 实测概况：RSS 类共实测约 50 个 URL，最终 38 个通过（通过率约 76%）；YouTube 18 个频道全部解析并验证通过（收录 12 个）；公众号走存量 wechat2rss 镜像通道，免测
- 已排除的存量重复（示例）：机器之心/量子位/新智元/雷峰网/智东西/甲子光年/远川/饭统戴老板/晚点LatePost/极客公园/硅星人/半导体行业观察/钛媒体/腾讯科技/网易科技/深网/脑极体/暗涌Waves/PaperWeekly/歸藏、ChinaTalk/Sinocism/Sinification/ByteByteGo/OneUsefulThing/Not Boring/Platformer/BigTechnology/Simon Willison/Ahead of AI/LastWeekinAI/Interconnects/Newcomer/AI Snake Oil、Lex Fridman/InvestLikeTheBest、晚点聊/硅谷101/张小珺/乱翻书/大小马聊科技/科技早知道/声东击西/半拿铁/面基/知行小酒馆/十字路口 等均已接入，不在本清单

## 一、英文 Newsletter / Substack（9 个，RSS 直连，全部实测✅）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL（实测） | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| gind_thegradient | The Gradient | Newsletter | RSS直连 | https://thegradient.pub/rss/ ✅ | en | 模型/研究 | 斯坦福背景 AI 研究评论，长文判断技术趋势拐点 |
| gind_stratechery | Stratechery (Ben Thompson) | Newsletter | RSS直连 | https://stratechery.com/feed/ ✅（首次429限流，复测200） | en | 综合/商业 | 科技战略分析标杆，AI 商业模式与巨头竞争格局 |
| gind_aisupremacy | AI Supremacy | Newsletter | RSS直连 | https://aisupremacy.substack.com/feed ✅ | en | 综合/创投 | AI 产业全景+投融资动态聚合，早期信号扫描 |
| gind_importai | Import AI (Jack Clark) | Newsletter | RSS直连 | https://jack-clark.net/feed/ ✅ | en | 模型/政策 | Anthropic 联创周报，前沿模型能力+监管政策信号 |
| gind_thesequence | The Sequence | Newsletter | RSS直连 | https://thesequence.substack.com/feed ✅ | en | 模型/研究 | ML 研究进展通俗化，技术路线风向标 |
| gind_latentspace | Latent Space (swyx) | Newsletter | RSS直连 | https://latent.space/feed ✅ | en | 应用/工程 | AI 工程师生态核心媒体，Agent/工具链一手动态 |
| gind_chinai | ChinAI (Jeff Ding) | Newsletter | RSS直连 | https://chinai.substack.com/feed ✅ | en | 中国AI | 中国 AI 生态英译解读，中美 AI 对比稀缺一手源 |
| gind_garymarcus | Marcus on AI (Gary Marcus) | Newsletter | RSS直连 | https://garymarcus.substack.com/feed ✅ | en | 模型/评论 | 空头视角对冲 hype，泡沫与风险评估 |
| gind_bensbites | Ben's Bites | Newsletter | RSS直连 | https://bensbites.substack.com/feed ✅（lastBuildDate 2026-08-03 仍活跃） | en | 应用/产品 | AI 产品/创业每日扫描，早期项目发现 |

## 二、AI 实验室官方博客（3 个，非自媒体但为一手信号，顺带接入，全部实测✅）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL（实测） | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| ofc_openai_blog | OpenAI Blog | 官方博客 | RSS直连 | https://openai.com/blog/rss.xml ✅ | en | 模型 | 模型发布一手源，直接驱动产业链行情 |
| ofc_google_ai_blog | Google AI Blog | 官方博客 | RSS直连 | https://blog.google/technology/ai/rss/ ✅ | en | 模型 | Google 全系 AI 发布与商业化动态 |
| ofc_deepmind_blog | Google DeepMind Blog | 官方博客 | RSS直连 | https://deepmind.google/blog/rss.xml ✅ | en | 模型/研究 | 前沿研究→应用转化信号 |

## 三、英文播客（15 个，全部经 iTunes API 确认官方 feed 后实测✅）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL（实测） | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| pod_dwarkesh | Dwarkesh Podcast | 播客 | RSS直连 | https://apple.dwarkesh-podcast.workers.dev/feed.rss ✅ | en | 模型/思想 | 深度访谈 AI 实验室领袖，判断 AGI 路线必听 |
| pod_bg2 | BG2Pod (Gerstner & Gurley) | 播客 | RSS直连 | https://anchor.fm/s/f06c2370/podcast/rss ✅ | en | 创投 | 顶级投资人谈 AI 资本开支/估值，投资信号直接 |
| pod_acquired | Acquired | 播客 | RSS直连 | https://feeds.transistor.fm/acquired ✅ | en | 综合/商业 | 科技公司深度商业史，AI 公司个案研究扎实 |
| pod_a16z | The a16z Show | 播客 | RSS直连 | https://feeds.simplecast.com/JGE3yC0V ✅ | en | 创投 | a16z 官方，AI 投资主题覆盖密度高 |
| pod_nopriors | No Priors (Conviction) | 播客 | RSS直连 | https://feeds.megaphone.fm/nopriors ✅ | en | 创投/模型 | Sarah Guo 主持，AI 创始人/研究员访谈 |
| pod_trainingdata | Training Data (Sequoia) | 播客 | RSS直连 | https://feeds.megaphone.fm/trainingdata ✅ | en | 创投 | 红杉官方，AI 投资逻辑与 portfolio 动态 |
| pod_allin | All-In Podcast | 播客 | RSS直连 | https://rss.libsyn.com/shows/254861/destinations/1928300.xml ✅ | en | 宏观/创投 | 投资人视角宏观+AI 热点，情绪与仓位风向标 |
| pod_20vc | The Twenty Minute VC | 播客 | RSS直连 | https://rss.libsyn.com/shows/61840/destinations/240976.xml ✅ | en | 创投 | VC 访谈高频，AI 赛道融资动向 |
| pod_eyeonai | Eye On A.I. (Craig Smith) | 播客 | RSS直连 | https://rss.libsyn.com/shows/123267/destinations/727317.xml ✅ | en | 模型/产业 | NYT 前记者主持，产业链高管访谈 |
| pod_aibreakdown | AI Breakdown (NLW) | 播客 | RSS直连 | https://media.rss.com/ai-breakdown/feed.xml ✅ | en | 综合 | 每日 AI 新闻+分析，信息密度高 |
| pod_mlstreettalk | Machine Learning Street Talk | 播客 | RSS直连 | https://anchor.fm/s/1e4a0eac/podcast/rss ✅ | en | 模型/研究 | 技术向长访谈，研究前沿信号 |
| pod_cognitiverev | The Cognitive Revolution | 播客 | RSS直连 | https://feeds.megaphone.fm/RINTP3108857801 ✅ | en | 应用/创投 | AI builder 访谈，应用层落地动态 |
| pod_hardfork | Hard Fork (NYT) | 播客 | RSS直连 | https://feeds.simplecast.com/6HKOhNgS ✅ | en | 综合/监管 | 主流媒体视角 AI 新闻+监管动态 |
| pod_sharptech | Sharp Tech (Ben Thompson) | 播客 | RSS直连 | https://sharptech.fm/feed/podcast ✅ | en | 综合/商业 | Stratechery 播客版，科技商业周评 |
| pod_twimlai | TWIML AI Podcast | 播客 | RSS直连 | https://twimlai.com/feed/podcast/ ✅ | en | 模型/工程 | ML 工程实践长访谈，企业落地信号 |

## 四、中文播客（3 个，全部实测✅）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL（实测） | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| pod_sdzaokafei | 声动早咖啡 | 播客 | RSS直连（喜马拉雅官方） | https://www.ximalaya.com/album/51076156.xml ✅ | zh | 综合 | 每日商业科技快讯，AI 行业动态日更覆盖 |
| pod_shangyejushi | 商业就是这样 | 播客 | RSS直连（喜马拉雅官方） | http://www.ximalaya.com/album/46587439.xml ✅ | zh | 综合/产业 | 一财出品商业深度，常覆盖 AI 公司商业模式 |
| pod_haiwaidujiaoshou | 海外独角兽 | 播客 | RSS直连（小宇宙官方 feed） | https://feed.xyzfm.space/ym6ug8jctfp8 ✅ | zh | 应用/创投 | 全球 AI 产品与创投访谈，出海+应用层信号 |

## 五、YouTube 频道（12 个，channel_id 全部解析并实测 feed 200✅）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL（实测） | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| yt_asianometry | Asianometry | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UC1LpsuAUaKoMzzJSEt5WImw ✅ | en | 半导体/算力 | 半导体产业史与制程分析，算力链投研上游 |
| yt_mooreslawisdead | Moore's Law Is Dead | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCRPdsCVuH53rcbTcEkuY4uQ ✅ | en | 半导体/算力 | GPU/晶圆代工供应链爆料，抢跑公开数据 |
| yt_twominutepapers | Two Minute Papers | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg ✅ | en | 模型/研究 | 论文速览，研究突破早期感知 |
| yt_yannickilcher | Yannic Kilcher | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew ✅ | en | 模型/研究 | 论文深读+行业评论，技术社区情绪指标 |
| yt_aiexplained | AI Explained | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw ✅ | en | 模型 | 模型能力测评与发布解读，冷静派 |
| yt_matthewberman | Matthew Berman | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCawZsQWqfGSbCI5yjkdVkTA ✅ | en | 应用/模型 | 新模型/产品实测，发布节奏跟踪 |
| yt_wesroth | Wes Roth | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCqcbQf6yw5KzRoDDcZ_wBSw ✅ | en | 综合 | AI 新闻周度整合，覆盖广 |
| yt_theaigrid | TheAIGRID | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCbY9xX3_jW5c2fjlZVBI4cg ✅ | en | 应用 | AI 工具/发布快讯，热度指标（注意 hype 过滤） |
| yt_mattvidpro | MattVidPro AI | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCXD9sGdcD3-l12dPo_PhTZQ ✅ | en | 应用 | 生成式 AI 工具实测，应用层落地信号 |
| yt_coldfusion | ColdFusion | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UC4QZ_LsYcvcq7qOsOhpAX4A ✅ | en | 综合/商业 | 科技公司纪录片式分析，叙事与风险识别 |
| yt_bloombergtech | Bloomberg Technology | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UCrM7B7SL_g1edFOnmj-SDKg ✅ | en | 综合/财经 | 主流财经媒体科技线，巨头与资本市场动态 |
| yt_hungyilee | Hung-yi Lee 李宏毅 | YouTube | RSS直连 | https://www.youtube.com/feeds/videos.xml?channel_id=UC2ggjtuuWvxrHHHiaDH1dlQ ✅ | zh | 模型/教学 | 台大李宏毅，中文圈生成式 AI 技术科普权威 |

未收录但已验证可用的备选 YT：Dwarkesh Patel（UCXl4i9dYBrFOabk0xGmbkRA，与播客重复）、ML Street Talk YT（UCMLtBahI5DMrt0NPvDSoIRQ，与播客重复）、All-In YT（UCESLZhusAkFfsNsApnjF_Cg，与播客重复）、DeepLearningAI（UCcIXc5mJsHVYTZR1maL5l9w，课程推广偏多）、Robert Miles AI Safety（UCLB7AzTwc6VFZrBsO2ucBMg，安全向）、Computerphile（UC9-y-6csu5WGm29I7JiwpnA，泛 CS）。

## 六、中文公众号（16 个，走存量 wechat2rss 镜像通道，免测；slug 为建议命名）

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL 或公众号名 | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| wechat_zimubang | 字母榜 | 公众号 | wechat2rss镜像 | 公众号「字母榜」（免测） | zh | 综合/产业 | AI 公司深度调查与巨头动态，中文 AI 叙事头部 |
| wechat_ailanmeihui | AI蓝媒汇 | 公众号 | wechat2rss镜像 | 公众号「AI蓝媒汇」（免测） | zh | 综合 | AI 行业媒体观察，舆情与风向 |
| wechat_pingwest | 品玩 | 公众号 | wechat2rss镜像 | 公众号「品玩」（免测） | zh | 综合/出海 | 全球化科技报道，中美 AI 公司双边覆盖 |
| wechat_zhinengyongxian | 智能涌现 | 公众号 | wechat2rss镜像 | 公众号「智能涌现」（免测） | zh | 应用/创投 | 36氪 AI 垂直号，创业公司+融资动态 |
| wechat_guangzhui | 光锥智能 | 公众号 | wechat2rss镜像 | 公众号「光锥智能」（免测） | zh | 应用/产业 | AI 落地与商业化深度分析 |
| wechat_shuzhiqianxian | 数智前线 | 公众号 | wechat2rss镜像 | 公众号「数智前线」（免测） | zh | 应用/产业 | 企业数字化+AI 落地案例，B 端需求信号 |
| wechat_dianchang | 电厂 | 公众号 | wechat2rss镜像 | 公众号「电厂」（免测） | zh | 综合/产业 | 科技产业深度报道，AI 公司调查 |
| wechat_jiqizhineng | 机器之能 | 公众号 | wechat2rss镜像 | 公众号「机器之能」（免测） | zh | 模型/研究 | 老牌 AI 媒体，研究解读与产业分析 |
| wechat_xinsixiang | 芯思想 | 公众号 | wechat2rss镜像 | 公众号「芯思想」（免测） | zh | 半导体 | 半导体产业深度，国产替代+供应链信号 |
| wechat_xinshiye | 芯师爷 | 公众号 | wechat2rss镜像 | 公众号「芯师爷」（免测） | zh | 半导体 | 芯片产业链公司动态，标的挖掘上游 |
| wechat_jiweinet | 集微网 | 公众号 | wechat2rss镜像 | 公众号「集微网」（免测） | zh | 半导体 | 半导体行业新闻全覆盖，政策+产能数据 |
| wechat_bdctzongheng | 半导体产业纵横 | 公众号 | wechat2rss镜像 | 公众号「半导体产业纵横」（免测） | zh | 半导体 | 产业趋势长文，算力链景气度跟踪 |
| wechat_touzhongwang | 投中网 | 公众号 | wechat2rss镜像 | 公众号「投中网」（免测） | zh | 创投 | PE/VC 行业报道，AI 融资与退出动态 |
| wechat_dsstziben | 东四十条资本 | 公众号 | wechat2rss镜像 | 公众号「东四十条资本」（免测） | zh | 创投 | 一级市场深度，AI 独角兽个案研究 |
| wechat_alphagongchang | 阿尔法工场 | 公众号 | wechat2rss镜像 | 公众号「阿尔法工场」（免测） | zh | 投资/二级 | 二级市场研究，AI 标的深度覆盖 |
| wechat_jinduan | 锦缎 | 公众号 | wechat2rss镜像 | 公众号「锦缎」（免测） | zh | 投资/产业 | 产业与公司研究，AI 相关标的分析 |

## 七、知乎专栏（2 个，备选-需镜像）

公共 RSSHub（rsshub.app）实测 403（官方已限制生产使用），需自建 RSSHub 或等效镜像后方可接入：

| source_slug | 显示名 | 类型 | 接入通道 | Feed URL 或专栏名 | 语言 | 环节 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| zhihu_jizhiplatform | 极市平台 | 知乎专栏 | RSSHub自建（/zhihu/zhuanlan/） | 备选-需镜像 | zh | 模型/应用 | CV/AI 工程实践内容，技术落地信号 |
| zhihu_cvlife | 计算机视觉life | 知乎专栏 | RSSHub自建（/zhihu/zhuanlan/） | 备选-需镜像 | zh | 模型/应用 | 视觉+多模态技术社区，人才与技术风向 |

X(Twitter) 说明：无可靠公共镜像通道；如自建 RSSHub+token 可建「AI 研究员/AI 投资人」列表（/twitter/list/ 路由），列为后续备选，本批不计入。

## 实测未通过（❌，不收录）

| 名称 | URL | 结果 |
|---|---|---|
| The Batch (DeepLearning.AI) | https://www.deeplearning.ai/the-batch/feed/ + /rss.xml | 404 ❌ |
| AlphaSignal | alphasignal.ai/feed + alphasignal.beehiiv.com/feed | 404 ❌ |
| The Rundown AI | therundown.beehiiv.com/feed + therundownai.beehiiv.com/feed + therundown.ai/feed | 404 ❌ |
| Superhuman / Mindstream | *.beehiiv.com/feed | 404 ❌（子域不对，未深究） |
| TLDR AI | https://tldr.tech/ai/feed | 404 ❌ |
| Anthropic Blog | anthropic.com/rss.xml + /news/rss.xml | 404 ❌（官方未提供 RSS） |
| Stratechery（首测） | stratechery.com/feed/ | 429 限流，复测 200 ✅ 已收录 |

## Top 20 必接（优先级排序）

| # | source_slug | 显示名 | 理由一句话 |
|---|---|---|---|
| 1 | gind_stratechery | Stratechery | AI 商业模式与巨头竞争的全球基准分析 |
| 2 | gind_chinai | ChinAI | 中美 AI 对比稀缺一手源，直接服务双边投资主题 |
| 3 | pod_bg2 | BG2Pod | 顶级买方视角谈 AI 资本开支与估值，信号最直接 |
| 4 | pod_dwarkesh | Dwarkesh Podcast | 实验室领袖长访谈，AGI 路线判断基准 |
| 5 | pod_acquired | Acquired | AI 公司深度个案研究，研究质量堪比卖方 |
| 6 | gind_importai | Import AI | Anthropic 联创视角，模型能力+政策双信号 |
| 7 | gind_latentspace | Latent Space | Agent/工具链一手动态，应用层投资上游 |
| 8 | pod_nopriors | No Priors | AI 创始人/研究员高密度访谈 |
| 9 | pod_trainingdata | Training Data (Sequoia) | 红杉 AI 投资逻辑与赛道判断 |
| 10 | pod_a16z | The a16z Show | a16z 官方，AI 主题覆盖密度最高的大所 |
| 11 | yt_asianometry | Asianometry | 半导体/算力链深度，中文创作者英文输出稀缺视角 |
| 12 | yt_mooreslawisdead | Moore's Law Is Dead | GPU/代工供应链爆料，抢跑公开披露 |
| 13 | wechat_xinsixiang | 芯思想 | 国产半导体深度，替代逻辑上游信号 |
| 14 | wechat_jiweinet | 集微网 | 半导体全行业新闻覆盖，景气度数据 |
| 15 | wechat_zimubang | 字母榜 | 中文 AI 公司调查报道头部 |
| 16 | wechat_zhinengyongxian | 智能涌现 | 36氪 AI 垂直，创业+融资动态 |
| 17 | wechat_touzhongwang | 投中网 | AI 一级市场融资与退出 |
| 18 | wechat_dsstziben | 东四十条资本 | AI 独角兽个案深度 |
| 19 | pod_sdzaokafei | 声动早咖啡 | 中文日更商业科技快讯，低成本日频覆盖 |
| 20 | gind_garymarcus | Marcus on AI | 空头视角对冲，泡沫风险预警 |

备选梯队：gind_thegradient、yt_aiexplained、wechat_pingwest、wechat_alphagongchang、wechat_jinduan、pod_eyeonai、pod_cognitiverev、ofc_openai_blog。

## 接入备注

1. 公众号 16 个走现有 wechat2rss 镜像批次流程（同前三批），slug 建议命名如上，接入前先按「接号前先 grep 查重」口诀复核 wechat2rss 后台已有号。
2. RSS 直连 41 个（newsletter 9 + 官方博客 3 + 播客 18 + YouTube 12，其中 Dwarkesh/MLST/All-In 播客与 YT 重复内容只接播客版）直接进 RSS 采集队列。
3. 知乎/X 类需自建 RSSHub，暂缓，列后续批次。
4. 采集端注意：podcast feed 正文是 shownotes（信息量低），建议这类源只取标题+链接入库，正文走摘要即可；YouTube feed 同理（description 在 entry 内）。
