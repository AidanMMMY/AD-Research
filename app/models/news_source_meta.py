"""资讯源内容性质元数据表（学习中心，2026-08-02）。

Why this exists
---------------
平台的 ~800 个资讯源里约 1/3 是深度分析 / 科普教育内容，但它们和
事实快讯混在同一个按时间倒序的 feed 里，用户"想学习无从下手"
（分析文档 ``docs/dev-notes/`` 之外，见 /tmp 分析报告 §1）。
本表在**源级别**打 ``content_type`` / ``topic`` / ``difficulty_default``
标签，学习中心 API 通过 ``news_article.source`` join 本表即可把
知识型内容从快讯里捞出来——不改 ``news_article`` 结构、不回填历史
数据、不动任何 crawler 表。

打标原则：宁可保守（拿不准的源不打标），打标基于源的实际内容性质。
种子数据在 ``app/services/news/source_meta_seed.py``，迁移只建表不
灌数据，手动执行入口 ``scripts/seed_news_source_meta.py``。

Tables:
  - news_source_meta : one row per tagged source
"""

from sqlalchemy import Column, String

from app.core.database import Base

#: 合法 content_type 取值（快讯 flash 不入库——未打标的源默认就是快讯）。
CONTENT_TYPES = ("deep", "edu")

#: 合法 topic 取值；research 是兜底深度类（装不进前 6 类的深度内容）。
TOPICS = (
    "allocation",  # 资产配置 / 理财规划
    "valuation",   # 估值方法 / 公司研究
    "macro",       # 宏观入门 / 宏观经济
    "industry",    # 行业研究
    "psychology",  # 交易心理 / 行为决策
    "tools",       # 工具教程
    "research",    # 深度研究（兜底）
)

#: 合法 difficulty_default 取值；NULL = 混合 / 不确定。
DIFFICULTIES = ("beginner", "advanced")


class NewsSourceMeta(Base):
    """一个资讯源的内容性质标签（学习中心知识 feed 的分类依据）。

    ``source`` 与 ``news_article.source`` 同值（如 ``wechat_zepinghongguan``、
    ``indie_lynalden``）。一个源只属于一个主题——"源可属于 1-2 个主题"
    的诉求在 MVP 阶段用单主题近似，运营可后续调整。
    """

    __tablename__ = "news_source_meta"

    source = Column(
        String(200),
        primary_key=True,
        comment="资讯源标识，与 news_article.source 对齐（wechat_/indie_/gind_ 等命名空间）",
    )
    content_type = Column(
        String(20),
        nullable=False,
        comment="deep=深度分析/研究 | edu=科普教育（快讯源不打标、不入库）",
    )
    topic = Column(
        String(40),
        nullable=True,
        comment="allocation|valuation|macro|industry|psychology|tools|research（兜底深度类）",
    )
    difficulty_default = Column(
        String(10),
        nullable=True,
        comment="beginner|advanced；NULL=混合/不确定（源级近似，不做逐篇难度）",
    )
    display_group = Column(
        String(60),
        nullable=True,
        comment="运营分组标签（如 公众号/中文播客/英文独立源），便于后台管理",
    )
    note = Column(
        String(200),
        nullable=True,
        comment="备注（通常为源的显示名，便于 SQL 维护时辨认）",
    )
