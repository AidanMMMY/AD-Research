# 中国 AI 产业链资讯源扩充候选（模型层 / 应用层 / 行业媒体）

- 日期：2026-08-04
- 目标：为关注中美 AI 全产业链投资机会的用户补上游信号 —— AI 垂直媒体、大模型厂商官方、AI 应用/Agent 社区、AI 创投媒体
- 排重依据：`/tmp/adresearch-build/existing_sources.txt`（1012 存量 slug）+ `app/services/news/sources/` 已有模块
- 实测方法：每个 RSS URL 均用 `curl -sL -o /dev/null -w "%{http_code}" --max-time 15~25` 实测，并校验返回体前 500 字符含 `<rss`/`<feed`/`<?xml`。测试环境为本地（中国大陆网络），与 Aliyun ECS 同网络类别；境外站点（github.io / medium.com / huggingface.co）间歇性不可达，已在备注标明。
- 存量已覆盖（**勿重复接入**）：机器之心、量子位、新智元、智东西、甲子光年、雷峰网、极客公园、钛媒体、爱范儿、IT之家（中/台）、cnBeta、博客园、开源中国、InfoQ（中/英）、SegmentFault、少数派、晚点LatePost、DeepTech、MIT科技评论、智能涌现、Founder Park、Z Potentials、机器之心SOTA、PaperWeekly、Datawhale、非凡产研、有新Newin、深思圈、十字路口、海外独角兽、白鲸出海、硅星人、脑极体、AI炼金术、数字生命卡兹克、歸藏的AI工具箱、硅谷101、半导体行业观察、42章经、傅盛、集智俱乐部、我爱计算机视觉、机器学习初学者、小众软件、网易科技、腾讯科技、创业邦、投资界、36氪、虎嗅、界面、财新、真格/红杉/高瓴/经纬 等
- 历史评估记录（`wechat2rss_batch3.py` 注释）：**AI科技评论**（与雷峰网同组织重复+软文多）、**硅基观察Pro**（标题党）已于 2026-07-29 评估后丢弃，本轮不再提议。

---

## 表 1：实测通过 ✅（17 个）

