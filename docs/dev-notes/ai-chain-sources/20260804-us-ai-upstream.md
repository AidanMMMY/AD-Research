# 20260804 美国 AI 产业链上游资讯源搜罗（半导体/硬件/数据中心/能源/政策/云）

- 日期：2026-08-04
- 范围：美国 AI 产业链**最上游信号**——半导体工艺/设备、GPU 供应链、数据中心建设、电力能源、出口管制与政策、云厂商 AI 基建
- 方法：每个候选源均 `curl -sL --max-time 15~25` 实测 RSS；403/000 用 `Mozilla/5.0` UA 重试；部分死链接从官网首页抓 `<link rel="alternate">` autodiscovery；本机网络对 substack/部分站点 DNS 抽风的用 WebFetch 二次验证
- 排重：全部 slug 与存量 1012 源（/tmp/adresearch-build/existing_sources.txt）grep 排重，剔除 5 个存量：`thenewstack`、`msft_research`、`infoq_ai`(存量 `global_infoq_en`)、`doe_news`(存量 `ofc_doe`)、`merics`(存量 `gind_merics`)
- 存量已覆盖（本轮不再收录）：`ofc_semianalysis`、`asen_semiengineering`、`asen_eetimes`、`asen_servethehome`、`asen_techpowerup`、`asen_tomshardware`、`asen_wccftech`、`gind_chipsandcheese`、`gind_fabricatedknowledge`、`asen_semiwiki`、`ofc_semidigest`、`asen_utilitydive`、`asen_canarymedia`、`ofc_eia`、`asen_powermag`、`ofc_bisspeeches`、`ofc_whitehouse`、`global_aws_blog`、`global_nvidia_blog`、`global_nvidia_dev`、`global_meta_engineering`、`gind_theregister`、`gind_chinatalk`、`ofc_techcrunch`、`global_arstechnica` 等

## 一、实测通过 ✅（43 个）

