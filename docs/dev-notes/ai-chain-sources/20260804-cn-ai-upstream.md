# 中国 AI 产业链上游资讯源搜罗（半导体/算力/云/政策/研究/能源）

- 日期：2026-08-04
- 范围：中国 AI 产业链最上游信号源——半导体、算力/数据中心、云计算、AI 政策监管、AI 研究机构、电力能源
- 方法：每个候选均 `curl -sL --http1.1 --compressed -A <浏览器UA> --max-time 15~18` 实测，取响应前 500-600 字符，含 `<rss`/`<feed`/`<?xml` 才判 ✅；已 grep 存量 1012 源排重（`/tmp/adresearch-build/existing_sources.txt`）
- 存量已覆盖（不重复接入）：半导体行业观察(wechat_bandaoti)、智东西/芯东西(wechat_zhidongxi)、InfoQ 中文(zhm_infoqcn/wechat_infoq)、机器之心(wechat_jiqizhixin)、量子位(zhb_qbitai)、新智元(wechat_xinzhiyuan)、雷锋网(wechat_leifeng/global_leiphone)、钛媒体(global_tmtpost)、ITHome(global_ithome_cn)、cnBeta(zhb_cnbeta)、博客园(zhb_cnblogs)、开源中国(zhb_oschina)、SegmentFault(global_segmentfault)、SemiAnalysis(ofc_semianalysis)、SemiWiki/Semiconductor Engineering(asen_*)、DeepTech(wechat_deeptech)
- RSSHub 公共实例 `rsshub.app` 从本网络实测 000 不可达、`docs.rsshub.app` 超时，镜像路由无法实测，本批一律标注"建议自建 RSSHub"而不写未验证路由

## 实测结果总表

图例：✅=官方 RSS 实测通过；❌=无官方 RSS（实测 404/WAF/反爬）；镜像=公众号体系走平台 wechat2rss；HTML=需 HTML 抓取