| source_slug（建议） | 显示名 | 站点 URL | RSS URL（已实测） | 语言 | 产业链环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| wechat_xixiaoyao | 夕小瑶科技说 | https://weixin.qq.com（公众号） | https://wechat2rss.xlab.app/feed/a1cd365aa14ed7d64cabfc8aa086da40ecaba34d.xml ✅（镜像） | 中文 | 媒体 | 深度 | AI 自媒体头部，大模型解读+论文拆解信噪比高，模型层叙事一线信号 |
| wechat_tanjiti | 碳基体 | https://weixin.qq.com（公众号） | https://wechat2rss.xlab.app/feed/4bc6a2ecb1feb2bd2961a898905147c9f76a4c3a.xml ✅（镜像） | 中文 | 媒体 | 深度 | 大模型产业观察，厂商动态与商业化分析，跟踪独角兽估值/融资叙事 |
| wechat_aliyun_dev | 阿里云开发者 | https://developer.aliyun.com | https://wechat2rss.xlab.app/feed/c74ed6db00cfbf16f2a048a165b4453f982681f0.xml ✅（镜像） | 中文 | 模型/云 | 官方 | 通义/百炼平台一手发布，阿里云 AI 收入是阿里核心估值变量 |
| wechat_alitech | 阿里技术 | https://weixin.qq.com（公众号） | https://wechat2rss.xlab.app/feed/6e1f9b775f7a5841ac1a94310f0478b45a02ec01.xml ✅（镜像） | 中文 | 模型/云 | 官方 | 阿里 AI 工程能力信号（Qwen 训练基建/推理优化），佐证云+模型叙事 |
| wechat_bytedance_tech | 字节跳动技术团队 | https://weixin.qq.com（公众号） | https://wechat2rss.xlab.app/feed/4025ea55575daf8bfd8227e68b28d9638b073267.xml ✅（镜像） | 中文 | 模型/应用 | 官方 | 豆包/扣子工程一手信号，字节 AI 投入影响算力产业链需求预期 |
| wechat_tencent_tech | 腾讯技术工程 | https://weixin.qq.com（公众号） | https://wechat2rss.xlab.app/feed/9685937b45fe9c7a526dbc32e4f24ba879a65b9a.xml ✅（镜像） | 中文 | 模型/应用 | 官方 | 混元/元宝工程信号，腾讯 AI capex 与产品化进度跟踪 |
| zhb_meituan_tech | 美团技术团队 | https://tech.meituan.com | https://tech.meituan.com/feed/ ✅（原生） | 中文 | 应用 | 官方 | 美团 AI 落地（无人配送/调度/LongCat 大模型），港股 AI 应用层标的 |
| ofc_qwen_blog | Qwen 官方博客（阿里通义） | https://qwenlm.github.io/blog/ | https://qwenlm.github.io/blog/index.xml ✅（原生，本地网络间歇不可达，ECS 需验证） | 英文 | 模型 | 官方 | 全球开源模型影响力第一梯队，每次发版直接驱动阿里 AI 叙事与算力需求 |
| global_openmmlab | OpenMMLab（商汤系开源社区） | https://openmmlab.medium.com | https://openmmlab.medium.com/feed ✅（Medium 镜像，本地网络间歇不可达） | 英文 | 模型 | 官方 | 商汤开源生态信号，计算机视觉/多模态技术趋势上游 |
| global_huggingface | Hugging Face Blog | https://huggingface.co/blog | https://huggingface.co/blog/feed.xml ✅（原生，本地网络间歇不可达） | 英文 | 模型/社区 | 官方 | 全球开源模型风向标，国产模型上榜/下载量是出海认可度硬指标 |
| global_producthunt | Product Hunt | https://www.producthunt.com | https://www.producthunt.com/feed ✅（原生） | 英文 | 应用 | 快讯 | AI 应用层新品首发阵地，国产 AI 出海产品（Agent/工具类）早期信号 |
| ofc_hellogithub | HelloGitHub 月刊 | https://hellogithub.com | https://hellogithub.com/rss ✅（原生） | 中文 | 应用/开源 | 深度 | 中文开源项目精选，AI 工具/Agent 项目早期曝光，开发者采用度信号 |
| zhb_v2ex_create | V2EX 分享创造节点 | https://www.v2ex.com/go/create | https://www.v2ex.com/feed/create.xml ✅（原生 Atom） | 中文 | 应用/社区 | 快讯 | 独立开发者 AI 产品发布一线，C 端 AI 应用萌芽期信号 |
| asen_arxiv_cscl | arXiv cs.CL（计算与语言） | https://arxiv.org/list/cs.CL/recent | https://arxiv.org/rss/cs.CL ✅（原生） | 英文 | 模型/上游论文 | 快讯 | 大模型 NLP 论文日更，跟踪国内团队（清华/智谱/阿里等）技术路线 |
| asen_arxiv_csai | arXiv cs.AI（人工智能） | https://arxiv.org/list/cs.AI/recent | https://arxiv.org/rss/cs.AI ✅（原生） | 英文 | 模型/上游论文 | 快讯 | AI 基础理论/推理/规划论文，技术拐点早期信号 |
| asen_arxiv_csro | arXiv cs.RO（机器人学） | https://arxiv.org/list/cs.RO/recent | https://arxiv.org/rss/cs.RO ✅（原生） | 英文 | 应用/具身智能 | 快讯 | 具身智能/人形机器人论文上游，映射机器人板块行情催化 |
| asen_arxiv_csma | arXiv cs.MA（多智能体系统） | https://arxiv.org/list/cs.MA/recent | https://arxiv.org/rss/cs.MA ✅（原生） | 英文 | 应用/Agent | 快讯 | 多 Agent 协作方向论文，Agent 赛道技术成熟度信号 |

> 备注：`wechat2rss.xlab.app` 镜像 feed 与存量 wechat2rss_batch 系列同一通道，集成时直接复用表驱动模式（slug/display_name/hash + batch 分组定时任务），无需新写解析器。境外源（qwen blog/medium/hf/producthunt）建议部署后先用 `verify_post_deploy` 在 ECS 上复测连通性再启用。

## 表 2：实测失败 ❌（17 个，附原因与替代建议）

