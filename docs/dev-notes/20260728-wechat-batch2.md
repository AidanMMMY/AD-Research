# 2026-07-28 微信公众号资讯源二批（103 源）runbook

> 交付：`app/services/news/sources/wechat2rss_batch2.py`（自包含模块）
> 测试：`app/tests/news/test_wechat2rss_batch2.py`（14 通过 + 13 xfail，集成后 27 全绿）
> 集成：见 `docs/dev-notes/20260728-wechat-batch2-integration.md`（主会话串行应用）
> 本批新增 **103 个**公众号源：宏观经济 26 / 投资策略 22 / 行业研究 14 / 科技评论 29 / 商业深度 12。

---

## 1. 背景与通道调研（为什么有两个镜像）

任务要求 ≥100 个新公众号源，聚焦宏观/策略/行业/科技/商业，剔除营销号、标题党、软文号。
候选通道逐一实测（全部从 ECS 验证）：

| 通道 | 状态 | 结论 |
|---|---|---|
| `wechat2rss.xlab.app`（一批同款公共镜像） | ✅ 活 | 全站仅 395 号、326 个安全类；一批已用 90+2，剩余合格号 ≤5，**不够** |
| `wechat2rss.bestblogs.dev`（BestBlogs 自建公共实例） | ✅ 活 | **375 号，财经/商业/科技为主，本批主通道（102 源）** |
| ECS wewe-rss 自建（通道 B） | ❌ 暂死 | 微信读书 token 失效（WeReadError401/-2041），`platform.getMpInfo` 报"暂无可用读书账号"。需用户重新扫码才能订阅新号，本批未使用 |
| feeddd.org | ❌ 死 | 域名已停靠（跳转 ww1.feeddd.org） |
| werss.app | ❌ 死 | 只剩 SPA 壳，API 全返回 HTML |
| CareerEngine（posts.careerengine.us） | ❌ 死 | 已改版 Next.js 北美生活站，`/author/{id}/rss` 404 |
| 瓦斯阅读（qnmlgb.tech） | ⚠️ 活但无 RSS | 有公众号目录，但作者页/文章页均不暴露 mp 链接、无公开 RSS 输出 |
| 今天看啥（jintiankansha.me） | ⚠️ 活但需账号 | RSS 为登录后功能（`/account/rss/submit`） |

**关键发现**：BestBlogs 项目把自己的 wechat2rss 私有实例以 OPML 公开
（`github.com/ginobefun/BestBlogs` 的 `opml/bestblogs_wechat2rss_opml_all.opml`，375 个 feed 全部可公开访问）。
feed 格式与 xlab 镜像完全一致（RSS 2.0 + `content:encoded` 全文），实测单 feed 最大 ~3.8MB。
feed id 是 HMAC(公众号ID, 服务端 secret)，**不可本地构造**——只能用其已收录账号，OPML 即权威清单。

## 2. 筛选与实测流程

1. 从 BestBlogs OPML（375）+ xlab 快照（395，本地 `/tmp/w2r_feeds.json`）取并集。
2. 排除已覆盖：一批 90 slug/名称、`wechat_maobidao`/`wechat_sixianggangyin`/`wechat_zeping`、
   wewe-rss 8 号（zhigu/yuanchuan/canghai/fupeng/lixunlei/congming/beiwei/latepost）。
3. 排除与平台直连源重复的号：华尔街见闻/财新/界面/36氪/虎嗅/财联社/雪球/新华社（直连源已覆盖）。
4. 排除官媒党政（人民日报/新华社/央视/环球时报…）、企业官方 PR（DeepSeek/Kimi/智谱/通义/钉钉/飞书…）、
   体育/文学/生活方式/设计/纯开发工程号（off-topic）。
5. 人工过一遍标题样本，剔除营销号/标题党/软文号（见 §4 剔除记录）。
6. **ECS 逐个实测**（`curl --max-time 25`，6 并发）：HTTP 200 + `items>0` + 前 5 条有正文
   （`content:encoded` >500 字符或 `description` >200 字符）+ 最新条目 ≤30 天。
   112 候选全部 200 且有正文；9 个因停更/质量淘汰（§4），最终 **103 源**。