| source_slug | 显示名 | 站点 URL | RSS URL（✅/❌/镜像） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| cn_laoyaoba | 集微网 | https://www.laoyaoba.com | ✅ https://www.laoyaoba.com/api/rss/hbb | zh | 半导体 | 行业新闻/深度 | 中国半导体产业第一垂直媒体，设计/制造/封测/设备材料全覆盖，上市公司动态密集 |
| cn_trendforce_semi | 集邦咨询-半导体 | https://www.trendforce.cn | ✅ https://www.trendforce.cn/feed/Semiconductors.html | zh | 半导体 | 研究机构快讯 | DRAM/HBM/NAND/晶圆代工报价与产能数据，存储周期最直接的上游信号 |
| cn_trendforce_emerging | 集邦咨询-新兴科技 | 同上 | ✅ https://www.trendforce.cn/feed/Emerging_technology.html | zh | 半导体/算力 | 研究快讯 | AI 服务器出货量、机器人、AR/VR 产业预估，算力需求侧权威数据 |
| cn_trendforce_energy | 集邦咨询-新能源 | 同上 | ✅ https://www.trendforce.cn/feed/Energy.html | zh | 能源 | 研究快讯 | 光伏/储能/电池报价，数据中心绿电配套的成本侧信号 |
| cn_cena | 电子信息产业网（中国电子报） | https://www.cena.com.cn | ✅ https://www.cena.com.cn/index.rss | zh | 半导体 | 官媒行业新闻 | 工信部主管行业报，半导体政策解读+产业新闻，政策风向标 |
| cn_c114_top | C114 中国通信网-要闻精选 | https://www.c114.com.cn | ✅ http://www.c114.com.cn/rss/rss_news_489.xml（GB2312） | zh | 算力 | 行业新闻 | 运营商集采/光模块/算力网络建设第一线，中际旭创、新易盛等光通信标的基本面信号 |
| cn_c114_policy | C114-行业政策 | 同上 | ✅ http://www.c114.com.cn/rss/rss_news_518.xml（GB2312） | zh | 政策 | 政策新闻 | 通信/算力基础设施政策与运营商监管动态 |
| cn_cfol | 光纤在线 | http://www.c-fol.net | ✅ http://www.c-fol.net/news/rss.php（GBK） | zh | 算力 | 行业新闻 | 光通信/光模块垂直媒体，800G/1.6T 光模块与 CPO 技术进展一手来源 |
| cn_dostor | 存储在线 | http://www.dostor.com | ✅ http://www.dostor.com/rss | zh | 算力 | 行业新闻 | 存储/服务器/数据中心垂直媒体，企业级存储与算力基建采购风向标 |
| cn_zol_cpu | 中关村在线-CPU 频道 | https://www.zol.com.cn | ✅ http://rss.zol.com.cn/cpu.xml（GB2312） | zh | 半导体 | 硬件新闻/评测 | 消费级芯片与 PC 硬件行情，国产 CPU/GPU 新品动态（频道齐全可换其他频道 xml） |
| cn_yesky_news | 天极网-资讯频道 | https://www.yesky.com | ✅ http://news.yesky.com/index.xml（GB2312） | zh | 云计算/半导体 | IT 新闻 | 综合 IT 资讯，企业 IT 与数据中心频道可扩展（net.yesky.com 已实测通） |
| cn_elecfans_bbs | 电子发烧友论坛 | https://www.elecfans.com | ✅ https://bbs.elecfans.com/forum.php?mod=rss&auth=0 | zh | 半导体 | 论坛讨论 | 一线工程师对国产芯片/EDA/器件的真实讨论热度，主站资讯无 RSS |
| cn_juejin | 掘金 | https://juejin.cn | ✅ https://juejin.cn/rss | zh | 云计算 | 开发者社区 | 国内最大开发者社区热榜，AI 工程化/云原生技术采用度的实时温度计 |
| cn_aws_blog | AWS 中国官方博客 | https://aws.amazon.com/cn/blogs/china/ | ✅ https://aws.amazon.com/cn/blogs/china/feed/ | zh | 云计算 | 官方技术博客 | 全球云厂商中国区产品/降价/区域策略，云价格战与 Graviton 自研芯片对标信号 |
| cn_meituan_tech | 美团技术团队 | https://tech.meituan.com | ✅ https://tech.meituan.com/atom.xml | zh | 云计算 | 企业技术博客 | 头部互联网算力基建与大模型工程实践，间接观察国内 AI 算力消耗强度 |
| cn_people_it | 人民网-IT 频道 | http://it.people.com.cn | ✅ http://www.people.com.cn/rss/it.xml | zh | 政策 | 官媒新闻 | 中央党媒科技口报道口径，数字经济/AI 政策风向的官方叙事基准 |
| cn_people_scitech | 人民网-科技频道 | http://scitech.people.com.cn | ✅ http://www.people.com.cn/rss/scitech.xml | zh | 研究/政策 | 官媒新闻 | 国家科技成就与重大专项报道，跟踪"科技自立自强"政策落地节奏 |
| cn_people_energy | 人民网-能源频道 | http://energy.people.com.cn | ✅ http://www.people.com.cn/rss/energy.xml | zh | 能源 | 官媒新闻 | 电力体制改革/绿电交易/电价政策，数据中心用电成本的政策先行指标 |
| cn_eetchina | 电子工程专辑（EET China） | https://www.eet-china.com | ❌ 全站连接被重置（000，疑似 WAF 封 IP），feed 路径未能实测 | zh | 半导体 | 行业媒体 | ASPENCORE 中文旗舰，模拟/MCU/功率半导体深度内容，建议换网络复测或 HTML 抓取 |
| cn_esmchina | 国际电子商情 | https://www.esmchina.com | ❌ 全站连接被重置（000） | zh | 半导体 | 供应链媒体 | 元器件分销/缺货涨价行情最敏感媒体，半导体周期拐点信号强 |
| cn_eeworld | 电子工程世界 | https://www.eeworld.com.cn | ❌ /rss.xml 403（WAF） | zh | 半导体 | 技术媒体 | 工程师向半导体/嵌入式内容，国产替代技术动态 |
| cn_eetop | EETOP 创芯网论坛 | https://bbs.eetop.cn | ❌ forum.php?mod=rss 403；主站 /rss 403 | zh | 半导体 | 论坛 | 国内 IC 设计工程师第一大社区，海思/寒武纪等校招与技术讨论风向标 |
| cn_moorenews | 摩尔芯闻 | https://www.moore.news | ❌ 全站连接失败（000） | zh | 半导体 | 行业新闻 | 半导体投融资/并购消息聚合，一级市场信号 |
| cn_21ic | 21IC 中国电子网 | https://www.21ic.com | ❌ 各 rss 路径 404 | zh | 半导体 | 技术媒体 | 老牌电子工程师媒体，MCU/功率器件国产替代动态 |
| cn_chinaflashmarket | 闪存市场 | https://www.chinaflashmarket.com | ❌ 无 RSS | zh | 半导体 | 行情数据 | NAND/DRAM 现货价与模组厂动态，存储周期最敏感的现货信号 |
| cn_eefocus | 与非网 | https://www.eefocus.com | ❌ 各 feed 路径 404 | zh | 半导体 | 技术媒体 | 芯片原厂方案与供应链新闻 |
| cn_semichina | SEMI 中国 | http://www.semi.org.cn | ❌ 无 RSS | zh/en | 半导体 | 行业协会 | 全球半导体设备/材料协会中国站，SEMI 报告与设备出货数据发布口 |
| cn_csia | 中国半导体行业协会 | http://www.csia.net.cn | ❌ 无 RSS | zh | 半导体 | 行业协会 | 官方行业统计与政策建议出口，IC 产业运行数据源头 |
| cn_eepw | 电子产品世界 | http://www.eepw.com.cn | ❌ 无 RSS | zh | 半导体 | 技术媒体 | 器件选型与原厂动态 |
| cn_ofweek_ee | OFweek 电子工程 | https://ee.ofweek.com | ❌ 无 RSS | zh | 半导体 | 行业媒体 | 半导体/光通讯综合行业站 |
| cn_chinaaet | 电子技术应用 | http://www.chinaaet.com | ❌ 无 RSS | zh | 半导体 | 技术期刊 | 北大核心期刊新闻口，偏学术 |
| cn_hqew | 华强电子网 | http://www.hqew.com | ❌ 无 RSS | zh | 半导体 | 现货市场 | 华强北元器件现货行情，缺货/炒货一线信号 |
| cn_chongdiantou | 充电头网 | https://www.chongdiantou.com | ❌ /feed 404 | zh | 能源/半导体 | 拆解评测 | 快充/电源管理芯片拆解数据库，数据中心电源链延伸观察 |
| wechat_xinzhixun | 芯智讯 | 公众号（无独立站） | 镜像：走 wechat2rss 体系 | zh | 半导体 | 公众号自媒体 | 信创/半导体 top 自媒体（2024 十大信创自媒体），产业链爆料速度快 |
| wechat_tiantianic | 天天IC | 公众号（无独立站） | 镜像：走 wechat2rss 体系 | zh | 半导体 | 公众号自媒体 | 半导体大厂人事/流片/订单小道消息集散地 |
| wechat_icrank | 芯榜 | 公众号（无独立站） | 镜像：走 wechat2rss 体系 | zh | 半导体 | 公众号自媒体 | 半导体榜单/融资统计，国产芯片公司追踪 |
| cn_idcquan | 中国 IDC 圈 | https://www.idcquan.com | ❌ 无 RSS，需 HTML 抓取 | zh | 算力 | 行业媒体 | IDC/算力中心垂直第一媒体，第三方数据中心（万国/世纪互联/秦淮）项目与政策全覆盖 |
| wechat_yuntoutiao | 云头条 | 公众号（无独立站） | 镜像：走 wechat2rss 体系 | zh | 算力/云计算 | 公众号自媒体 | 信创十大自媒体，云计算/算力基础设施采购与政企中标信息快 |
| cn_cdcc | CDCC 中国数据中心工作组 | 无有效官网（cdcc.com.cn 已变卖页域名） | 镜像：公众号"CDCC"；cidc.org.cn（通信协会数据中心委员会）亦无 RSS | zh | 算力 | 标准组织 | 数据中心国家标准/液冷/PUE 白皮书出口，AIDC 建设标准风向 |
| cn_jifang360 | 机房 360 | http://www.jifang360.com | ❌ 全站连接失败（000，未实测） | zh | 算力 | 行业媒体 | 机房工程/UPS/精密空调供应链 |
| cn_upsapp | UPS 应用 | http://www.upsapp.com | ❌ 全站连接失败（000，未实测） | zh | 算力/能源 | 行业媒体 | 数据中心供配电/UPS 专业媒体 |
| cn_cww | 通信世界网 | http://www.cww.net.cn | ❌ 无 RSS | zh | 算力 | 行业媒体 | 工信部背景通信媒体，算力网络政策解读 |
| cn_cnii | 中国信息产业网 | http://www.cnii.com.cn | ❌ 无 RSS | zh | 算力/政策 | 官媒行业新闻 | 人民邮电报旗下，运营商与信息产业政策 |
| cn_aliyun_dev | 阿里云开发者社区 | https://developer.aliyun.com | ❌ 各 feed 路径 404 | zh | 云计算 | 官方社区 | 国内最大云厂商技术输出，通义/百炼/倚天芯片动态，需 HTML 或 HTML 列表页抓取 |
| cn_tencentcloud_dev | 腾讯云开发者社区 | https://cloud.tencent.com/developer | ❌ /feed /rss 均 404 | zh | 云计算 | 官方社区 | 腾讯云/混元/星星海服务器动态 |
| cn_huaweicloud_blog | 华为云博客 | https://bbs.huaweicloud.com/blogs | ❌ /rss /feed 均 404 | zh | 云计算 | 官方社区 | 华为云/盘古/昇腾生态第一出口，昇腾算力链必盯，需 HTML 抓取 |
| cn_51cto | 51CTO | https://www.51cto.com | ❌ WAF 自定义 567 拦截 | zh | 云计算 | IT 媒体 | 老牌企业 IT 媒体 |
| cn_csdn | CSDN | https://www.csdn.net | ❌ /rss 404（官方已下线全站 RSS） | zh | 云计算 | 开发者社区 | 国内最大开发者社区，需 RSSHub 自建 |
| cn_volcengine_dev | 火山引擎开发者社区 | https://developer.volcengine.com | ❌ 无 RSS | zh | 云计算 | 官方社区 | 字节云/豆包大模型算力输出口 |
| cn_zhiding | 至顶网 | https://www.zhiding.cn | ❌ 无 RSS | zh | 云计算 | 企业 IT 媒体 | 企业级 IT/服务器/存储报道 |
| cn_chinabyte | 比特网 | http://www.chinabyte.com | ❌ 无 RSS | zh | 云计算 | 企业 IT 媒体 | 服务器/数据中心频道有积累 |
| cn_donews | DoNews | https://www.donews.com | ❌ 无 RSS | zh | 云计算 | IT 媒体 | 综合互联网新闻 |
| cn_techweb | TechWeb | http://www.techweb.com.cn | ❌ 500/连接失败 | zh | 云计算 | IT 媒体 | 综合科技新闻 |
| cn_pconline | 太平洋电脑网 | https://www.pconline.com.cn | ❌ /rss/ 403 | zh | 半导体 | 硬件媒体 | 消费硬件行情 |
| cn_mydrivers | 快科技 | https://www.mydrivers.com | ❌ rss.aspx 变 HTML，无有效 RSS | zh | 半导体 | 硬件新闻 | 芯片新品爆料快，消费级 GPU/CPU 行情 |
| cn_expreview | 超能网 | https://www.expreview.com | ❌ 全站 JS WAF（/_guard/auto.js） | zh | 半导体 | 硬件评测 | 显卡/功耗深度评测 |
| cn_pingwest | 品玩 | https://www.pingwest.com | ❌ /feed 404 | zh | 云计算 | 科技媒体 | 大模型产业报道有深度 |
| cn_it168 | IT168 | http://www.it168.com | ❌ rss 子域 404 | zh | 云计算 | 企业 IT 媒体 | 服务器/存储评测老牌 |
| gov_miit | 工业和信息化部 | https://www.miit.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 部委官网 | AI/半导体/算力政策最核心出口（电子信息司/信息技术发展司），算力券/大模型备案/集成电路政策源头 |
| gov_cac | 国家网信办 | http://www.cac.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 部委官网 | 生成式 AI 备案/算法备案/数据出境监管唯一出口，AI 监管合规第一信号 |
| gov_ndrc | 国家发改委 | https://www.ndrc.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 部委官网 | 全国一体化算力网/东数西算工程主管，数据中心能耗指标与电价政策源头 |
| gov_most | 科技部 | https://www.most.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 部委官网 | AI 国家科技重大专项/新一代 AI 发展规划主管 |
| gov_nda | 国家数据局 | https://www.nda.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 部委官网 | 数据要素×行动计划/数据基础设施主管，数据要素产业最权威出口 |
| gov_caict | 中国信通院 | http://www.caict.ac.cn | ❌ 412 WAF 拦截，需 HTML 抓取（换 UA/IP 复测） | zh | 政策/研究 | 智库 | 工信部直属智库，算力指数/大模型白皮书/数据中心白皮书权威数据源 |
| gov_govcn | 中国政府网 | https://www.gov.cn | ❌ 无官方 RSS（404），需 HTML 抓取 | zh | 政策 | 国务院官网 | 国务院 AI+ 行动意见等顶层文件首发 |
| gov_scio | 国新网 | http://www.scio.gov.cn | ❌ 521 源站故障（未实测） | zh | 政策 | 官方发布 | 国新办发布会实录，部委 AI 表态实录 |
| dep_chinadep | 上海数据交易所 | https://www.chinadep.com | ❌ 无 RSS，需 HTML 抓取 | zh | 政策 | 交易所 | 数据产品挂牌/交易额官方口径，数据要素市场化直接证据 |
| lab_baai | 智源研究院 | https://www.baai.ac.cn | ❌ SPA 无 RSS，需 HTML 抓取 | zh | 研究 | 研究院官网 | 北京 AI 旗舰研究院（悟道/FlagOpen），国产大模型技术路线风向标 |
| lab_baai_hub | 智源社区 | https://hub.baai.ac.cn | ❌ 各 feed 路径 404 | zh | 研究 | 社区 | 智源论文解读/活动，AI 前沿中文解读 |
| lab_shlab | 上海人工智能实验室 | https://www.shlab.org.cn | ❌ 无 RSS，需 HTML 抓取 | zh | 研究 | 研究院官网 | 书生大模型/OpenDataLab，国产开源模型与数据集核心供给方 |
| lab_zhejianglab | 之江实验室 | https://www.zhejianglab.com | ❌ SPA 无 RSS，需 HTML 抓取 | zh | 研究 | 实验室官网 | 智能计算/智能算力国家实验室方向 |
| lab_pcl | 鹏城实验室 | https://www.pcl.ac.cn | ❌ 无 RSS，需 HTML 抓取 | zh | 研究 | 实验室官网 | 鹏城云脑/中国算力网（C²NET）建设方，国家算力调度关键节点 |
| lab_air_tsinghua | 清华智能产业研究院（AIR） | https://air.tsinghua.edu.cn | ❌ 无 RSS | zh | 研究 | 研究院官网 | 张亚勤领衔，AI+产业研究与企业合作动态 |
| org_caai | 中国人工智能学会 | http://www.caai.cn | ❌ 无 RSS | zh | 研究 | 学会官网 | CAAI 智库报告/学会奖项，学术-产业连接点 |
| org_ccf | 中国计算机学会 | https://www.ccf.org.cn | ❌ 无 RSS | zh | 研究 | 学会官网 | CNCC/技术前沿报告，计算学科权威声音 |
| cn_bjx_power | 北极星电力网 | https://www.bjx.com.cn | ❌ 阿里云 WAF JS 挑战，curl 不可过，需 HTML（带 JS 方案） | zh | 能源 | 行业媒体 | 电力行业第一垂直站，电价/绿电/虚拟电厂/电力市场化交易全覆盖，AIDC 用电成本信号源 |
| cn_inen | 国际能源网 | https://www.in-en.com | ❌ 无 RSS | zh | 能源 | 行业媒体 | 能源综合门户，电力/储能频道 |
| cn_china5e | 中国能源网 | https://www.china5e.com | ❌ 无 RSS | zh | 能源 | 行业媒体 | 能源政策与行业新闻 |
| cn_chinapower | 中国电力网 | http://www.chinapower.com.cn | ❌ 无 RSS | zh | 能源 | 行业媒体 | 电力行业新闻 |
| cn_cpnn | 中国电力新闻网 | http://www.cpnn.com.cn | ❌ 无 RSS | zh | 能源 | 官媒行业新闻 | 中电传媒官方出口，电力系统动态 |
| cn_sgcc_news | 国家电网新闻网 | http://news.sgcc.com.cn | ❌ 连接失败（000，未实测） | zh | 能源 | 央企官网 | 特高压/电网投资/数据中心并网政策执行方动态 |
| cn_cbdio | 数据观（中国大数据产业观察） | http://www.cbdio.com | ❌ 连接失败（000，未实测） | zh | 政策 | 行业媒体 | 大数据/数据要素产业报道 |
| cn_cctv | 央视网 | https://www.cctv.com | ❌ /rss/ 403 | zh | 政策 | 官媒 | 新闻联播口径 AI 报道 |
| cn_cnr | 央广网 | https://www.cnr.cn | ❌ 无有效 RSS | zh | 政策 | 官媒 | 经济之声 AI 产业报道 |