| source_slug（建议） | 显示名 | 站点 URL | 实测 RSS URL 与结果 | 语言 | 产业链环节 | 内容类型 | 投资相关性与替代建议 |
|---|---|---|---|---|---|---|---|
| — | 品玩 PingWest | https://www.pingwest.com | https://www.pingwest.com/feed → 200 但返回 HTML；/rss → 404 ❌（无官方 RSS） | 中文 | 媒体 | 深度 | 硅星人母公司，AI 出海报道强；建议走公众号镜像（品玩/品玩Global） |
| — | 果壳 | https://www.guokr.com | /rss → 404；/feed → 200 但 HTML ❌（无官方 RSS） | 中文 | 媒体 | 深度 | 科学传播，AI 科普占比低，放弃 |
| — | 智源社区（BAAI） | https://hub.baai.ac.cn | /rss、/feed → 均 404 ❌（无官方 RSS） | 中文 | 模型/研究 | 深度 | 智源研究院一手内容；建议走公众号镜像（智源研究院/智源社区） |
| — | 机器之心（官网） | https://www.jiqizhixin.com | /rss → 200 但 HTML ❌（无原生 RSS）；存量 wechat_jiqizhixin 已覆盖，仅记录 | 中文 | 媒体 | 快讯 | 已覆盖，无需动作 |
| — | 猎云网 | https://www.lieyunwang.com | https/http /feed → 000 连接失败 ❌（站点不可达/无 RSS） | 中文 | 创投 | 快讯 | 创投快讯，放弃（36氪/投资界/创业邦已覆盖） |
| — | 亿欧 | https://www.iyiou.com | /rss → 202 + JS 反爬挑战 ❌（WAF 拦截） | 中文 | 创投 | 深度 | 产业数字化报道；如需可评公众号镜像（亿欧） |
| — | 凤凰网科技 | https://tech.ifeng.com | /rss/index.xml → 200 但内容为重定向残桩；/feed.shtml → HTML ❌（无 RSS） | 中文 | 媒体 | 快讯 | 综合科技快讯，信噪比一般，放弃 |
| — | 快科技 MyDrivers | https://www.mydrivers.com | /rss.aspx → 404 ❌（原生 RSS 已下线） | 中文 | 媒体 | 快讯 | 硬件快讯（GPU/算力新品），如需可评 RSSHub 自建路由 |
| — | 芯智讯 ICSmart | https://www.icsmart.cn | /feed、/rss → 403 宝塔 WAF ❌ | 中文 | 模型/算力 | 快讯 | 半导体/算力快讯质量不错；建议走公众号镜像（芯智讯） |
| — | 集微网（爱集微） | https://www.laoyaoba.com | /rss → 200 但 HTML ❌（无 RSS） | 中文 | 模型/算力 | 快讯 | 半导体产业头部媒体（国产算力链关键）；建议公众号镜像（爱集微/集微网） |
| — | EET-China 电子工程专辑 | https://www.eet-china.com | /rss → 000 连接失败 ❌ | 中文 | 模型/算力 | 深度 | 英文版 asen_eetimes 已在库，中文版放弃 |
| — | Donews | https://www.donews.com | /rss → 404 ❌ | 中文 | 媒体 | 快讯 | 站点衰落，放弃 |
| — | TechWeb | https://www.techweb.com.cn | /rss → 000 ❌ | 中文 | 媒体 | 快讯 | 放弃 |
| — | AIbase | https://www.aibase.com | /rss、/feed → 404 ❌（无 RSS） | 中文 | 媒体/聚合 | 快讯 | AI 资讯聚合站，转载为主原创少，放弃 |
| — | V2EX「AI」节点 | https://www.v2ex.com/go/ai | /feed/ai.xml → 200 但 body 为空 ❌（节点 feed 未生成内容） | 中文 | 应用/社区 | 快讯 | 用「分享创造」节点（已✅）替代 |
| — | RSSHub 公共实例（rsshub.app / rssforever / pseudoyu） | https://rsshub.app | /mydrivers、/pingwest 等路由 → 403 Cloudflare / 000 / 522 ❌（公共实例均不可用） | — | — | — | 结论：依赖公共 RSSHub 的候选一律不可接；要么 RSSHub 自建，要么走公众号镜像 |
| — | Gitee 官方博客 | https://gitee.com | /blog.rss → 404 ❌ | 中文 | 应用/开源 | 官方 | 放弃（开源中国 zhb_oschina 已覆盖同集团内容） |

> 另有 Hugging Face Papers（https://huggingface.co/papers/rss → 401 无官方 RSS），如需论文热度信号建议后续用第三方镜像或 API，本轮不接。

## 无 RSS 但建议镜像接入（公众号 wewe-rss / wechat2rss 通道）