| source_slug | 显示名 | 站点 URL | RSS URL | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| trendforce | TrendForce 集邦 | https://www.trendforce.com | https://www.trendforce.com/news/feed/ ✅ | en | 供应链 | 产业研究新闻 | DRAM/HBM/NAND 报价与产能、代工稼动率，半导体周期最灵敏一手信号 |
| digitimes | DIGITIMES（免费日更 feed） | https://www.digitimes.com | https://www.digitimes.com/rss/daily.xml ✅（需 UA） | en | 供应链 | 供应链新闻 | 台系代工/封测/PCB/组装链日报，CoWoS 产能与 GPU 出货领先指标 |
| micron_pr | Micron 投资者新闻稿 | https://investors.micron.com | https://investors.micron.com/rss/news-releases.xml ✅（需 UA） | en | 供应链 | 官方 PR | HBM 供货协议/扩产公告第一落点，AI 存储纯度最高 |
| lamresearch_pr | Lam Research 新闻室 | https://newsroom.lamresearch.com | https://newsroom.lamresearch.com/press-releases?pagetemplate=rss ✅ | en | 半导体 | 官方 PR | 刻蚀/沉积设备龙头动向，WFE 资本开支先行指标 |
| intel_newsroom | Intel Newsroom | https://newsroom.intel.com | https://newsroom.intel.com/feed ✅ | en | 半导体 | 官方博客+PR | 18A 工艺/代工业务/Gaudi 进展，美国本土制造政策受益度 |
| arm_newsroom | Arm Newsroom | https://newsroom.arm.com | https://newsroom.arm.com/news/feed/ ✅ | en | 半导体 | 官方 PR | CSS/Neoverse 数据中心渗透，ARM vs x86 份额战信号 |
| semiconductor_digest | Semiconductor Digest | https://www.semiconductor-digest.com | https://www.semiconductor-digest.com/feed/ ✅ | en | 半导体 | 行业杂志 | 先进封装/晶圆厂建设/设备材料新闻，补 SemiEngineering 之外的美国视角 |
| stratechery | Stratechery | https://stratechery.com | https://stratechery.com/feed/ ✅ | en | 半导体 | 深度分析 | Ben Thompson 对 NVDA/TSMC/出口管制的战略解读，定价权分析标杆 |
| morethanmoore | More than Moore（Ian Cutress） | https://morethanmoore.substack.com | https://morethanmoore.substack.com/feed ✅(WebFetch 验证；本机 substack DNS 抽风） | en | 半导体 | 深度分析 | 前 AnandTech 主编的芯片架构/路线图拆解，技术尽调级 |
| thechipletter | The Chip Letter | https://thechipletter.substack.com | https://thechipletter.substack.com/feed ✅(WebFetch 验证） | en | 半导体 | 深度分析 | 芯片产业史+架构演变长文，理解技术路线竞争的背景库 |
| phoronix | Phoronix | https://www.phoronix.com | https://www.phoronix.com/rss.php ✅ | en | 半导体 | 硬件测评新闻 | Linux 下 GPU/CPU 实测与驱动进展，AMD/Intel 数据中心芯片早期信号 |
| igorslab | Igor's Lab（英文版） | https://www.igorslab.de/en | https://www.igorslab.de/en/feed/ ✅ | en | 半导体 | 硬件拆解 | GPU 供电/散热/良率猛料，显卡卡脖子环节（供电/PCB）一手拆机 |
| eejournal | EE Journal | https://www.eejournal.com | https://www.eejournal.com/feed/ ✅ | en | 半导体 | 行业媒体 | FPGA/EDA/芯片设计生态，补 EDA 双巨头（SNPS/CDNS）信号 |
| 3dincites | 3D InCites | https://3dincites.com | https://3dincites.com/feed/ ✅ | en | 半导体 | 行业媒体 | 先进封装/Chiplet/异构集成垂直社区，CoWoS 产业链毛细血管 |
| datacenterknowledge | Data Center Knowledge | https://www.datacenterknowledge.com | https://www.datacenterknowledge.com/rss.xml ✅ | en | 数据中心 | 行业新闻 | DC 建设/并购/电力交易一线报道，AI capex 落地最强跟踪器 |
| uptime_journal | Uptime Institute Journal | https://journal.uptimeinstitute.com | https://journal.uptimeinstitute.com/feed/ ✅ | en | 数据中心 | 行业研究 | DC 可靠性/供电架构/液冷标准制定者，行业标准风向标 |
| fierce_network | Fierce Network | https://www.fierce-network.com | https://www.fierce-network.com/rss.xml ✅ | en | 数据中心 | 行业新闻 | 光通信/宽带/电信基建，AI 集群网络（光模块/DCI）需求侧信号 |
| capacitymedia | Capacity Media | https://www.capacitymedia.com | https://www.capacitymedia.com/rss ✅ | en | 数据中心 | 行业新闻 | 海缆/互联/批发带宽市场，全球 DC 互联投资地图 |
| rcrwireless | RCR Wireless | https://www.rcrwireless.com | https://www.rcrwireless.com/feed ✅ | en | 数据中心 | 行业新闻 | 5G/边缘/私有网络，边缘 AI 与电信侧算力部署 |
| datacenterpost | Data Center POST | https://datacenterpost.com | https://datacenterpost.com/feed/ ✅ | en | 数据中心 | 行业新闻 | DC 运营商/REIT 动态，Equinix/DLR 产业链生态位 |
| cloudflare_blog | Cloudflare Blog | https://blog.cloudflare.com | https://blog.cloudflare.com/rss/ ✅ | en | 数据中心 | 工程博客 | 全球流量/边缘网络工程实录，AI 推理流量分布的独特数据源 |
| siliconangle | SiliconANGLE | https://siliconangle.com | https://siliconangle.com/feed ✅ | en | 数据中心 | 科技新闻 | 企业基础设施/芯片/云新闻量大，theCUBE 访谈有管理层原声 |
| networkworld | Network World | https://www.networkworld.com | https://www.networkworld.com/feed/ ✅ | en | 数据中心 | 行业媒体 | 企业网络/以太网 vs InfiniBand 之争，AI 后端网络标准演进 |
| heatmap | Heatmap News | https://heatmap.news | https://heatmap.news/feeds/feed.rss ✅ | en | 能源 | 深度新闻 | "AI 用电"专题跟踪最狠的媒体，DC 抢电/电网排队/核电 PPA 前线 |
| latitudemedia | Latitude Media | https://www.latitudemedia.com | https://www.latitudemedia.com/feed/ ✅ | en | 能源 | 深度新闻 | 能源转型×AI 交叉选题，DC 供电瓶颈与新型电力交易 |
| rtoinsider | RTO Insider | https://www.rtoinsider.com | https://www.rtoinsider.com/feed/ ✅ | en | 能源 | 行业新闻 | PJM/ERCOT 等电力市场容量拍卖与并网排队，DC 电价政策直接信号 |
| energystorage_news | Energy Storage News | https://www.energy-storage.news | https://www.energy-storage.news/feed/ ✅ | en | 能源 | 行业新闻 | 储能/电网级电池，DC 备用电源与电网缓冲技术路线 |
| pvmagazine_usa | pv magazine USA | https://pv-magazine-usa.com | https://pv-magazine-usa.com/feed/ ✅ | en | 能源 | 行业新闻 | 美国光伏+储能装机，AI 用电催生的新能源购电结构 |
| berkeley_lab | Berkeley Lab News | https://newscenter.lbl.gov | https://newscenter.lbl.gov/feed/ ✅ | en | 能源 | 官方研究 | 劳伦斯伯克利实验室并网排队报告（DC 并网数据源）发布方 |
| nist_news | NIST News | https://www.nist.gov | https://www.nist.gov/news-events/news/rss.xml ✅ | en | 政策 | 政府官方 | AI 安全/芯片计量/标准制定，联邦 AI 监管的技术底座 |
| csis | CSIS | https://www.csis.org | https://www.csis.org/rss.xml ✅ | en | 政策 | 智库分析 | 出口管制/芯片战争核心智库，Wadhwani AI 中心直接解读 BIS 规则 |
| cset | Georgetown CSET | https://cset.georgetown.edu | https://cset.georgetown.edu/rss/ ✅ | en | 政策 | 智库研究 | AI 算力/人才/出口管制数据最硬的学术智库，政策量化分析 |
| rhodium | Rhodium Group | https://rhg.com | https://rhg.com/feed/ ✅ | en | 政策 | 智库研究 | 中美投资双向流动/对华限制经济影响测算，跨境资本视角 |
| itif | ITIF | https://itif.org | https://itif.org/feed/ ✅ | en | 政策 | 智库分析 | 产业政策/芯片法案/创新竞争力，偏产业界立场的政策解读 |
| aws_hpc | AWS HPC Blog | https://aws.amazon.com/blogs/hpc | https://aws.amazon.com/blogs/hpc/feed/ ✅ | en | 云 | 工程博客 | Trainium/EFA/集群架构官方技术细节，AWS AI 基建路线图 |
| azure_blog | Azure Blog | https://azure.microsoft.com/en-us/blog | https://azure.microsoft.com/en-us/blog/feed/ ✅ | en | 云 | 官方博客 | Azure AI 基建/Maia 芯片/GB200 部署，微软 capex 落地口径 |
| google_cloud_blog | Google Cloud Blog | https://cloudblog.withgoogle.com | https://cloudblog.withgoogle.com/rss/ ✅ | en | 云 | 官方博客 | TPU/Axion/基建公告，谷歌 AI 基建与模型协同信号 |
| openai_blog | OpenAI Blog | https://openai.com/blog | https://openai.com/blog/rss.xml ✅ | en | 云 | 官方博客 | 需求侧最大单一变量：模型发布+Stargate 等算力承诺第一落点 |
| deepmind_blog | Google DeepMind Blog | https://deepmind.google | https://deepmind.google/blog/rss.xml ✅ | en | 云 | 官方博客 | Gemini/TPU 协同演进，谷歌模型-芯片垂直整合进度 |
| google_research | Google Research Blog | https://research.google/blog | https://research.google/blog/rss/ ✅ | en | 云 | 研究博客 | 模型效率/硬件协同设计论文解读，算法降本对算力需求的对冲信号 |
| huggingface_blog | Hugging Face Blog | https://huggingface.co/blog | https://huggingface.co/blog/feed.xml ✅ | en | 云 | 工程博客 | 开源模型生态与推理部署趋势，GPU 需求结构的草根指标 |
| databricks_blog | Databricks Blog | https://www.databricks.com | https://www.databricks.com/feed ✅ | en | 云 | 工程博客 | 企业 AI 落地/数据平台，AI 从训练到推理工作负载迁移观察 |
| lambda_blog | Lambda Blog | https://lambda.ai/blog | https://lambda.ai/blog/rss.xml ✅ | en | 云 | 工程博客 | GPU 云二线厂商视角，现货 GPU 供需/租赁价格敏感度 |