## 3. 103 源清单（slug / 名称 / 分类 / 镜像 / 实测状态）

实测时间 2026-07-28（ECS 发起）；全部 HTTP 200、有正文、30 天内有更新。

| source | 名称 | 分类 | 镜像 | 实测 |
|---|---|---|---|---|
| `wechat_zepinghongguan` | 泽平宏观 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_xiangshuai` | 香帅的金融江湖 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_zhongjin` | 中金点睛 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_cf40` | 中国金融四十人论坛 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_worldbank` | 世界银行 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_eeo` | 经济观察报 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_yetan` | 叶檀财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_zhangyong` | 张湧说财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_gongfucaijing` | 功夫财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_cjzaocan` | 财经早餐 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_econdaily` | 一天一篇经济学人 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_caijing` | 财经杂志 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 26 Jul 2026 |
| `wechat_yicai` | 第一财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_herald21` | 21世纪经济报道 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_nbd` | 每日经济新闻 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_qszg` | 券商中国 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_lengjing` | 棱镜 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_shenwang` | 深网腾讯新闻 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_ifengcj` | 凤凰网财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_gelonghui` | 格隆汇APP | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_eastmoney` | 东方财富网 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_wind` | Wind万得 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_barrons` | Barrons巴伦 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_txcaijing` | 腾讯财经 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_xiaolinshuo` | 小Lin说的公众号 | 宏观经济 | bestblogs | ✅ 200 / 10 条 / 最新 02 Jul 2026 |
| `wechat_dashuilai` | 大水来 | 宏观经济 | xlab | ✅ 200 / 20 条 / 最新 14 Jul 2026 |
| `wechat_dianshi` | 点拾投资 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 25 Jul 2026 |
| `wechat_luosiding` | 银行螺丝钉 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_laoqian` | 老钱日日谈 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_tzshixi` | 投资实习所 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 08 Jul 2026 |
| `wechat_gududanao` | 孤独大脑 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_sanzhe` | 三折人生 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 20 Jul 2026 |
| `wechat_gelan` | 格兰投研 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_laozhang` | 老张投研 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_investguru` | investguru | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 03 Jul 2026 |
| `wechat_haitun` | 海豚研究 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_fengrui` | 峰瑞资本 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_gaoling` | 高瓴创投 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 19 Jul 2026 |
| `wechat_jingwei` | 经纬创投 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_zhenge` | 真格基金 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 24 Jul 2026 |
| `wechat_hongshan` | 红杉汇 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_shanxing` | 山行资本 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_etfjinhua` | ETF进化论 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_liubei` | 刘备教授 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 11 Jul 2026 |
| `wechat_zhenglitao` | 郑立涛 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 14 Jul 2026 |
| `wechat_xieyin` | 携隐Melody | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_sjfendui` | 随机小分队 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_taiyang` | 太阳照常升起 | 投资策略 | bestblogs | ✅ 200 / 10 条 / 最新 24 Jul 2026 |
| `wechat_bandaoti` | 半导体行业观察 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_zhidongxi` | 智东西 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_jiazi` | 甲子光年 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 24 Jul 2026 |
| `wechat_daofa` | 刀法研究所 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 26 Jul 2026 |
| `wechat_zhaibo` | 窄播 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_xinbang` | 新榜 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 25 Jul 2026 |
| `wechat_yunying` | 运营研究社 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_jianshi` | 见实 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_medsci` | 梅斯医学 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_deeptech` | DeepTech深科技 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_naojiti` | 脑极体 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_langchao` | 浪潮工作室 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_saasbyx` | SaaS白夜行 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 26 Jul 2026 |
| `wechat_fangwei` | 方伟看十年 | 行业研究 | bestblogs | ✅ 200 / 10 条 / 最新 26 Jul 2026 |
| `wechat_sota` | 机器之心SOTA模型 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_infoq` | InfoQ | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_sspai` | 少数派 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_appso` | APPSO | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_leifeng` | 雷峰网 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_taimeiti` | 钛媒体 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_guixingren` | 硅星人Pro | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_lanxi` | 阑夕 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 23 Jul 2026 |
| `wechat_caoz` | caoz的梦呓 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 23 Jul 2026 |
| `wechat_guaidao` | 互联网怪盗团 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_mactalk` | MacTalk | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_wangjianshuo` | 王建硕 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_mitreview` | 麻省理工科技评论APP | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_znyx` | 智能涌现 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_txkeji` | 腾讯科技 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_wangyikeji` | 网易科技 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_baijing` | 白鲸出海 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_woshipm` | 人人都是产品经理 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_founderpark` | Founder Park | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_kazike` | 数字生命卡兹克 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_guicang` | 歸藏的AI工具箱 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 17 Jul 2026 |
| `wechat_saibo` | 赛博禅心 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_crossing` | 十字路口Crossing | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_newin` | 有新Newin | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 25 Jul 2026 |
| `wechat_hwunicorn` | 海外独角兽 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_shensiquan` | 深思圈 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_guigu` | 硅谷科技评论 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 25 Jul 2026 |
| `wechat_thoughtworks` | 思特沃克洞见 | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_wadianai` | 晚点AI | 科技评论 | bestblogs | ✅ 200 / 10 条 / 最新 16 Jul 2026 |
| `wechat_dailaoban` | 饭统戴老板 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_wuxiaobo` | 吴晓波频道 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_liurun` | 刘润 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_bijixia` | 笔记侠 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_lishi` | 砺石商业评论 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 24 Jul 2026 |
| `wechat_hbr` | 哈佛商业评论 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_zhenghedao` | 正和岛 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_chuangyebang` | 创业邦 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_pedaily` | 投资界 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |
| `wechat_anyong` | 暗涌Waves | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 24 Jul 2026 |
| `wechat_jiubian` | 九边 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 22 Jul 2026 |
| `wechat_caobian` | 槽边往事 | 商业深度 | bestblogs | ✅ 200 / 10 条 / 最新 27 Jul 2026 |

## 4. 剔除记录（12 条）

| 名称 | 拟分类 | 镜像 | 剔除原因 |
|---|---|---|---|
| 老钱说钱 | 投资策略 | bestblogs | 停更：最新文 2022-07-01 |
| 孟岩 | 投资策略 | bestblogs | 停更：最新文 2026-03-27（>120 天） |
| 刘言飞语 | 科技评论 | bestblogs | 停更：最新文 2026-06-25（>30 天） |
| 43 Talks | 科技评论 | bestblogs | 停更：最新文 2026-06-14（>40 天） |
| 晚点对话 | 商业深度 | bestblogs | 停更：最新文 2025-05-19 |
| Delphi研习社 | 宏观经济 | xlab | 停更：最新文 2026-05-31（>55 天） |
| 金色钱江 | 宏观经济 | xlab | 停更：最新文 2025-04-10 |
| 科技美学 | 科技评论 | bestblogs | 内容质量：近期全为新品官宣软文流，营销属性重 |
| 毛有话说 | 宏观经济 | bestblogs | 内容质量：标题党化（“今天的瓜太猛了！”），剔除 |
| 卢瑟经济学之安生杂谈 | 宏观经济 | xlab | 2026-07-27 一批已验证 404 死号（不在本次候选） |
| 卢瑟经济学安生杂谈 | 宏观经济 | xlab | 同上 |
| 碳基体 | 科技评论 | xlab | 2026-07-27 一批已验证 0 条目停更（不在本次候选） |

另：候选阶段即排除的大类——安全研究号 ~326（off-topic，一批文档已述）、官媒党政、企业 PR、
体育（苏群/体坛周报…）、文学生活（莫言/十点读书/看理想…）、纯设计（优设/设计癖…）、
纯开发（前端早读课/稀土掘金…）、AI 公司官方号（DeepSeek/智谱/Kimi…）。

## 5. 运维手册

### 5.1 日常健康

- 10 个 job：`news_wechat2b_w2[a-j]_60m`，每小时一批，健康面板"公众号二批 X 组"。
- 单源缺文排查：`SELECT * FROM etl_log WHERE job_name='news_wechat2b_w2a_60m' ORDER BY start_time DESC;`
  先 grep normalize SQL error（2026-07-27 截断 P0 的教训）；`source_id` 已加宽 500，本批 mp 长链接安全。

### 5.2 镜像失效

- 症状：某批次连续 failed、日志 `feed <slug> failed: ...`。
- bestblogs 镜像是他人公益实例，可能随时下线/改密。失效时：
  1. 先确认是整域失效还是单 feed：`curl -s -o /dev/null -w "%{http_code}" https://wechat2rss.bestblogs.dev/feed/<hash>.xml`
  2. 单 feed 失效 → 从 `WECHAT2B_FEEDS` 删除该行（批次自动收缩）；
  3. 整域失效 → 尝试 xlab 是否有同名号替补；没有就把批次 job 下掉（scheduler 里注释对应注册）。