以下均为无官方 RSS 的知名源，建议通过自建 wewe-rss（**注意：wewe-rss token 已于 2026-07-29 失效，需用户重新扫码后方可接入**）或后续 wechat2rss 镜像收录后接入。按投资相关性排序。

### 大模型厂商官方公众号（模型层一手发布）

| 显示名 | 环节 | 投资相关性 |
|---|---|---|
| 通义千问 | 模型 | 阿里 AI 叙事核心，发版/降价直接影响云计算板块预期 |
| DeepSeek | 模型 | 国产模型价格屠夫，每次发版引发算力/应用板块重估 |
| 智谱AI | 模型 | IPO 进程中的大模型第一股候选，融资/发版均为事件催化 |
| 月之暗面 Moonshot | 模型 | Kimi 用户数据与融资是 AI 应用层估值锚 |
| 腾讯混元 | 模型 | 腾讯 AI capex 与 3D/视频生成进展 |
| 文心一言（百度） | 模型 | 百度估值修复核心变量，云+模型双线信号 |
| 豆包（字节） | 模型/应用 | DAU 国内第一的 C 端 AI 应用，算力需求风向标 |
| MiniMax 稀宇科技 | 模型/出海 | 出海收入标杆，已递表港股，IPO 事件密集 |
| 阶跃星辰 | 模型 | 多模态+终端 Agent 路线，融资与车企合作催化 |
| 百川智能 | 模型 | 医疗垂直落地代表 |
| 商汤科技 SenseTime | 模型 | 港股 AI 第一股，日日新发版+生成式 AI 收入披露 |
| 科大讯飞 / 讯飞星火 | 模型 | A 股 AI 龙头，星火发版与教育/医疗订单信号 |
| 零一万物 01.AI | 模型 | 李开复系，ToB 转型与海外发布信号 |
| 面壁智能 | 模型 | 端侧小模型代表（MiniCPM），映射端侧 AI 硬件链 |
| 上海人工智能实验室 | 模型/研究 | 书生·浦语开源，国家队技术风向 |
| 华为云（盘古） | 模型/云 | 昇腾+盘古，国产算力自主化核心叙事 |
| 智源研究院 | 模型/研究 | BAAI 官方号，替代 hub.baai.ac.cn 无 RSS 的缺口 |
| 魔搭社区 ModelScope | 模型/社区 | 阿里系开源模型社区，国产模型生态活跃度指标 |

### AI 媒体 / 创投 / 应用社区公众号

| 显示名 | 环节 | 投资相关性 |
|---|---|---|
| 光锥智能 | 媒体/创投 | AI 创投报道头部，独角兽融资与商业化案例密集 |
| 拾象 | 创投/研究 | AI 投研质量天花板（海外独角兽姊妹号），一级市场定价参考 |
| 暗涌Waves（36氪旗下） | 创投 | 投资人与创业者深访，一级市场情绪与赛道轮动信号 |
| 数智前线 | 媒体 | 前 36kr 团队创立，AI 产业落地与企业级订单信号 |
| 机器之能 | 媒体 | AI 深度报道，技术产业化视角 |
| 芯东西 | 媒体/算力 | 智东西同门，AI 芯片/国产算力链核心媒体 |
| 智猩猩 | 媒体/算力 | 芯东西同门，算力公开课+芯片公司动态 |
| 爱集微 / 集微网 | 媒体/算力 | 半导体产业权威，国产替代/先进制程/存储行情上游 |
| 芯智讯 | 媒体/算力 | 半导体快讯，替代其 403 WAF 站点 |
| 投中网 | 创投 | PE/VC 行业报道，AI 赛道融资数据 |
| 线性资本 | 创投 | AI 早期基金，被投组合与技术趋势判断 |
| 奇绩创坛 | 创投/孵化 | 陆奇系，AI 早期项目批量曝光（Demo Day 信号） |
| 将门创投 | 创投 | AI 早期投资+技术社区 |
| AI产品榜 | 应用 | AI 应用流量榜单（aicpb），C 端产品景气度量化信号 |
| CVer | 应用/社区 | CV/算法求职与技术社区，大模型人才流动信号 |
| 自动驾驶之心 | 应用/智驾 | 智驾技术社区头部，NOA/端到端渗透信号 |
| 机器人大讲堂 | 应用/具身 | 机器人产业媒体，人形机器人产业链信号 |
| 具身智能之心 | 应用/具身 | 具身智能技术社区，VLA 路线进展 |
| 硅兔赛跑 | 应用/出海 | AI 出海创业观察 |
| 字母榜 | 媒体 | 大厂战略观察，AI 业务组织变动信号 |
| 中国信通院CAICT | 政策/智库 | AI 政策/标准/白皮书一手来源，监管节奏信号 |
| 未尽研究 | 研究 | 周健工主持 AI 研究 newsletter，中美 AI 对比深度分析 |
| 飞桨PaddlePaddle | 模型/开源 | 百度开源框架生态信号 |