## 二、实测未通过 ❌（反爬拦截或无公开 feed，留档备查）

| source_slug | 显示名 | 站点 URL | RSS URL（测试结果） | 语言 | 环节 | 内容类型 | 投资相关性 |
|---|---|---|---|---|---|---|---|
| videocardz | VideoCardz | https://videocardz.com | https://videocardz.com/feed ❌ 403（三种 UA 均拦，Cloudflare；浏览器可用） | en | 半导体 | 硬件爆料 | GPU/显卡新品泄露最快，消费级 GPU 需求与价格前瞻 |
| hpcwire | HPCwire | https://www.hpcwire.com | https://www.hpcwire.com/feed/ ❌ 403（反爬；需 Jina/浏览器） | en | 数据中心 | 行业新闻 | 超算/AI 集群采购与部署，政府超算订单信号 |
| aiwire | AIwire（HPCwire 子站） | https://www.aiwire.net | 301→hpcwire.com/aiwire/feed/ ❌ 403（同被拦） | en | 数据中心 | 行业新闻 | 企业 AI 基建案例库 |
| nextplatform | The Next Platform | https://www.nextplatform.com | https://www.nextplatform.com/feed/ ❌ 200 但返回 PoW 人机验证页（Labrador） | en | 数据中心 | 深度分析 | 数据中心芯片/系统经济性分析标杆，AI 基建 TCO 测算必看 |
| blocksandfiles | Blocks and Files | https://blocksandfiles.com | https://blocksandfiles.com/feed ❌ 200 但返回 PoW 人机验证页 | en | 供应链 | 行业新闻 | 存储（HDD/SSD/HBM）供应链，希捷/西数/美光竞争格局 |
| insidehpc | insideHPC | https://insidehpc.com | https://insidehpc.com/feed/ ❌ 000（连接持续失败） | en | 数据中心 | 行业新闻 | HPC/AI 集群生态新闻聚合 |
| datacenterdynamics | Data Center Dynamics (DCD) | https://www.datacenterdynamics.com | /en/rss/ 与 /feed/ ❌ 403（Cloudflare；DC 行业第一媒体，值得浏览器接入） | en | 数据中心 | 行业新闻 | 全球 DC 建设/电力/并购头号媒体，AI capex 跟踪核心 |
| datacenterfrontier | Data Center Frontier | https://www.datacenterfrontier.com | https://www.datacenterfrontier.com/rss/ ❌ 403（Cloudflare；需 Jina） | en | 数据中心 | 深度报道 | hyperscale DC 选址/电力交易深度报道，美国 DC 地产最前线 |
| sdxcentral | SDxCentral | https://www.sdxcentral.com | https://www.sdxcentral.com/feed/ ❌ 403 | en | 数据中心 | 行业新闻 | 网络虚拟化/边缘/AI 基建软件栈 |
| lightreading | Light Reading | https://www.lightreading.com | https://www.lightreading.com/feed ❌ 403 | en | 数据中心 | 行业新闻 | 电信运营商 capex 与光网络，AI 流量的承载侧 |
| dgtlinfra | Dgtl Infra | https://dgtlinfra.com | https://dgtlinfra.com/feed/ ❌ 403/ECONNRESET（Cloudflare；内容极对口，强烈建议浏览器/Jina 接入） | en | 数据中心 | 深度分析 | 数字基建（DC/光纤/电塔）投资分析，PE 视角的 DC 估值框架 |
| datacentremag | Data Centre Magazine | https://datacentremagazine.com | https://datacentremagazine.com/feed ❌ 403/000 | en | 数据中心 | 行业杂志 | DC 运营商排名与项目盘点 |
| baxtel | Baxtel | https://baxtel.com | https://baxtel.com/rss ❌ 404（未找到公开 feed） | en | 数据中心 | 数据目录 | DC 设施数据库，site 级情报 |
| allaboutcircuits | All About Circuits | https://www.allaboutcircuits.com | https://www.allaboutcircuits.com/rss/ ❌ 403 | en | 半导体 | 技术媒体 | 模拟/功率半导体，AI 电源管理链 |
| guru3d | Guru3D | https://www.guru3d.com | https://www.guru3d.com/rss/ ❌ 403 | en | 半导体 | 硬件测评 | GPU 实测数据，产品力对比 |
| electronicsweekly | Electronics Weekly | https://www.electronicsweekly.com | https://www.electronicsweekly.com/feed/ ❌ 403 | en | 半导体 | 行业新闻 | 欧洲视角半导体分销/元器件 |
| thememoryguy | The Memory Guy（Jim Handy） | https://thememoryguy.com | https://thememoryguy.com/feed/ ❌ 403（Wordfence） | en | 供应链 | 深度分析 | 存储行业最资深独立分析师，NAND/DRAM/HBM 周期判断 |
| counterpoint | Counterpoint Research | https://www.counterpointresearch.com | /feed/ ❌ 404；/insights/feed/ 200 但为 SPA HTML（未找到公开 feed） | en | 供应链 | 产业研究 | 晶圆代工/手机/AI 终端份额数据，官网无 RSS 需邮件订阅或抓取 |
| yole | Yole Group | https://www.yolegroup.com | https://www.yolegroup.com/feed/ ❌ 403/202（未找到公开 feed） | en | 供应链 | 产业研究 | 先进封装/功率半导体市场结构权威 |
| omdia | Omdia | https://omdia.tech.informa.com | https://omdia.tech.informa.com/rss ❌ 403/000（未找到公开 feed） | en | 供应链 | 产业研究 | 显示/半导体/云 IT 支出预测 |
| techinsights | TechInsights | https://www.techinsights.com | /blog/rss.xml ❌ 404；/rss ❌ 404（未找到公开 feed） | en | 供应链 | 拆解分析 | 芯片 teardown/工艺节点鉴定（华为芯片事件主角），官网无 RSS |
| semi_org | SEMI 行业协会 | https://www.semi.org | /en/rss ❌ 403；/en/rss.xml ❌ 403 | en | 供应链 | 协会官方 | 设备出货额（BB 值）/晶圆厂预测发布方 |
| semiconductor_today | Semiconductor Today | https://semiconductor-today.com | rss.xml ❌ 404；news_rss.php ❌ 404 | en | 半导体 | 行业新闻 | 化合物半导体/光电子 |
| compoundsemi | Compound Semiconductor | https://compoundsemiconductor.net | /rss ❌ 404（未找到公开 feed） | en | 半导体 | 行业杂志 | SiC/GaN 功率半导体，AI 电源链上游 |
| microgrid_knowledge | Microgrid Knowledge | https://www.microgridknowledge.com | https://www.microgridknowledge.com/feed ❌ 403 | en | 能源 | 行业新闻 | DC 自发电/微电网，离网供电方案 |
| lightwave | Lightwave | https://www.lightwaveonline.com | https://www.lightwaveonline.com/rss ❌ 403 | en | 数据中心 | 行业新闻 | 光通信/光模块垂直媒体 |
| powergrid_intl | POWERGRID International | https://www.power-grid.com | https://www.power-grid.com/feed/ ❌ 403 | en | 能源 | 行业新闻 | 输配电设备，电网扩容瓶颈（变压器交期） |
| tdworld | T&D World | https://www.tdworld.com | https://www.tdworld.com/rss.xml ❌ 403 | en | 能源 | 行业新闻 | 输配电工程，DC 并网工程视角 |
| epri | EPRI | https://www.epri.com | /rss 与 /rss.xml ❌ 200 但返回 SPA HTML（无公开 feed） | en | 能源 | 研究院官方 | DC 用电预测报告（"Powering AI"）发布方，只能抓网页 |
| rmi | RMI 落基山研究所 | https://rmi.org | /feed/ 与 /rss.xml ❌ 200 但返回 HTML（无公开 feed） | en | 能源 | 智库研究 | 清洁能源+DC 选址研究 |
| lawfare | Lawfare | https://www.lawfaremedia.org | https://www.lawfaremedia.org/rss.xml ❌ 403（Cloudflare） | en | 政策 | 法律分析 | 出口管制/对外投资限制的法律细节拆解 |
| brookings | Brookings | https://www.brookings.edu | /feed/ 与 /articles/feed/ ❌ 200 但返回 HTML（无公开 feed） | en | 政策 | 智库分析 | AI 治理/产业政策 |
| federalregister_ai | Federal Register（AI 检索 feed） | https://www.federalregister.gov | documents/search.rss?conditions[term]=... ❌ 302 到 unblock 页（bot wall）；有官方 API 可替代 | en | 政策 | 政府文件 | BIS 规则/行政命令原文第一落点，建议改走 API |
| cisa_alerts | CISA Alerts | https://www.cisa.gov | https://www.cisa.gov/uscert/ncas/alerts.xml ❌ 403（边缘拦截 curl/Googlebot，feed 本身存在，需服务器 IP 复测） | en | 政策 | 政府官方 | 关键基础设施网络安全告警 |
| ferc_news | FERC 新闻稿 | https://www.ferc.gov | https://www.ferc.gov/rss/news.xml ❌ 403（gov 边缘拦截） | en | 能源 | 政府官方 | 电力批发市场监管，DC 购电政策 |
| commerce_gov | 美国商务部新闻 | https://www.commerce.gov | /news/press-releases/rss ❌ 403（gov 边缘拦截） | en | 政策 | 政府官方 | 芯片法案拨款/出口管制声明（BIS 上级） |
| nerc_news | NERC 新闻室 | https://www.nerc.com | nerc.com/rss ❌ 403 | en | 能源 | 政府官方 | 电网可靠性评估，DC 负荷冲击报告 |
| anthropic | Anthropic News | https://www.anthropic.com/news | 首页无 feed autodiscovery；rss.xml/feed.xml/news/rss.xml ❌ 均 404 | en | 云 | 官方博客 | 模型竞争格局关键一方，只能抓网页 |
| broadcom_blog | Broadcom | https://www.broadcom.com | /blog/rss ❌ 404；/company/news/rss ❌ 404（未找到公开 feed） | en | 半导体 | 官方 PR | 定制 ASIC（XPU）+网络芯片双主线，AI 芯片第二极 |
| asml_news | ASML | https://www.asml.com | /en/news/rss ❌ 404；/en/news/press-releases/rss ❌ 404（未找到公开 feed） | en | 半导体 | 官方 PR | EUV 光刻垄断者，出口管制最大单一标的 |
| tsmc_blog | TSMC | https://www.tsmc.com | blog.tsmc.com DNS NXDOMAIN；官网无 feed | en | 半导体 | 官方 | 代工之王无官方 RSS，只能抓 IR 页/法说会 |
| amd_blog | AMD | https://www.amd.com | community.amd.com 为论坛无简单 feed；/en/blogs 无 autodiscovery ❌ | en | 半导体 | 官方 | MI 系列 GPU 官方动态只能抓网页 |
| appliedmaterials_blog | Applied Materials | https://www.appliedmaterials.com | /us/en/blog/rss.xml ❌ 403 | en | 半导体 | 官方博客 | 设备龙头技术博客 |
| qualcomm_blog | Qualcomm | https://www.qualcomm.com | /news/onq/rss ❌ 404 | en | 半导体 | 官方 PR | 边缘 AI/手机 SoC |
| nxp_blog | NXP | https://www.nxp.com | /company/about-nxp/rss ❌ 404 | en | 半导体 | 官方 PR | 车用/边缘芯片 |
| oracle_cloud_infra | Oracle Cloud Infrastructure Blog | https://blogs.oracle.com/cloud-infrastructure | /cloud-infrastructure/rss 与 /rss ❌ 403（Akamai 拦截） | en | 云 | 工程博客 | OCI 超算集群/GPU 云，Oracle AI capex 口径 |
| coreweave_blog | CoreWeave Blog | https://www.coreweave.com/blog | https://www.coreweave.com/blog/rss ❌ 403（Cloudflare） | en | 云 | 官方博客 | 最大独立 GPU 云，NVDA 生态绑定度 |

