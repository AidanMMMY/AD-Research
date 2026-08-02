"""用户文章状态表（学习中心 P1，2026-08-02）。

Why this exists
---------------
学习中心上线知识库 feed 后，用户需要"稍后读"（收藏）与"已读"
两种**文章级、用户级**状态（分析文档 §2.3，P1 优先级）。状态不能
写进 ``news_article``（那是全局共享的爬虫表，行是跨用户复用的），
所以单独建一张 (user, article) 维度的状态表：

* 收藏 = ``bookmarked_at`` 非空（再点一次置 NULL，幂等切换，不删行
  ——已读标记得以保留）；
* 已读 = ``read_at`` 非空（首次打开详情时写入，重复标记不动原时间戳）。

复合主键 (user_id, article_id)：一个用户对一篇文章最多一行，
UPSERT 语义天然安全。两列都加 CASCADE 外键——用户注销或文章被
清理时状态行随之消失，不留孤儿。

Tables:
  - user_article_state : one row per (user, article)
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func

from app.core.database import Base


class UserArticleState(Base):
    """一个用户对一篇文章的收藏/已读状态。

    ``bookmarked_at`` / ``read_at`` 均为可空时间戳：NULL 表示未收藏 /
    未读，非空值即首次发生的时间。用时间戳而非布尔位是为了后续能做
    "最近收藏"排序（收藏列表按 bookmarked_at DESC）与阅读行为分析。
    """

    __tablename__ = "user_article_state"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="用户 ID（users.id），复合主键之一",
    )
    article_id = Column(
        Integer,
        ForeignKey("news_article.id", ondelete="CASCADE"),
        primary_key=True,
        comment="文章 ID（news_article.id），复合主键之一",
    )
    bookmarked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="收藏时间；NULL=未收藏（取消收藏置 NULL 不删行，保留已读状态）",
    )
    read_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="首次标记已读时间；NULL=未读（重复标记不改写原时间戳）",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="状态行创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="状态行最近更新时间",
    )