- 禁止在运行时重试放大：爬虫失败即 WARNING + 跳过，下个小时再来。

### 5.3 wewe-rss 通道 B 恢复（用户操作）

当前微信读书 token 失效。恢复流程：
1. `docker exec -it alloyresearch-wewe-rss` 不可扫码；走 Web：`http://<ECS>:4000`（仅 127.0.0.1，需 SSH 隧道
   `ssh -L 4000:127.0.0.1:4000 ad-research`）→ dash 登录 AuthCode `123567` → 账号管理重新扫码。
2. 或 tRPC：`POST /trpc/platform.addAccount?batch=1` 拿二维码 base64，用户微信读书扫码。
3. 恢复后可把"一批 wewe-rss 8 号"之外的财经号（即本批因镜像限制未能覆盖的号）走通道 B 增补。
4. 注意：feed.add 间隔 ≥10s（过频封控 24h）；代理 weread.111965.xyz 抖动，refresh 要多轮重试。

**已知问题（非本批引入）**：wewe-rss 现有 8 号入库文章 `body` 为空（`.json` 默认不带 `mode=fulltext`，
实测 atom/rss 也只有标题）。修复方向：`wechat_zeping._build_feed_url` 追加 `mode=fulltext`
（首次抓取触发 wewe-rss 按需取全文并缓存，之后命中缓存）。属既有源改进，本批未动。