---

## Top 20 必接优先级清单

排序依据：信噪比 + 更新频率 + 投资相关性；标注 ✅ 的 17 个为已实测可直接接入，标注【镜像】的 3 个为 wewe-rss 恢复后第一优先。

| # | 源 | 接入状态 | 理由 |
|---|---|---|---|
| 1 | DeepSeek（公众号） | 【镜像】 | 国产模型最大变量，发版即行情催化，必须一手 |
| 2 | 智谱AI（公众号） | 【镜像】 | 大模型 IPO 第一股候选，事件密集 |
| 3 | 光锥智能（公众号） | 【镜像】 | AI 创投报道头部，补一级市场盲区 |
| 4 | 夕小瑶科技说 | ✅ wechat2rss | AI 自媒体信噪比天花板，模型解读+产业分析 |
| 5 | Qwen 官方博客 | ✅ 原生 | 全球开源模型第一梯队，发版驱动阿里叙事 |
| 6 | 通义千问（公众号，见镜像节） | 镜像待 wewe-rss | 与 Qwen blog 互补的中文一手发布（若只接一个取本项） |
| 7 | 阿里云开发者 | ✅ wechat2rss | 百炼/通义平台官方，阿里 AI 收入叙事 |
| 8 | 字节跳动技术团队 | ✅ wechat2rss | 豆包/扣子工程信号，算力需求预期 |
| 9 | 碳基体 | ✅ wechat2rss | 大模型产业观察，商业化与估值叙事 |
| 10 | Hugging Face Blog | ✅ 原生 | 开源模型全球风向标，国产模型出海认可度 |
| 11 | Product Hunt | ✅ 原生 | AI 应用层新品首发，出海产品早期信号 |
| 12 | arXiv cs.CL | ✅ 原生 | 大模型论文日更，技术拐点上游 |
| 13 | arXiv cs.RO | ✅ 原生 | 具身智能/人形机器人行情上游 |
| 14 | arXiv cs.MA | ✅ 原生 | Agent 技术成熟度信号 |
| 15 | arXiv cs.AI | ✅ 原生 | AI 基础研究方向信号 |
| 16 | 美团技术团队 | ✅ 原生 | 港股 AI 应用层标的（LongCat/无人配送） |
| 17 | 腾讯技术工程 | ✅ wechat2rss | 混元/元宝工程信号 |
| 18 | 阿里技术 | ✅ wechat2rss | Qwen 训练基建佐证 |
| 19 | OpenMMLab | ✅ Medium | 商汤开源生态，多模态/CV 趋势 |
| 20 | HelloGitHub | ✅ 原生 | 中文开源 AI 项目采用度信号 |

备选（未进 Top20 但已✅）：V2EX 分享创造（#21，独立开发者产品信号，噪声略高）。

## 集成建议

1. **6 个 wechat2rss 镜像源**：按 `wechat2rss_batch.py` 表驱动模式新增 batch4（slug/display_name/hash），单 job 串行抓取+礼貌延迟，category 打 `tech`（夕小瑶/碳基体）与 `tech`（四个厂商技术号）。
2. **原生 RSS 源**：复用 `zh_blog_batch.py` / `global_rss_batch.py` 模式；arXiv 四个走 `asen_` 命名空间（英文源批次），qwen/medium/hf/producthunt 走 `global_`/`ofc_` 批次。
3. **境外源连通性**：qwenlm.github.io / medium.com / huggingface.co 在中国大陆间歇不可达，部署后必须先在 ECS 复测（`curl` 同法），不可达则改走 GitHub release/镜像或暂缓启用；producthunt.com 本次实测稳定 200。
4. **wewe-rss token 失效**是镜像节 22 个公众号（尤其 Top3：DeepSeek/智谱/光锥智能）的前置阻塞项，需用户重新扫码后接入。
5. RSSHub 公共实例已全灭（403/522/000），后续凡需 RSSHub 路由的源一律走自建实例或放弃。