## 三、Top 20 必接（按投资信号优先级）

| # | slug | 理由 |
|---|---|---|
| 1 | trendforce | HBM/DRAM 报价与产能，半导体周期最灵敏指标，直接影响 Micron/SK 海力士/三星判断 |
| 2 | digitimes | 台系供应链日报，CoWoS/代工稼动率，NVDA 出货领先指标（需 UA 取 feed） |
| 3 | datacenterknowledge | 美国 DC 建设/电力交易/并购一线，AI capex 落地最强跟踪器 |
| 4 | micron_pr | HBM 官方公告第一落点，AI 存储最纯标的 |
| 5 | heatmap | "AI 抢电"报道最狠，电力瓶颈主题核心源 |
| 6 | datacenterfrontier | ❌ 403 但内容不可替代——hyperscale 选址/购电深度报道，建议 Jina/浏览器接入 |
| 7 | datacenterdynamics | ❌ 403 但为 DC 行业第一媒体，建议 Jina/浏览器接入 |
| 8 | nextplatform | ❌ PoW 拦截但为 AI 基建 TCO 分析标杆，建议浏览器接入 |
| 9 | nist_news | 联邦 AI 标准/出口管制技术底座，政策源中 feed 最干净 |
| 10 | csis | 出口管制解读第一智库 |
| 11 | cset | AI 算力政策量化研究，算力管制影响测算 |
| 12 | rhodium | 中美资本流动/对华限制经济影响 |
| 13 | lamresearch_pr | 设备资本开支先行指标官方源 |
| 14 | intel_newsroom | 18A/代工/美国制造政策受益度官方口径 |
| 15 | arm_newsroom | 数据中心 ARM 渗透官方信号 |
| 16 | aws_hpc | AWS AI 基建（Trainium/EFA）官方技术路线 |
| 17 | azure_blog | 微软 AI capex 与 Maia/GB200 部署口径 |
| 18 | google_cloud_blog | TPU/Axion 官方公告，谷歌垂直整合进度 |
| 19 | rtoinsider | PJM/ERCOT 容量拍卖与并网排队，DC 电价与电力政策直接信号 |
| 20 | uptime_journal | DC 可靠性/液冷/供电架构标准风向标 |