### 5.4 营销过滤器

本批 job 复用 `WechatMarketingFilter`（LLM 24h 缓存）。门户媒体号（腾讯科技/网易科技/凤凰财经等）
偶发软文会被 LLM 判 `not is_knowledge` 拒掉，`rejected_marketing` 计数体现在 etl_log。
若某源误杀严重，在 runbook 记录后可考虑把该源挪去独立白名单 job（暂未实现）。

## 6. 决策日志

| 决策 | 理由 |
|---|---|
| 主通道用 bestblogs 镜像而非 xlab | xlab 合格池枯竭（≤5）；bestblogs 375 号正对财经/科技 |
| 每行存完整 URL 而非 hash+固定模板 | 双镜像并存，URL 自带镜像归属；未来加第三镜像零改动 |
| 批次键 `w2a-w2j`、job 前缀 `wechat2b` | 与一批 `a-i`/`wechat2rss`、indie `a-n`、global `a-l` 命名空间隔离 |
| 保留营销过滤器 | 本批含门户媒体/评测号，软文概率高于一批独立号 |
| 本批不走 wewe-rss | token 失效需用户扫码；恢复后作为三批通道 |
| slug 用拼音/缩写 `[a-z0-9]+` | 与一批风格一致；`source = wechat_{slug}` 进统一命名空间 |

## 7. 文件清单

| 文件 | 说明 |
|---|---|
| `app/services/news/sources/wechat2rss_batch2.py` | 103 源表 + 10 批次 + `Wechat2RssBatch2Crawler` |
| `app/tests/news/test_wechat2rss_batch2.py` | 表完整性/格式/无重复/爬虫 mock/集成接线（xfail 待集成） |
| `docs/dev-notes/20260728-wechat-batch2-integration.md` | 三文件精确补丁（scheduler_jobs/scheduler/news） |
| `docs/dev-notes/20260728-wechat-batch2.md`(+`.html`) | 本 runbook |