## 统计

- 候选总数：**74 行**（去重后站点级 63 个，其中 TrendForce 多 feed 计 3 行、C114 计 2 行）
- 官方 RSS 实测通过（✅）：**15 站 / 18 个 feed**（含 GB2312/GBK 编码 4 个，解析端需处理编码）
- 实测通过率：15/63 ≈ **24%**（中文专业媒体 RSS 生态整体凋敝，符合预期）
- ❌ 但高价值、建议 HTML 抓取/公众号镜像接入的：约 20 个（政府部委、研究院、IDC 圈、北极星等）
- 连接层失败未能实测的（000/WAF）：eet-china、esmchina、moore.news、jifang360、upsapp、sgcc、cbdio、scio、eeworld(403)、eetop(403)、expreview(WAF)、51cto(567)、bjx(WAF 挑战)、caict(412)——建议从 ECS 生产网络或换 UA 复测后定级

## Top 20 必接（优先级排序）

| # | 源 | 接入方式 | 理由 |
|---|---|---|---|
| 1 | 集微网 laoyaoba | ✅ RSS 直连 | 中国半导体第一垂直媒体，设计-制造-封测-设备材料全链新闻 |
| 2 | 集邦咨询-半导体 | ✅ RSS 直连 | DRAM/HBM/代工报价与产能，存储周期最硬数据 |
| 3 | 集邦咨询-新兴科技 | ✅ RSS 直连 | AI 服务器出货量预测，算力需求侧权威 |
| 4 | 工信部 gov_miit | HTML 抓取 | 半导体/AI/算力政策最核心出口 |
| 5 | 网信办 gov_cac | HTML 抓取 | 大模型备案/算法监管，AI 合规生死线 |
| 6 | 国家发改委 gov_ndrc | HTML 抓取 | 东数西算/一体化算力网/能耗指标政策源头 |
| 7 | 国家数据局 gov_nda | HTML 抓取 | 数据要素政策最权威出口 |
| 8 | C114 要闻精选 | ✅ RSS 直连 | 运营商集采/光模块订单一线信号 |
| 9 | 光纤在线 c-fol | ✅ RSS 直连 | 800G/1.6T 光模块与 CPO 技术垂直源 |
| 10 | 中国电子报 cena | ✅ RSS 直连 | 工信部主管行业报，产业政策+半导体新闻 |
| 11 | 存储在线 dostor | ✅ RSS 直连 | 企业级存储/服务器/数据中心采购风向 |
| 12 | 人民网 IT/科技 | ✅ RSS 直连×2 | 党媒科技政策叙事基准，AI 顶层表态 |
| 13 | 中国 IDC 圈 idcquan | HTML 抓取 | 第三方 IDC/智算中心项目与政策第一媒体 |
| 14 | 信通院 CAICT | HTML 抓取（换 UA 复测） | 算力指数/大模型/数据中心白皮书数据源 |
| 15 | 智源研究院 BAAI | HTML 抓取 | 国产大模型技术路线风向标 |
| 16 | 上海 AI 实验室 | HTML 抓取 | 书生系开源模型与数据集核心供给方 |
| 17 | 华为云博客 | HTML 抓取 | 昇腾算力生态第一出口，国产算力链必盯 |
| 18 | 人民网能源 | ✅ RSS 直连 | 电价/绿电/电力市场化，AIDC 用电成本政策 |
| 19 | 北极星电力网 | HTML（需 JS 渲染方案） | 电力垂直第一站，数据中心绿电配套信号 |
| 20 | 芯智讯+云头条+天天IC | wechat2rss 镜像 | 信创/半导体 top 公众号，爆料速度全网最快 |

