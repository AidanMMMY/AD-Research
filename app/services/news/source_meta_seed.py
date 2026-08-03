"""学习中心资讯源打标种子数据（2026-08-02）。

Why this exists
---------------
分析结论（``learning-section-analysis`` §1.1）：平台 ~800 个资讯源中
约 1/3 是深度分析 / 科普教育内容，但与快讯混在同一 feed。本文件把
这些源逐个捞出打标，作为 ``news_source_meta`` 表的种子数据。

打标规则（宁可保守——拿不准的源不打标）
--------------------------------------
* **覆盖范围**：9 个批次表（wechat×3 / zhx / zhb / indie / gind /
  global / asen）+ ``rss_simple`` 单源 + wewe-rss 账号。独立爬虫
  （新华/新浪/财联社/华尔街见闻/财新/CNBC/SEC/cninfo/雪球…）几乎
  全是事实快讯与公告，不打标。
* **content_type**：deep=深度分析/研究，edu=科普教育。
* **topic**：6+1 主题——allocation（资产配置/理财）/ valuation
  （估值方法/公司研究）/ macro（宏观）/ industry（行业研究）/
  psychology（交易心理/行为决策）/ tools（工具教程）/ research
  （兜底深度类）。wechat batch2/3 行内 category 映射：
  macro→macro、strategy→valuation、industry→industry、
  tech/business→research 或 industry 酌定。
* **difficulty_default**：中文科普/理财源=beginner；论文/量化/
  宏观深度=advanced；混合或拿不准=NULL。
* **note** 统一放源的显示名，便于 SQL 维护时辨认。

加载方式：``seed_source_meta(db)`` 幂等（等价 INSERT ... ON CONFLICT
DO NOTHING）；手动入口 ``scripts/seed_news_source_meta.py``。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.news_source_meta import NewsSourceMeta

# (source, content_type, topic, difficulty_default, display_group, note)
# source 与 news_article.source 同值；note 为源显示名。
_SEED_ROWS: list[tuple[str, str, str, str | None, str, str]] = [
    # ────────────────────────────────────────────────────────────────
    # wechat batch1（wechat2rss_batch.py，xlab 镜像）——深度/科普号
    # ────────────────────────────────────────────────────────────────
    ("wechat_jisilu", "deep", "allocation", None, "公众号", "集思录（低风险投资社区）"),
    ("wechat_changying", "deep", "allocation", "beginner", "公众号", "长赢指数投资（ETF拯救世界）"),
    ("wechat_yetanqian", "edu", "allocation", "beginner", "公众号", "也谈钱（FIRE/理财）"),
    ("wechat_dingtou", "edu", "allocation", "beginner", "公众号", "从零开始定投日记"),
    ("wechat_luojijingji", "deep", "macro", None, "公众号", "逻辑与现实经济"),
    ("wechat_shugongfuli", "deep", "research", None, "公众号", "数工复利（数据/量化投资随笔）"),
    ("wechat_tiaodongjisuanqi", "deep", "research", None, "公众号", "跳动的计算器（投资数据分析）"),
    # ────────────────────────────────────────────────────────────────
    # wewe-rss 账号（WECHAT_RSS_FEED_MAP，独立深度号）
    # ────────────────────────────────────────────────────────────────
    ("wechat_zhigu", "deep", "macro", None, "公众号", "智谷趋势"),
    ("wechat_yuanchuan", "deep", "industry", None, "公众号", "远川研究所"),
    ("wechat_canghai", "deep", "macro", "advanced", "公众号", "沧海一土狗（宏观/债券）"),
    ("wechat_fupeng", "deep", "macro", "advanced", "公众号", "付鹏的财经世界"),
    ("wechat_lixunlei", "deep", "macro", "advanced", "公众号", "李迅雷金融与投资"),
    ("wechat_congming", "deep", "valuation", None, "公众号", "聪明投资者（投资访谈）"),
    ("wechat_latepost", "deep", "industry", None, "公众号", "晚点LatePost（商业深度报道）"),
    # wechat_zeping 是未配置 feed map 时的兜底 source 名（泽平宏观，
    # 与 batch2 wechat_zepinghongguan 同一账号，两个 source 都打标）。
    ("wechat_zeping", "deep", "macro", None, "公众号", "泽平宏观（单源兜底）"),
    # ────────────────────────────────────────────────────────────────
    # wechat batch2（WECHAT2B_FEEDS）——macro/strategy 类几乎全部、
    # industry/business 类的深度号；tech 类与纯新闻媒体保守跳过。
    # ────────────────────────────────────────────────────────────────
    # macro 类（剔除 财经早餐/一财/每经/券商中国 等快讯媒体）
    ("wechat_zepinghongguan", "deep", "macro", None, "公众号", "泽平宏观"),
    ("wechat_xiangshuai", "deep", "macro", None, "公众号", "香帅的金融江湖"),
    ("wechat_zhongjin", "deep", "macro", "advanced", "公众号", "中金点睛"),
    ("wechat_cf40", "deep", "macro", "advanced", "公众号", "中国金融四十人论坛"),
    ("wechat_worldbank", "deep", "macro", "advanced", "公众号", "世界银行"),
    ("wechat_yetan", "deep", "macro", None, "公众号", "叶檀财经"),
    ("wechat_econdaily", "deep", "macro", None, "公众号", "一天一篇经济学人"),
    ("wechat_dashuilai", "deep", "macro", None, "公众号", "大水来（宏观随笔）"),
    ("wechat_xiaolinshuo", "edu", "macro", "beginner", "公众号", "小Lin说（财经科普）"),
    # strategy 类 → valuation（估值方法/投研），VC 研究归 research
    ("wechat_dianshi", "deep", "valuation", None, "公众号", "点拾投资（基金经理访谈/方法论）"),
    ("wechat_luosiding", "edu", "valuation", "beginner", "公众号", "银行螺丝钉（指数估值科普）"),
    ("wechat_laoqian", "edu", "allocation", "beginner", "公众号", "老钱日日谈（理财科普）"),
    ("wechat_tzshixi", "deep", "research", None, "公众号", "投资实习所（科技/创投研究）"),
    ("wechat_gududanao", "edu", "psychology", "beginner", "公众号", "孤独大脑（思维模型/决策）"),
    ("wechat_sanzhe", "edu", "allocation", "beginner", "公众号", "三折人生（理财/保险科普）"),
    ("wechat_gelan", "deep", "valuation", None, "公众号", "格兰投研"),
    ("wechat_laozhang", "deep", "valuation", None, "公众号", "老张投研"),
    ("wechat_haitun", "deep", "research", None, "公众号", "海豚研究（公司/行业研究）"),
    ("wechat_fengrui", "deep", "research", None, "公众号", "峰瑞资本（创投研究）"),
    ("wechat_gaoling", "deep", "research", None, "公众号", "高瓴创投"),
    ("wechat_jingwei", "deep", "research", None, "公众号", "经纬创投"),
    ("wechat_zhenge", "deep", "research", None, "公众号", "真格基金"),
    ("wechat_hongshan", "deep", "research", None, "公众号", "红杉汇"),
    ("wechat_shanxing", "deep", "research", None, "公众号", "山行资本"),
    ("wechat_etfjinhua", "edu", "allocation", "beginner", "公众号", "ETF进化论（指数基金科普）"),
    # industry 类（剔除 运营研究社/见实/梅斯医学/浪潮 等弱相关）
    ("wechat_bandaoti", "deep", "industry", None, "公众号", "半导体行业观察"),
    ("wechat_zhidongxi", "deep", "industry", None, "公众号", "智东西（AI/硬科技产业）"),
    ("wechat_jiazi", "deep", "industry", None, "公众号", "甲子光年（科技产业研究）"),
    ("wechat_daofa", "deep", "industry", None, "公众号", "刀法研究所（消费品牌）"),
    ("wechat_zhaibo", "deep", "industry", None, "公众号", "窄播（消费/零售）"),
    ("wechat_xinbang", "deep", "industry", None, "公众号", "新榜（内容产业数据）"),
    ("wechat_deeptech", "deep", "industry", None, "公众号", "DeepTech深科技"),
    ("wechat_naojiti", "deep", "industry", None, "公众号", "脑极体（科技评论）"),
    ("wechat_saasbyx", "deep", "industry", None, "公众号", "SaaS白夜行"),
    # tech 类酌定：只保留研究/产业属性强的
    ("wechat_sota", "deep", "research", "advanced", "公众号", "机器之心SOTA模型（AI研究）"),
    ("wechat_caoz", "deep", "industry", None, "公众号", "caoz的梦呓（互联网商业评论）"),
    ("wechat_guaidao", "deep", "industry", None, "公众号", "互联网怪盗团（互联网公司分析）"),
    ("wechat_baijing", "deep", "industry", None, "公众号", "白鲸出海（出海产业）"),
    ("wechat_hwunicorn", "deep", "research", None, "公众号", "海外独角兽（科技公司/创投研究）"),
    ("wechat_wadianai", "deep", "industry", None, "公众号", "晚点AI（AI商业深度报道）"),
    # business 类
    ("wechat_dailaoban", "deep", "industry", None, "公众号", "饭统戴老板（商业深度）"),
    ("wechat_wuxiaobo", "deep", "research", None, "公众号", "吴晓波频道（财经商业评论）"),
    ("wechat_liurun", "edu", "research", "beginner", "公众号", "刘润（商业洞察科普）"),
    ("wechat_bijixia", "edu", "research", "beginner", "公众号", "笔记侠（商业知识笔记）"),
    ("wechat_lishi", "deep", "research", None, "公众号", "砺石商业评论（企业案例）"),
    ("wechat_hbr", "deep", "research", None, "公众号", "哈佛商业评论"),
    ("wechat_pedaily", "deep", "research", None, "公众号", "投资界（VC/PE 深度）"),
    ("wechat_anyong", "deep", "research", None, "公众号", "暗涌Waves（创投深度）"),
    ("wechat_jiubian", "deep", "macro", "beginner", "公众号", "九边（通俗政经长文）"),
    # ────────────────────────────────────────────────────────────────
    # wechat batch3（WECHAT3_FEEDS，22 个；tech/business 新闻类跳过）
    # ────────────────────────────────────────────────────────────────
    ("wechat_diqiuzhishiju", "edu", "macro", "beginner", "公众号", "地球知识局（地缘/资源科普）"),
    ("wechat_lxiansheng", "edu", "psychology", "beginner", "公众号", "L先生说（认知/学习心理学）"),
    ("wechat_dalirushan", "deep", "industry", None, "公众号", "大力如山（金融行业观察）"),
    ("wechat_xingqiuyanjiusuo", "edu", "industry", "beginner", "公众号", "星球研究所（地理/城市/工程科普）"),
    ("wechat_feifanchanyan", "deep", "industry", None, "公众号", "非凡产研（产业研究）"),
    ("wechat_youxiputao", "deep", "industry", None, "公众号", "游戏葡萄（游戏行业）"),
    ("wechat_houlang", "deep", "industry", None, "公众号", "后浪研究所（消费趋势）"),
    ("wechat_guigu101", "deep", "industry", None, "公众号", "硅谷101（科技商业深度）"),
    ("wechat_luanfanshu", "deep", "industry", None, "公众号", "乱翻书（互联网商业访谈）"),
    # ────────────────────────────────────────────────────────────────
    # 中文播客 zhx_*（ZH_MULTI_FEEDS，40 个；文化/娱乐类跳过）
    # ────────────────────────────────────────────────────────────────
    ("zhx_zhixingjiuguan", "edu", "allocation", "beginner", "中文播客", "知行小酒馆（投资理财对谈）"),
    ("zhx_touzishizhanpai", "deep", "valuation", None, "中文播客", "投资实战派"),
    ("zhx_mancangyihou", "deep", "valuation", None, "中文播客", "满仓以后（投资对谈）"),
    ("zhx_sandianxiaban", "deep", "valuation", None, "中文播客", "三点下班（二级投资）"),
    ("zhx_fengtouquan", "deep", "research", None, "中文播客", "疯投圈（VC/商业分析）"),
    ("zhx_sishierzhangjing", "deep", "research", None, "中文播客", "42章经（创投）"),
    ("zhx_shangyewhyjiang", "deep", "research", None, "中文播客", "商业WHY酱"),
    ("zhx_jinjibocaijing", "deep", "research", None, "中文播客", "进击波财经"),
    ("zhx_xiaomasong", "deep", "industry", None, "中文播客", "小马宋商业观察（营销/消费）"),
    ("zhx_wandianliao", "deep", "industry", None, "中文播客", "晚点聊 LateTalk（商业访谈）"),
    ("zhx_zhaiboyixia", "deep", "industry", None, "中文播客", "窄播一下（消费/零售）"),
    ("zhx_shizilukou", "deep", "industry", None, "中文播客", "十字路口Crossing（AI/创业）"),
    ("zhx_chuhaixiangduilun", "deep", "industry", None, "中文播客", "出海相对论"),
    ("zhx_equalocean", "deep", "industry", None, "中文播客", "EqualOcean（出海研究）"),
    ("zhx_xiaofeixinzhi", "deep", "industry", None, "中文播客", "消费新知"),
    ("zhx_dongyaguanchaju", "deep", "macro", None, "中文播客", "东亚观察局（国际政经）"),
    ("zhx_gooaye", "deep", "valuation", None, "中文播客", "股癌 Gooaye（股市评论）"),
    ("zhx_zhaohuaguhuozai", "deep", "valuation", None, "中文播客", "兆華與股惑仔"),
    ("zhx_gushiyinzhe", "deep", "valuation", None, "中文播客", "股市隱者"),
    ("zhx_caibaogou", "deep", "valuation", None, "中文播客", "財報狗（财报分析）"),
    ("zhx_bubaijiaozhu", "edu", "allocation", "beginner", "中文播客", "不敗教主陳重銘（理财）"),
    ("zhx_touzihaishenme", "edu", "allocation", "beginner", "中文播客", "投資嗨什麼（投资科普）"),
    ("zhx_xiabanjingjixue", "edu", "macro", "beginner", "中文播客", "下班經濟學（财经科普）"),
    ("zhx_caijinghaojiao", "deep", "macro", None, "中文播客", "游庭皓的財經皓角（宏观）"),
    ("zhx_mindixuandu", "edu", "macro", "beginner", "中文播客", "敏迪選讀（国际政经解读）"),
    ("zhx_mguandian", "deep", "industry", None, "中文播客", "M觀點（商业科技分析）"),
    # ────────────────────────────────────────────────────────────────
    # 中文博客 zhb_*（ZH_BLOG_FEEDS，38 个；技术博客/V2EX/媒体跳过）
    # ────────────────────────────────────────────────────────────────
    ("zhb_xueqiuhots", "deep", "research", None, "中文博客", "雪球热帖（投资社区精选）"),
    ("zhb_ftchinese", "deep", "macro", None, "中文博客", "FT中文网（评论/深度）"),
    ("zhb_it199", "deep", "industry", None, "中文博客", "199IT（行业数据报告聚合）"),
    # ────────────────────────────────────────────────────────────────
    # 英文独立源 indie_*（INDEPENDENT_FEEDS；技术/文化/生活类跳过）
    # ────────────────────────────────────────────────────────────────
    ("indie_collabfund", "deep", "psychology", None, "英文独立源", "Collaborative Fund (Morgan Housel，投资行为)"),
    ("indie_stratechery", "deep", "industry", "advanced", "英文独立源", "Stratechery（科技战略分析）"),
    ("indie_notboring", "deep", "industry", None, "英文独立源", "Not Boring（科技商业）"),
    ("indie_generalist", "deep", "industry", None, "英文独立源", "The Generalist（科技商业深度）"),
    ("indie_lynalden", "deep", "macro", "advanced", "英文独立源", "Lyn Alden（宏观深度）"),
    ("indie_alphaarchitect", "deep", "research", "advanced", "英文独立源", "Alpha Architect（量化/因子研究）"),
    ("indie_priceactionlab", "deep", "research", "advanced", "英文独立源", "Price Action Lab（量化交易）"),
    ("indie_abnormalreturns", "deep", "research", None, "英文独立源", "Abnormal Returns（投资精选/评论）"),
    ("indie_financialsamurai", "edu", "allocation", "beginner", "英文独立源", "Financial Samurai（理财）"),
    ("indie_earlyretirementnow", "edu", "allocation", "beginner", "英文独立源", "Early Retirement Now（FIRE）"),
    ("indie_farnamstreet", "edu", "psychology", "beginner", "英文独立源", "Farnam Street（思维模型）"),
    ("indie_investmentmoats", "edu", "allocation", "beginner", "英文独立源", "Investment Moats（SG 理财）"),
    ("indie_financialhorse", "edu", "allocation", "beginner", "英文独立源", "Financial Horse（SG 理财）"),
    ("indie_madfientist", "edu", "allocation", "beginner", "英文独立源", "Mad Fientist（FIRE）"),
    ("indie_physicianonfire", "edu", "allocation", "beginner", "英文独立源", "Physician on FIRE"),
    ("indie_whitecoatinvestor", "edu", "allocation", "beginner", "英文独立源", "The White Coat Investor"),
    ("indie_obliviousinvestor", "edu", "allocation", "beginner", "英文独立源", "Oblivious Investor"),
    ("indie_retirementmanifesto", "edu", "allocation", "beginner", "英文独立源", "The Retirement Manifesto"),
    ("indie_millennialrevolution", "edu", "allocation", "beginner", "英文独立源", "Millennial Revolution（FIRE）"),
    ("indie_coachcarson", "edu", "allocation", "beginner", "英文独立源", "Coach Carson（房产投资）"),
    ("indie_heisenbergreport", "deep", "macro", "advanced", "英文独立源", "Heisenberg Report（宏观/市场）"),
    ("indie_constructionphysics", "deep", "industry", None, "英文独立源", "Construction Physics（建筑产业）"),
    ("indie_teachablemoment", "edu", "psychology", "beginner", "英文独立源", "A Teachable Moment（投资行为）"),
    ("indie_bellecurve", "edu", "allocation", "beginner", "英文独立源", "The Belle Curve（理财评论）"),
    ("indie_monevator", "edu", "allocation", "beginner", "英文独立源", "Monevator（UK 理财）"),
    ("indie_firevlondon", "edu", "allocation", "beginner", "英文独立源", "FIRE v London"),
    ("indie_rationalreminder", "deep", "allocation", "advanced", "英文独立源", "Rational Reminder（循证投资）"),
    ("indie_investlikethebest", "deep", "research", None, "英文独立源", "Invest Like the Best（投资访谈）"),
    ("indie_chatwithtraders", "deep", "research", None, "英文独立源", "Chat With Traders（交易访谈）"),
    ("indie_mianji", "deep", "allocation", None, "中文播客", "面基（投资理财访谈）"),
    ("indie_luanfanshu", "deep", "industry", None, "中文播客", "乱翻书（播客，互联网商业）"),
    ("indie_zhangxiaojun", "deep", "industry", None, "中文播客", "张小珺Jùn（商业访谈）"),
    ("indie_sv101", "deep", "industry", None, "中文播客", "硅谷101（播客，科技商业深度）"),
    ("indie_beiwanglu", "deep", "industry", None, "中文播客", "贝望录（商业/营销访谈）"),
    # ────────────────────────────────────────────────────────────────
    # 全球独立源 gind_*（GLOBAL_INDIE_FEEDS；政治/技术/安全类跳过）
    # ────────────────────────────────────────────────────────────────
    ("gind_sinocism", "deep", "macro", "advanced", "全球独立源", "Sinocism（中国观察）"),
    ("gind_chinatalk", "deep", "research", None, "全球独立源", "ChinaTalk（中国科技/政策）"),
    ("gind_sinification", "deep", "research", "advanced", "全球独立源", "Sinification（中国政策研究）"),
    ("gind_merics", "deep", "research", "advanced", "全球独立源", "MERICS（中国研究智库）"),
    ("gind_uncharted", "edu", "macro", "beginner", "全球独立源", "Uncharted Territories（地缘经济科普）"),
    ("gind_betonit", "deep", "macro", "advanced", "全球独立源", "Bet On It (Bryan Caplan，经济学评论)"),
    ("gind_commoditycontext", "deep", "macro", "advanced", "全球独立源", "Commodity Context（大宗/能源宏观）"),
    ("gind_volts", "deep", "industry", None, "全球独立源", "Volts（能源转型产业）"),
    ("gind_employamerica", "deep", "macro", "advanced", "全球独立源", "Employ America（宏观政策研究）"),
    ("gind_modeledbehavior", "deep", "macro", "advanced", "全球独立源", "Modeled Behavior（经济评论）"),
    ("gind_yetanothervalueblog", "deep", "valuation", "advanced", "全球独立源", "Yet Another Value Blog（价值投资）"),
    ("gind_alhambra", "deep", "macro", "advanced", "全球独立源", "Alhambra Investments (Jeff Snider)"),
    ("gind_valueplays", "deep", "valuation", None, "全球独立源", "ValuePlays (Todd Sullivan)"),
    ("gind_quantifiableedges", "deep", "research", "advanced", "全球独立源", "Quantifiable Edges（量化交易）"),
    ("gind_smbtraining", "deep", "research", None, "全球独立源", "SMB Capital Trading Blog（交易方法）"),
    ("gind_appeconomy", "deep", "valuation", None, "全球独立源", "App Economy Insights（科技公司财报）"),
    ("gind_asiancenturystocks", "deep", "valuation", None, "全球独立源", "Asian Century Stocks（亚洲股票深度）"),
    ("gind_retirementresearcher", "deep", "allocation", "advanced", "全球独立源", "Retirement Researcher (Wade Pfau)"),
    ("gind_looniedoctor", "edu", "allocation", "beginner", "全球独立源", "Loonie Doctor（CA 理财）"),
    ("gind_wallethacks", "edu", "allocation", "beginner", "全球独立源", "Wallet Hacks"),
    ("gind_esimoney", "edu", "allocation", "beginner", "全球独立源", "ESI Money"),
    ("gind_moneywithkatie", "edu", "allocation", "beginner", "全球独立源", "Money with Katie"),
    ("gind_meaningfulmoney", "edu", "allocation", "beginner", "全球独立源", "Meaningful Money (UK)"),
    ("gind_mrsmummypenny", "edu", "allocation", "beginner", "全球独立源", "Mrs Mummypenny (UK)"),
    ("gind_moneytothemasses", "edu", "allocation", "beginner", "全球独立源", "Money to the Masses (UK)"),
    ("gind_budgetsaresexy", "edu", "allocation", "beginner", "全球独立源", "Budgets Are Sexy"),
    ("gind_exponentialview", "deep", "research", None, "全球独立源", "Exponential View（技术/宏观趋势）"),
    ("gind_benedicttevans", "deep", "industry", "advanced", "全球独立源", "Benedict Evans（科技战略）"),
    ("gind_eladgil", "deep", "research", None, "全球独立源", "Elad Gil（创投）"),
    ("gind_chipsandcheese", "deep", "industry", "advanced", "全球独立源", "Chips and Cheese（半导体技术）"),
    ("gind_fabricatedknowledge", "deep", "industry", "advanced", "全球独立源", "Fabricated Knowledge（半导体产业）"),
    ("gind_unchained", "deep", "research", None, "全球独立源", "Unchained（crypto 深度访谈）"),
    ("gind_bitmexresearch", "deep", "research", "advanced", "全球独立源", "BitMEX Research（crypto 研究）"),
    # ────────────────────────────────────────────────────────────────
    # 全球多语种 global_*（GLOBAL_RSS_FEEDS；媒体/技术类跳过）
    # ────────────────────────────────────────────────────────────────
    ("global_acquirers_multiple", "deep", "valuation", "advanced", "全球媒体", "The Acquirer's Multiple（价值/量化）"),
    ("global_automatic_earth", "deep", "macro", None, "全球媒体", "The Automatic Earth（宏观评论）"),
    ("global_bankunderground", "deep", "macro", "advanced", "全球媒体", "Bank Underground (BoE)"),
    ("global_contra_corner", "deep", "macro", None, "全球媒体", "Contra Corner (David Stockman)"),
    ("global_conversable_economist", "edu", "macro", "beginner", "全球媒体", "Conversable Economist（经济学教育）"),
    ("global_econlib", "deep", "macro", None, "全球媒体", "EconLog / Econlib（经济学评论）"),
    ("global_grumpy_economist", "deep", "macro", "advanced", "全球媒体", "The Grumpy Economist (John Cochrane)"),
    ("global_incrementum", "deep", "macro", "advanced", "全球媒体", "Incrementum（宏观/黄金）"),
    ("global_liberty_street", "deep", "macro", "advanced", "全球媒体", "Liberty Street Economics (NY Fed)"),
    ("global_lse_business", "deep", "research", "advanced", "全球媒体", "LSE Business Review（学术通俗）"),
    ("global_nber", "deep", "macro", "advanced", "全球媒体", "NBER（工作论文）"),
    ("global_project_syndicate", "deep", "macro", None, "全球媒体", "Project Syndicate（经济学家评论）"),
    ("global_promarket", "deep", "research", "advanced", "全球媒体", "ProMarket (Chicago Booth)"),
    ("global_quantocracy", "deep", "research", "advanced", "全球媒体", "Quantocracy（量化聚合）"),
    ("global_realinvestmentadvice", "deep", "macro", None, "全球媒体", "Real Investment Advice (Lance Roberts)"),
    ("global_der_bank_blog", "deep", "industry", None, "全球媒体", "Der Bank Blog（德语银行业分析）"),
    ("global_finanzrocker", "edu", "allocation", "beginner", "全球媒体", "Finanzrocker（德语理财播客）"),
    ("global_elblogsalmon", "edu", "allocation", "beginner", "全球媒体", "El Blog Salmón（西语理财）"),
    # ────────────────────────────────────────────────────────────────
    # 亚太英文 asen_*（ASIA_EN_FEEDS；各国大众财经媒体快讯跳过，
    # 主要收尾部的理财/投资博客与学术通俗源）
    # ────────────────────────────────────────────────────────────────
    ("asen_conversation_au_biz", "deep", "research", None, "亚太英文", "The Conversation AU Business（学术通俗）"),
    ("asen_conversation_global_biz", "deep", "research", None, "亚太英文", "The Conversation Business（学术通俗）"),
    ("asen_fred_blog", "edu", "macro", "beginner", "亚太英文", "FRED Blog (St. Louis Fed，数据宏观教育)"),
    ("asen_coppolacomment", "deep", "macro", "advanced", "亚太英文", "Coppola Comment (Frances Coppola)"),
    ("asen_assi_sg", "edu", "allocation", "beginner", "亚太英文", "A Singaporean Stock Investor (ASSI)"),
    ("asen_boringinvestor", "edu", "allocation", "beginner", "亚太英文", "The Boring Investor (SG)"),
    ("asen_dividendgrowth", "deep", "allocation", None, "亚太英文", "Dividend Growth Investor（股息投资）"),
    ("asen_dollarsandsense", "edu", "allocation", "beginner", "亚太英文", "DollarsAndSense (SG)"),
    ("asen_econbrowser2", "deep", "macro", "advanced", "亚太英文", "Macro Musings (David Beckworth)"),
    ("asen_econompic", "deep", "macro", None, "亚太英文", "EconomPic（数据宏观）"),
    ("asen_epchan", "deep", "research", "advanced", "亚太英文", "Quantitative Trading (Ernie Chan)"),
    ("asen_europeandgi", "edu", "allocation", "beginner", "亚太英文", "European DGI（股息投资）"),
    ("asen_fifthperson", "edu", "allocation", "beginner", "亚太英文", "The Fifth Person (SG)"),
    ("asen_freefincal", "edu", "allocation", "beginner", "亚太英文", "freefincal（IN 理财分析/工具）"),
    ("asen_lt3000", "deep", "valuation", "advanced", "亚太英文", "LT3000 (Lyall Taylor，公司深度)"),
    ("asen_mebfaber", "deep", "allocation", "advanced", "亚太英文", "Meb Faber Research（配置/量化）"),
    ("asen_musings_markets", "deep", "valuation", "advanced", "亚太英文", "Musings on Markets (Damodaran)"),
    ("asen_myownadvisor", "edu", "allocation", "beginner", "亚太英文", "My Own Advisor (CA)"),
    ("asen_providend", "edu", "allocation", "beginner", "亚太英文", "Providend (SG 理财顾问)"),
    ("asen_quantstart", "edu", "research", "advanced", "亚太英文", "QuantStart（量化交易教程）"),
    ("asen_retirementinvestingtoday", "edu", "allocation", "beginner", "亚太英文", "Retirement Investing Today"),
    ("asen_robotwealth", "deep", "research", "advanced", "亚太英文", "Robot Wealth（量化）"),
    ("asen_routetoretire", "edu", "allocation", "beginner", "亚太英文", "Route to Retire"),
    ("asen_safalniveshak", "edu", "allocation", "beginner", "亚太英文", "Safal Niveshak（IN 价值投资科普）"),
    ("asen_strongmoneyau", "edu", "allocation", "beginner", "亚太英文", "Strong Money Australia"),
    ("asen_tawcan", "edu", "allocation", "beginner", "亚太英文", "Tawcan（CA 股息）"),
    ("asen_thepoorswiss", "edu", "allocation", "beginner", "亚太英文", "The Poor Swiss (CH)"),
    ("asen_boomerandecho", "edu", "allocation", "beginner", "亚太英文", "Boomer & Echo (CA)"),
    ("asen_capitalspectator", "deep", "macro", "advanced", "亚太英文", "The Capital Spectator（数据宏观）"),
    ("asen_dividendguy", "edu", "allocation", "beginner", "亚太英文", "The Dividend Guy Blog (CA)"),
    ("asen_jagoinvestor", "edu", "allocation", "beginner", "亚太英文", "JagoInvestor (IN 理财)"),
    ("asen_looniedoctor", "edu", "allocation", "beginner", "亚太英文", "The Loonie Doctor (CA)"),
    ("asen_moneywehave", "edu", "allocation", "beginner", "亚太英文", "Money We Have (CA)"),
    ("asen_retirebeforedad", "edu", "allocation", "beginner", "亚太英文", "Retire Before Dad"),
    ("asen_tradebrains", "edu", "allocation", "beginner", "亚太英文", "Trade Brains (IN 股票科普)"),
    ("asen_treeofprosperity", "edu", "allocation", "beginner", "亚太英文", "Tree of Prosperity (SG)"),
    # ────────────────────────────────────────────────────────────────
    # rss_simple 单源（快讯 marketwatch/ft/investing 与央行新闻稿跳过）
    # ────────────────────────────────────────────────────────────────
    ("arxiv_qfin", "deep", "research", "advanced", "RSS单源", "arXiv q-fin（量化金融论文）"),
    ("wolfstreet", "deep", "macro", "advanced", "RSS单源", "Wolf Street (Wolf Richter)"),
    ("calculatedrisk", "deep", "macro", "advanced", "RSS单源", "Calculated Risk (Bill McBride，地产/宏观)"),
    ("awealthofcommonsense", "edu", "allocation", "beginner", "RSS单源", "A Wealth of Common Sense (Ben Carlson)"),
    ("ofdollarsanddata", "edu", "allocation", "beginner", "RSS单源", "Of Dollars and Data (Nick Maggiulli)"),
    ("marginalrevolution", "deep", "macro", None, "RSS单源", "Marginal Revolution（经济学博客）"),
    ("ritholtz", "deep", "research", None, "RSS单源", "The Big Picture (Barry Ritholtz)"),
    ("netinterest", "deep", "industry", "advanced", "RSS单源", "Net Interest (Marc Rubinstein，金融机构深度)"),
    ("doomberg", "deep", "industry", "advanced", "RSS单源", "Doomberg（工业/能源分析）"),
    ("apricitas", "deep", "macro", "advanced", "RSS单源", "Apricitas Economics (Joey Politano)"),
    ("noahpinion", "deep", "macro", "advanced", "RSS单源", "Noahpinion (Noah Smith)"),
    ("econbrowser", "deep", "macro", "advanced", "RSS单源", "Econbrowser（学术宏观）"),
    ("theovershoot", "deep", "macro", "advanced", "RSS单源", "The Overshoot (Matt Klein)"),
    ("quantpedia", "deep", "research", "advanced", "RSS单源", "Quantpedia（量化策略研究）"),
    ("wechat_maobidao", "deep", "macro", None, "公众号", "猫笔刀（市场评论）"),
    ("wechat_sixianggangyin", "deep", "valuation", None, "公众号", "思想钢印（基金经理随笔）"),
    # ────────────────────────────────────────────────────────────────
    # edu 科普批次（edu_batch.py，2026-08-02）——学习中心专设知识源
    # ────────────────────────────────────────────────────────────────
    ("edu_humbledollar", "edu", "allocation", "beginner", "科普批次", "Humble Dollar"),
    ("edu_choosefi", "edu", "allocation", "beginner", "科普批次", "ChooseFI"),
    ("edu_behavioralsci", "edu", "psychology", None, "科普批次", "Behavioral Scientist"),
    ("edu_klement", "deep", "research", "advanced", "科普批次", "Klement on Investing"),
    ("edu_macrocompass", "deep", "macro", "advanced", "科普批次", "The Macro Compass"),
    ("edu_napkinfinance", "edu", "allocation", "beginner", "科普批次", "Napkin Finance"),
    ("edu_ytbenfelix", "edu", "allocation", None, "科普批次", "Ben Felix (YouTube)"),
    ("edu_ytplainbagel", "edu", "allocation", "beginner", "科普批次", "The Plain Bagel (YouTube)"),
    ("edu_yttwocents", "edu", "allocation", "beginner", "科普批次", "Two Cents - PBS (YouTube)"),
    ("edu_ytdamodaran", "edu", "valuation", "advanced", "科普批次", "Aswath Damodaran (YouTube)"),
    ("edu_ytpboyle", "edu", "macro", None, "科普批次", "Patrick Boyle (YouTube)"),
    ("edu_ytpensioncraft", "edu", "allocation", None, "科普批次", "PensionCraft (YouTube)"),
    ("edu_ytmoneyguy", "edu", "allocation", "beginner", "科普批次", "The Money Guy Show (YouTube)"),
    ("edu_ytdamien", "edu", "allocation", "beginner", "科普批次", "Damien Talks Money (YouTube)"),
    ("edu_ytjamesshack", "edu", "allocation", None, "科普批次", "James Shack (YouTube)"),
    ("edu_ytmoneymacro", "edu", "macro", "beginner", "科普批次", "Money & Macro (YouTube)"),
    ("edu_stockfeel", "edu", "allocation", "beginner", "科普批次", "股感 StockFeel"),
    # ────────────────────────────────────────────────────────────────
    # 英文财经波 enf_*（en_fin_batch.py，2026-08-02 三波扩源 A 组）——
    # CNBC/NYT/CBS/PBS/各大众媒体快讯线与 fool/marketbeat 等荐股营销
    # 源一律不打标；只收央行/智库/宏观 Substack/深度分析媒体。
    # ────────────────────────────────────────────────────────────────
    ("enf_economistfinance", "deep", "macro", None, "英文财经波", "The Economist Finance & Economics"),
    ("enf_economistbusiness", "deep", "industry", None, "英文财经波", "The Economist Business"),
    ("enf_ftalphaville", "deep", "research", "advanced", "英文财经波", "FT Alphaville（市场/金融分析）"),
    ("enf_bespoke", "deep", "research", None, "英文财经波", "Bespoke Investment Group（数据驱动市场分析）"),
    ("enf_macrobusiness", "deep", "macro", None, "英文财经波", "MacroBusiness（澳洲宏观/地产分析）"),
    ("enf_moneymagau", "edu", "allocation", "beginner", "英文财经波", "Money Magazine Australia（理财科普）"),
    ("enf_finshots", "edu", "macro", "beginner", "英文财经波", "Finshots（印度财经科普）"),
    ("enf_krugman", "deep", "macro", "advanced", "英文财经波", "Paul Krugman"),
    ("enf_chartbook", "deep", "macro", "advanced", "英文财经波", "Chartbook (Adam Tooze)"),
    ("enf_sumner", "deep", "macro", "advanced", "英文财经波", "Scott Sumner（货币经济学）"),
    ("enf_braddelong", "deep", "macro", "advanced", "英文财经波", "Brad DeLong（经济史/政策）"),
    ("enf_bonddad", "deep", "macro", None, "英文财经波", "Bonddad Blog（经济/市场分析）"),
    ("enf_nakedcapitalism", "deep", "macro", None, "英文财经波", "Naked Capitalism（金融/经济评论）"),
    ("enf_pensionpulse", "deep", "research", None, "英文财经波", "Pension Pulse（养老金/机构投资）"),
    ("enf_epi", "deep", "macro", None, "英文财经波", "Economic Policy Institute（劳动/经济政策）"),
    ("enf_fedtestimony", "deep", "macro", "advanced", "英文财经波", "Federal Reserve Testimony（联储证词）"),
    ("enf_boj", "deep", "macro", "advanced", "英文财经波", "Bank of Japan（日本央行官方）"),
    # ────────────────────────────────────────────────────────────────
    # 官方机构波 ofc_*（official_batch.py，2026-08-02 三波扩源 B 组）——
    # 监管执法/机构新闻稿（SEC/CFTC/FTC/FDIC/BEA…）、Dive 家族行业
    # 快讯、techcrunch/engadget 等科技快讯、汽车媒体一律不打标；
    # 只收央行讲话/货币政策、智库研究、行业深度与官方数据分析。
    # ────────────────────────────────────────────────────────────────
    ("ofc_fedspeeches", "deep", "macro", "advanced", "官方机构波", "Federal Reserve Speeches（联储讲话）"),
    ("ofc_fedmonetary", "deep", "macro", "advanced", "官方机构波", "Fed Monetary Policy Press（货币政策声明）"),
    ("ofc_bisspeeches", "deep", "macro", "advanced", "官方机构波", "BIS Central Bank Speeches（央行行长讲话）"),
    ("ofc_riksbank", "deep", "macro", "advanced", "官方机构波", "Riksbank（瑞典央行）"),
    ("ofc_eia", "deep", "industry", None, "官方机构波", "EIA Today in Energy（能源数据分析）"),
    ("ofc_cbo", "deep", "macro", "advanced", "官方机构波", "CBO Publications（财政研究）"),
    ("ofc_dallasfed", "deep", "macro", "advanced", "官方机构波", "Dallas Fed News"),
    ("ofc_dallasfedrel", "deep", "macro", "advanced", "官方机构波", "Dallas Fed Releases"),
    ("ofc_dallasspeeches", "deep", "macro", "advanced", "官方机构波", "Dallas Fed Speeches"),
    ("ofc_cfr", "deep", "research", "advanced", "官方机构波", "Council on Foreign Relations（外交/地缘智库）"),
    ("ofc_cato", "deep", "macro", None, "官方机构波", "Cato Institute（经济政策评论）"),
    ("ofc_hoover", "deep", "research", "advanced", "官方机构波", "Hoover Institution（政策研究智库）"),
    ("ofc_mckinsey", "deep", "research", None, "官方机构波", "McKinsey Insights（管理/产业研究）"),
    ("ofc_semianalysis", "deep", "industry", "advanced", "官方机构波", "SemiAnalysis（半导体产业深度）"),
    ("ofc_miningcom", "deep", "industry", None, "官方机构波", "MINING.COM（矿业产业）"),
    ("ofc_aerotime", "deep", "industry", None, "官方机构波", "AeroTime（航空产业深度）"),
    ("ofc_breakingdefense", "deep", "industry", None, "官方机构波", "Breaking Defense（国防产业深度）"),
    # ────────────────────────────────────────────────────────────────
    # 中文媒体波 zhm_*（zh_media_batch.py，2026-08-02 三波扩源 C 组）——
    # 港台/日韩大众媒体快讯、IT 科技线、东南亚英文快讯、crypto 价格
    # 快讯一律不打标；只收深度调查/评论媒体。
    # ────────────────────────────────────────────────────────────────
    ("zhm_twreporter", "deep", "research", None, "中文媒体波", "报导者（深度调查报道）"),
    ("zhm_thenewslens", "deep", "research", None, "中文媒体波", "关键评论网（评论/深度）"),
    ("zhm_toyokeizai", "deep", "industry", None, "中文媒体波", "东洋经济（日本商业/产业分析）"),
    # ────────────────────────────────────────────────────────────────
    # AI链-中文波（ai_cn_batch.py，2026-08-04）——厂商技术工程号
    # （阿里云/阿里技术/字节/腾讯/美团/AWS中国/掘金/电子发烧友）沿用
    # zhb 批次"技术博客跳过"先例不打标；人民网/c114/zol/yesky/光纤在线/
    # 存储在线/电子信息产业网/HelloGitHub/V2EX 为快讯或聚合不打标；
    # 实验室/产品官方博客（ofc_qwen_blog/global_openmmlab/
    # global_huggingface/global_producthunt）沿用存量 global_apple_ml /
    # global_nvidia_blog 未打标先例跳过；集微网快讯占比高不打标；
    # 声动早咖啡为日更新闻播客不打标。
    # ────────────────────────────────────────────────────────────────
    ("wechat_tanjiti", "deep", "industry", None, "公众号", "碳基体（AI 深度分析）"),
    # arXiv 四栏目与存量 arxiv_qfin 同值同组（RSS单源）
    ("asen_arxiv_cscl", "deep", "research", "advanced", "RSS单源", "arXiv cs.CL（计算与语言）"),
    ("asen_arxiv_csai", "deep", "research", "advanced", "RSS单源", "arXiv cs.AI（人工智能）"),
    ("asen_arxiv_csro", "deep", "research", "advanced", "RSS单源", "arXiv cs.RO（机器人学）"),
    ("asen_arxiv_csma", "deep", "research", "advanced", "RSS单源", "arXiv cs.MA（多智能体系统）"),
    # 集邦咨询=研究机构出品（非快讯门户），三栏目均打标
    ("cn_trendforce_semi", "deep", "industry", None, "产业研究", "集邦咨询-半导体"),
    ("cn_trendforce_emerging", "deep", "industry", None, "产业研究", "集邦咨询-新兴科技"),
    ("cn_trendforce_energy", "deep", "industry", None, "产业研究", "集邦咨询-新能源"),
    ("pod_shangyejushi", "deep", "industry", None, "中文播客", "商业就是这样（商业案例深聊）"),
    # 与存量 wechat_hwunicorn（公众号）同一团队、同值打标
    ("pod_haiwaidujiaoshou", "deep", "research", None, "中文播客", "海外独角兽（播客，科技公司/创投研究）"),
    # 李宏毅 ML 课程（大学课程级，同 edu_ytdamodaran 定级）
    ("yt_hungyilee", "edu", "research", "advanced", "YouTube", "Hung-yi Lee 李宏毅（ML 课程）"),
    # ────────────────────────────────────────────────────────────────
    # AI链-英文波（ai_us_batch.py，2026-08-04）——不打标：TLDR/
    # bensbites/techcrunch/theverge/arstechnica AI 栏目等日更快讯；
    # 实验室与公司官方博客（OpenAI/Google AI/DeepMind/Google Research/
    # MSR/Amazon Science/EleutherAI/Databricks/HuggingFace）沿用存量
    # global_apple_ml/global_nvidia_blog/gind_bairblog 未打标先例；
    # 厂商 PR 新闻室（micron/lamresearch/intel/arm）与半导体/数据中心/
    # 能源/网络行业快讯媒体（digitimes/semiconductor_digest/phoronix/
    # igorslab/eejournal/3dincites/DCK/uptime/fierce/capacity/rcr/
    # datacenterpost/siliconangle/networkworld/heatmap/latitude/
    # rtoinsider/energystorage/pvmagazine/berkeley_lab/nist）不打标；
    # 云厂商工程博客（aws_hpc/azure/google_cloud/lambda/cloudflare）不打标；
    # 日更/评论播客（allin/aibreakdown/hardfork）与 AI 快讯 YouTube
    # 频道（aiexplained/matthewberman/wesroth/theaigrid/mattvidpro/
    # mooreslawisdead/bloombergtech）不打标；cerebralvalley/mitnews/
    # mittr_ai 拿不准不打标。
    # ────────────────────────────────────────────────────────────────
    # 英文 Newsletter（深度分析/研究类）
    ("gind_thegradient", "deep", "research", None, "Newsletter", "The Gradient（AI 研究评论）"),
    # 与存量 indie_stratechery 同站不同 source，沿用同值
    ("gind_stratechery", "deep", "industry", "advanced", "Newsletter", "Stratechery (Ben Thompson，科技战略分析)"),
    ("gind_aisupremacy", "deep", "industry", None, "Newsletter", "AI Supremacy（AI 产业分析）"),
    ("gind_importai", "deep", "research", None, "Newsletter", "Import AI (Jack Clark，AI 政策/研究)"),
    ("gind_thesequence", "deep", "research", None, "Newsletter", "The Sequence（ML 研究解读）"),
    ("gind_latentspace", "deep", "research", None, "Newsletter", "Latent Space (swyx，AI 工程)"),
    # 与存量 gind_chinatalk 同类（中国 AI 研究/翻译）
    ("gind_chinai", "deep", "research", None, "Newsletter", "ChinAI (Jeff Ding，中国 AI 研究)"),
    ("gind_garymarcus", "deep", "research", None, "Newsletter", "Marcus on AI (Gary Marcus，AI 评论)"),
    ("ai_swyx", "deep", "research", None, "Newsletter", "swyx (Shawn Wang，AI 工程)"),
    ("ai_thezvi", "deep", "research", None, "Newsletter", "Don't Worry About the Vase (Zvi，AI 深度评论)"),
    ("ai_chiphuyen", "deep", "research", None, "Newsletter", "Chip Huyen Blog（ML 系统）"),
    ("ai_lilianweng", "deep", "research", "advanced", "Newsletter", "Lil'Log (Lilian Weng，ML 研究笔记)"),
    # VC 研究博客（同存量 gind_eladgil 先例）
    ("ai_sequoia", "deep", "research", None, "Newsletter", "Sequoia Capital（创投研究）"),
    ("ai_epoch_ai", "deep", "research", "advanced", "Newsletter", "Epoch AI（AI 趋势量化研究）"),
    # 与存量 gind_exponentialview 同站不同 source，沿用同值
    ("ai_exponentialview", "deep", "research", None, "Newsletter", "Exponential View (Azeem Azhar，技术/宏观趋势)"),
    ("ai_usv", "deep", "research", None, "Newsletter", "Union Square Ventures（创投研究）"),
    # arXiv 两栏目与存量 arxiv_qfin 同值同组
    ("ai_arxiv_cslg", "deep", "research", "advanced", "RSS单源", "arXiv cs.LG (Machine Learning)"),
    ("ai_arxiv_cscv", "deep", "research", "advanced", "RSS单源", "arXiv cs.CV (Computer Vision)"),
    # 深度报道媒体（同存量 wechat_latepost 先例）
    ("ai_theinformation", "deep", "industry", None, "全球媒体", "The Information（科技商业深度报道）"),
    # TrendForce 英文站=研究机构（同中文三栏目）
    ("trendforce", "deep", "industry", None, "产业研究", "TrendForce（半导体/科技研究）"),
    # 半导体深度分析 Substack（同存量 gind_chipsandcheese 先例）
    ("morethanmoore", "deep", "industry", "advanced", "Newsletter", "More than Moore (Ian Cutress，半导体深度)"),
    ("thechipletter", "deep", "industry", None, "Newsletter", "The Chip Letter（半导体史/产业分析）"),
    # 政策智库（同存量 ofc_cfr/ofc_hoover/gind_merics 先例）
    ("csis", "deep", "research", None, "智库", "CSIS（战略与国际研究中心）"),
    ("cset", "deep", "research", "advanced", "智库", "Georgetown CSET（AI 政策研究）"),
    ("rhodium", "deep", "research", "advanced", "智库", "Rhodium Group（中国/能源研究）"),
    ("itif", "deep", "research", None, "智库", "ITIF（科技政策智库）"),
    # 英文播客（深度访谈/研究类；日更快讯类已剔除）
    ("pod_dwarkesh", "deep", "research", None, "播客", "Dwarkesh Podcast（AI/历史长访谈）"),
    ("pod_bg2", "deep", "industry", None, "播客", "BG2Pod (Gerstner & Gurley，科技投资)"),
    ("pod_acquired", "deep", "industry", None, "播客", "Acquired（公司深度拆解）"),
    ("pod_a16z", "deep", "industry", None, "播客", "The a16z Show（科技/创投）"),
    ("pod_nopriors", "deep", "industry", None, "播客", "No Priors (Conviction，AI 创投访谈)"),
    ("pod_trainingdata", "deep", "industry", None, "播客", "Training Data (Sequoia，AI 访谈)"),
    ("pod_20vc", "deep", "industry", None, "播客", "The Twenty Minute VC（创投访谈）"),
    ("pod_eyeonai", "deep", "industry", None, "播客", "Eye On A.I. (Craig Smith，AI 访谈)"),
    ("pod_mlstreettalk", "deep", "research", "advanced", "播客", "Machine Learning Street Talk（ML 研究访谈）"),
    ("pod_cognitiverev", "deep", "research", None, "播客", "The Cognitive Revolution（AI 研究者访谈）"),
    ("pod_sharptech", "deep", "industry", None, "播客", "Sharp Tech (Ben Thompson，科技分析)"),
    ("pod_twimlai", "deep", "research", None, "播客", "TWIML AI Podcast（ML 从业者访谈）"),
    # 英文 YouTube（深度/教育类；快讯评论频道已剔除）
    ("yt_asianometry", "deep", "industry", None, "YouTube", "Asianometry（半导体/科技史深度）"),
    ("yt_twominutepapers", "edu", "research", None, "YouTube", "Two Minute Papers（论文科普）"),
    ("yt_yannickilcher", "deep", "research", "advanced", "YouTube", "Yannic Kilcher（论文深度解读）"),
    ("yt_coldfusion", "deep", "industry", None, "YouTube", "ColdFusion（科技公司/产业纪录片）"),
]

#: 种子表（list[dict]），键与 NewsSourceMeta 列一一对应。
SOURCE_META_SEED: list[dict] = [
    {
        "source": source,
        "content_type": content_type,
        "topic": topic,
        "difficulty_default": difficulty,
        "display_group": display_group,
        "note": note,
    }
    for source, content_type, topic, difficulty, display_group, note in _SEED_ROWS
]


def seed_source_meta(db: Session) -> int:
    """把种子标签灌入 ``news_source_meta``，幂等。

    等价于逐行 ``INSERT ... ON CONFLICT DO NOTHING``：先一次性读出
    已有 source 主键，再只插入缺失行——同一实现同时兼容 Postgres
    与 SQLite（测试库），已打标的行不会被覆盖（运营手改优先）。

    Returns
    -------
    int
        本次实际插入的行数（重复执行为 0）。
    """
    existing = set(db.execute(select(NewsSourceMeta.source)).scalars().all())
    inserted = 0
    for row in SOURCE_META_SEED:
        if row["source"] in existing:
            continue
        db.add(NewsSourceMeta(**row))
        inserted += 1
    if inserted:
        db.commit()
    return inserted