候补梯队：openai_blog（需求侧最大变量）、deepmind_blog、semiconductor_digest、stratechery、morethanmoore、siliconangle、latitudemedia、capacitymedia、energystorage_news、fierce_network。

## 四、接入注意事项

1. **需 UA 才能取 feed**：`digitimes`、`micron_pr`——采集器必须带浏览器 UA（平台现有 UA 配置即可）。
2. **substack 源**：`morethanmoore`、`thechipletter` feed 本身有效，本机测试网络对 *.substack.com DNS 抽风导致 curl 000，WebFetch 已验证有效；ECS 上按存量 substack 源同法接入即可。
3. **Cloudflare/反爬拦截但内容高价值**（建议走 Jina 或浏览器渲染通道，注意存量 [[20260801 Jina 余额]] 约束）：datacenterdynamics、datacenterfrontier、nextplatform、hpcwire、blocksandfiles、dgtlinfra、videocardz、lawfare、coreweave、oracle_cloud_infra。
4. **无公开 feed 只能抓网页**：anthropic、broadcom、asml、tsmc、amd、counterpoint、yole、omdia、techinsights、epri、rmi、brookings。
5. **gov 边缘拦截（403）**：cisa/ferc/commerce/nerc feed 本身存在，需从 ECS（非住宅 IP）复测；federalregister 有 bot wall，建议改用其官方 API（https://www.federalregister.gov/developers/documentation/api/v1）。
6. AnadTech 已于 2024-08 停更，不收录；其精神续作为 `morethanmoore`（已收录）。