## 接入备注

1. **编码**：c114/zol/yesky 为 GB2312，c-fol 为 GBK，采集端需按 charset 解码（平台 rss_common 已处理过类似源，参考 20260730 iplaysoft 容错恢复经验）。
2. **政府站 HTML 抓取**：miit/cac/ndrc/most/nda/caict 均无 RSS，建议复用平台 `stats_gov`/`cninfo` 的 HTML 列表页抓取模式，按栏目（如 miit 电子信息司 `jgsj/dzs/gzdt/`）定向抓。
3. **WAF 复测清单**：bjx（阿里云 WAF JS 挑战）、caict（412）、51cto（567）、eetop/eeworld（403）、eet-china/esmchina（连接重置）——建议在 ECS 生产网络复测，必要时走 Playwright 渲染抓取。
4. **公众号镜像**：芯智讯/云头条/天天IC/芯榜/CDCC 无独立站，直接走平台 wechat2rss 体系（参考 20260727 批次经验，先 grep 查重再入批次）。
5. ** TrendForce 完整 feed 清单**（全部实测 ✅）：Semiconductors / Emerging_technology / Energy / Display / Communication / Consumer_electronics / LED / macroeconomic，可按需扩展。
6. **C114 完整频道**：rss_news_{17,18,21,24,27,38,51,162,489,518,522,549,550,551,552}.xml 均同构可用，当前接入 489(要闻)+518(政策)即可。
