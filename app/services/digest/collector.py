"""Daily Digest 聚合层（2026-08-03，B2）。

``DigestDataCollector`` 以 report_date 当日 06:30 (Asia/Shanghai) 为
窗口终点、前一日 06:30 为起点（半开区间 [start, end)），采集 8 个
数据包写入 :class:`DigestContext`：

1. macro      宏观指标快照（MacroDataService.latest_snapshot）
2. sector     板块轮动（SectorRotationService.analyze_sectors，
              轮动信号 + 1 月回报 top/bottom 5）
3. scores     评分榜（ScoringService.get_scores，A股/美股各 top10；
              market 参数用 DB 原始值 "A股"/"US"，记忆教训：DB 里
              A股 market 值是中文）
4. fund_flow  资金流（大盘 + 板块 top10 + 微观结构摘要）
5. news       窗口内重要资讯（importance>=4 ≤40 条 + importance=3
              补齐到 60 条，按 event_category 分桶）
6. watchlist  主用户（settings.digest_primary_username）的
              UserFavorite ∪ PaperTradePosition 标的，逐标的行情/
              窗口内关联新闻/最新评分——「分析重点」落点
7. sentiment  watchlist 标的的近 3 日情绪（依赖包 6，故顺序固定）
8. sellside   卖方研报（research_reports 窗口内 ≤10 条）

每个包独立 try/except：单包失败记 ``context.degraded`` 不阻塞整体
出报（LLM prompt 会声明该包缺失）。每个包同时渲染**紧凑中文事实
清单文本**（``context.facts``）供 prompt 直接拼接。

时区注意：``news_article.published_at`` 是 naive UTC（crawler 入库
统一转 UTC 去时区，见 api/v1/learning.py 注释），新闻查询先把
Shanghai 窗口边界转 naive UTC 再比较。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.etf import ETFInfo, InstrumentDailyBar
from app.models.favorite import UserFavorite
from app.models.research_report import ResearchReport
from app.models.scoring import ETFScore
from app.models.trading import PaperTradeAccount, PaperTradePosition
from app.models.user import User
from app.services import fund_flow_service, microstructure_service
from app.services.digest.context import DigestContext

# 注意：app/models/news.py 被 app/models/news/ 包遮蔽（平台历史坑），
# NewsArticle 必须经 _model_loader 导入（见该模块 docstring）。
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol

logger = logging.getLogger(__name__)

SHANGHAI = ZoneInfo("Asia/Shanghai")

# 窗口终点时刻：每日 06:30 Asia/Shanghai（与 scheduler 触发时刻一致，
# 接受美股指标偶尔晚到，预案 06:45——见方案文档）。
WINDOW_END_TIME = time(6, 30)

# 资讯限量：importance>=4 全量上限 40 条，importance=3 补齐到总 60 条
NEWS_HIGH_LIMIT = 40
NEWS_TOTAL_LIMIT = 60

# 事件分桶：buckets 之外的 event_category（earnings/macro/...）并入 other
NEWS_BUCKET_LABELS = {
    "regulation": "监管",
    "geopolitics": "地缘",
    "central_bank": "央行",
    "election": "选举",
    "trade_war": "贸易",
    "sanction": "制裁",
    "other": "其他",
}

# 每个标的最多带 5 条窗口内关联新闻
WATCHLIST_NEWS_LIMIT = 5
# 卖方研报窗口内最多 10 条
SELLSIDE_LIMIT = 10


class DigestDataCollector:
    """聚合 8 个数据包，产出 DigestContext。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 窗口
    # ------------------------------------------------------------------

    @staticmethod
    def compute_window(report_date: date) -> tuple[datetime, datetime]:
        """返回 (start, end)，tz-aware Asia/Shanghai，半开区间 [start, end)。"""
        end = datetime.combine(report_date, WINDOW_END_TIME, tzinfo=SHANGHAI)
        return end - timedelta(days=1), end

    def collect(self, report_date: date | None = None) -> DigestContext:
        """采集全部数据包。单包失败记 degraded，不阻塞。"""
        if report_date is None:
            report_date = datetime.now(SHANGHAI).date()
        start, end = self.compute_window(report_date)
        ctx = DigestContext(
            report_date=report_date, window_start=start, window_end=end
        )

        # 顺序固定：sentiment 依赖 watchlist 的标的列表
        packages = [
            ("macro", self._collect_macro),
            ("sector", self._collect_sector),
            ("scores", self._collect_scores),
            ("fund_flow", self._collect_fund_flow),
            ("news", self._collect_news),
            ("watchlist", self._collect_watchlist),
            ("sentiment", self._collect_sentiment),
            ("sellside", self._collect_sellside),
        ]
        for name, fn in packages:
            try:
                fn(ctx)
            except Exception as exc:  # noqa: BLE001 - 单包失败不阻塞整体
                logger.warning("digest collector package %s failed: %s", name, exc)
                ctx.degraded.append(name)
        return ctx

    # ------------------------------------------------------------------
    # 1. 宏观指标快照
    # ------------------------------------------------------------------

    def _collect_macro(self, ctx: DigestContext) -> None:
        from app.services.macro_service import MacroDataService

        snapshot = MacroDataService(self.db).latest_snapshot()
        ctx.macro = snapshot
        lines = []
        for item in (snapshot.get("items") or [])[:30]:
            change = item.get("change_pct")
            change_txt = f"{change:+.2f}%" if change is not None else "—"
            lines.append(
                f"{item.get('name_zh') or item.get('code')}"
                f"({item.get('region')})：{item.get('value')}"
                f"{item.get('unit') or ''}（{change_txt}，{item.get('period')}）"
            )
        ctx.facts["macro"] = "\n".join(lines) if lines else "（无宏观快照数据）"

    # ------------------------------------------------------------------
    # 2. 板块轮动
    # ------------------------------------------------------------------

    def _collect_sector(self, ctx: DigestContext) -> None:
        from app.services.sector_rotation_service import SectorRotationService

        result = SectorRotationService(self.db).analyze_sectors(window_weeks=4)
        ctx.sector = result
        sectors = result.get("sectors") or []
        signals = result.get("rotation_signals") or []
        market_avg = result.get("market_avg") or {}

        lines = [
            f"数据日期：{result.get('trade_date')}；"
            f"市场平均 1 月回报：{market_avg.get('return_1m', 0):.2f}%"
        ]
        if signals:
            lines.append("轮动信号：" + "；".join(s.get("message", "") for s in signals))
        top = sectors[:5]
        bottom = sectors[-5:] if len(sectors) > 5 else []
        if top:
            lines.append(
                "1 月回报 Top5："
                + "；".join(
                    f"{s['sector']} {s['return_1m']:+.2f}%（RS {s.get('relative_strength_1m', 0):+.2f}）"
                    for s in top
                )
            )
        if bottom:
            lines.append(
                "1 月回报 Bottom5："
                + "；".join(f"{s['sector']} {s['return_1m']:+.2f}%" for s in bottom)
            )
        ctx.facts["sector"] = "\n".join(lines)

    # ------------------------------------------------------------------
    # 3. 评分榜（A股/美股各 top10）
    # ------------------------------------------------------------------

    def _collect_scores(self, ctx: DigestContext) -> None:
        from app.services.scoring_service import ScoringService

        svc = ScoringService(self.db)
        # market 用 DB 原始值："A股"（中文，记忆教训）/ "US"
        data = {
            "cn_a": svc.get_scores(market="A股", limit=10),
            "us": svc.get_scores(market="US", limit=10),
        }
        ctx.scores = data

        lines = []
        for label, key in (("A股", "cn_a"), ("美股", "us")):
            rows = data[key]
            if not rows:
                lines.append(f"{label}评分 Top10：无数据")
                continue
            items = "；".join(
                f"{i + 1}. {r.get('etf_name')}({r.get('etf_code')}) "
                f"{float(r.get('composite_score') or 0):.1f}分"
                for i, r in enumerate(rows)
            )
            lines.append(f"{label}评分 Top10：{items}")
        ctx.facts["scores"] = "\n".join(lines)

    # ------------------------------------------------------------------
    # 4. 资金流 + 微观结构
    # ------------------------------------------------------------------

    def _collect_fund_flow(self, ctx: DigestContext) -> None:
        from app.models.fund_flow import SectorFundFlow

        market = fund_flow_service.list_market(self.db)
        # 板块 top10 直查 SectorFundFlow——不用 fund_flow_service.list_sector：
        # 其 _parse_sort 对 "main_net_inflow" 固定返回 IndividualFundFlow
        # 的列（dict 第一个），在板块表查询里产生跨表 ORDER BY（潜在
        # 平台 bug，另案处理；此处绕开不改公共 service）。
        latest_day = self.db.execute(
            select(func.max(SectorFundFlow.trade_date))
        ).scalar()
        sector_rows: list[dict[str, Any]] = []
        if latest_day is not None:
            sector_rows = [
                {"sector_name": r.sector_name, "main_net_inflow": (
                    float(r.main_net_inflow) if r.main_net_inflow is not None else None
                )}
                for r in self.db.execute(
                    select(SectorFundFlow)
                    .where(SectorFundFlow.trade_date == latest_day)
                    .order_by(SectorFundFlow.main_net_inflow.desc())
                    .limit(10)
                ).scalars().all()
            ]
        micro = microstructure_service.get_summary(self.db)
        data = {
            "market": (market.get("items") or [None])[0],
            "sector": sector_rows,
            "micro": micro,
        }
        ctx.fund_flow = data

        lines = []
        m = data["market"]
        if m:
            total = m.get("total_main_net_inflow")
            total_txt = _fmt_yi(total) if total is not None else "—"
            lines.append(
                f"大盘资金流（{m.get('trade_date')}）：沪深主力净流入 {total_txt}，"
                f"沪 {_fmt_yi(m.get('sh_main_net_inflow'))} / "
                f"深 {_fmt_yi(m.get('sz_main_net_inflow'))}"
            )
        if data["sector"]:
            lines.append(
                "板块主力净流入 Top10："
                + "；".join(
                    f"{s.get('sector_name')} {_fmt_yi(s.get('main_net_inflow'))}"
                    for s in data["sector"]
                )
            )
        lhb = (micro or {}).get("lhb") or {}
        if lhb.get("top_buyers"):
            buyers = "；".join(
                f"{r.get('stock_name') or r.get('stock_code')} "
                f"{_fmt_yi(r.get('lhb_net_amount'))}"
                for r in lhb["top_buyers"][:5]
            )
            lines.append(f"龙虎榜净买入 Top5（{lhb.get('trade_date')}）：{buyers}")
        hsgt = (micro or {}).get("hsgt") or {}
        if hsgt:
            lines.append(f"北向资金：{hsgt}")
        ctx.facts["fund_flow"] = "\n".join(lines) if lines else "（无资金流数据）"

    # ------------------------------------------------------------------
    # 5. 窗口内重要资讯（分桶）
    # ------------------------------------------------------------------

    def _collect_news(self, ctx: DigestContext) -> None:
        # published_at 是 naive UTC —— Shanghai 窗口边界先转 UTC 再去时区
        start_utc = ctx.window_start.astimezone(UTC).replace(tzinfo=None)
        end_utc = ctx.window_end.astimezone(UTC).replace(tzinfo=None)
        window_cond = (
            (NewsArticle.published_at >= start_utc)
            & (NewsArticle.published_at < end_utc)
        )

        cols = (
            NewsArticle.id,
            NewsArticle.title,
            NewsArticle.title_zh,
            NewsArticle.summary_zh,
            NewsArticle.sentiment_label,
            NewsArticle.sentiment_score,
            NewsArticle.market,
            NewsArticle.source,
            NewsArticle.event_category,
            NewsArticle.importance,
            NewsArticle.published_at,
        )
        high = (
            self.db.execute(
                select(*cols)
                .where(window_cond)
                .where(NewsArticle.importance >= 4)
                .order_by(NewsArticle.importance.desc(), NewsArticle.published_at.desc())
                .limit(NEWS_HIGH_LIMIT)
            )
            .mappings()
            .all()
        )
        rows = list(high)
        if len(rows) < NEWS_TOTAL_LIMIT:
            fill = (
                self.db.execute(
                    select(*cols)
                    .where(window_cond)
                    .where(NewsArticle.importance == 3)
                    .order_by(NewsArticle.published_at.desc())
                    .limit(NEWS_TOTAL_LIMIT - len(rows))
                )
                .mappings()
                .all()
            )
            rows.extend(fill)

        buckets: dict[str, list[dict[str, Any]]] = {
            key: [] for key in NEWS_BUCKET_LABELS
        }
        for r in rows:
            cat = r["event_category"] if r["event_category"] in NEWS_BUCKET_LABELS else "other"
            buckets[cat].append(dict(r))
        ctx.news = {"buckets": buckets, "total": len(rows)}

        lines = [f"窗口内重要资讯共 {len(rows)} 条，按事件分桶："]
        for cat, label in NEWS_BUCKET_LABELS.items():
            items = buckets[cat]
            if not items:
                continue
            lines.append(f"【{label}】{len(items)} 条")
            for r in items:
                lines.append("  - " + _render_news_line(r))
        ctx.facts["news"] = "\n".join(lines)

    # ------------------------------------------------------------------
    # 6. 主用户自选 ∪ 持仓（分析重点）
    # ------------------------------------------------------------------

    def _primary_user(self) -> User | None:
        return (
            self.db.execute(
                select(User).where(
                    User.username == get_settings().digest_primary_username
                )
            )
            .scalars()
            .first()
        )

    def _collect_watchlist(self, ctx: DigestContext) -> None:
        user = self._primary_user()
        if user is None:
            # 主用户不存在属于配置问题——记 degraded 由外层捕获不合适，
            # 这里直接产出空包并在 facts 中声明，prompt 会如实说明。
            ctx.watchlist = {"primary_user": None, "codes": [], "items": []}
            ctx.facts["watchlist"] = (
                f"（主用户 {get_settings().digest_primary_username} 不存在，"
                "无自选/持仓数据）"
            )
            return

        fav_codes = [
            r[0]
            for r in self.db.execute(
                select(UserFavorite.etf_code).where(
                    UserFavorite.username == user.username
                )
            ).all()
        ]
        position_rows = (
            self.db.execute(
                select(PaperTradePosition)
                .join(
                    PaperTradeAccount,
                    PaperTradePosition.account_id == PaperTradeAccount.id,
                )
                .where(
                    PaperTradeAccount.user_id == user.id,
                    PaperTradeAccount.status == "active",
                    PaperTradePosition.quantity > 0,
                )
            )
            .scalars()
            .all()
        )
        position_map = {p.instrument_code: p for p in position_rows}
        codes = sorted(set(fav_codes) | set(position_map))

        start_utc = ctx.window_start.astimezone(UTC).replace(tzinfo=None)
        end_utc = ctx.window_end.astimezone(UTC).replace(tzinfo=None)

        items = []
        for code in codes:
            info = self.db.get(ETFInfo, code)
            bar = (
                self.db.execute(
                    select(InstrumentDailyBar)
                    .where(InstrumentDailyBar.etf_code == code)
                    .order_by(InstrumentDailyBar.trade_date.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            score = (
                self.db.execute(
                    select(ETFScore)
                    .where(ETFScore.etf_code == code)
                    .order_by(ETFScore.trade_date.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            news_rows = (
                self.db.execute(
                    select(
                        NewsArticle.title,
                        NewsArticle.title_zh,
                        NewsArticle.sentiment_label,
                        NewsArticle.sentiment_score,
                        NewsArticle.source,
                        NewsArticle.published_at,
                    )
                    .join(
                        NewsArticleSymbol,
                        NewsArticleSymbol.article_id == NewsArticle.id,
                    )
                    .where(
                        NewsArticleSymbol.symbol == code,
                        NewsArticle.published_at >= start_utc,
                        NewsArticle.published_at < end_utc,
                    )
                    .order_by(NewsArticle.published_at.desc())
                    .limit(WATCHLIST_NEWS_LIMIT)
                )
                .mappings()
                .all()
            )
            pos = position_map.get(code)
            items.append(
                {
                    "code": code,
                    "name": (info.name_zh or info.name) if info else code,
                    "market": info.market if info else None,
                    "is_favorite": code in fav_codes,
                    "position": (
                        {
                            "quantity": float(pos.quantity),
                            "avg_cost": float(pos.avg_cost),
                            "unrealized_pnl": (
                                float(pos.unrealized_pnl)
                                if pos.unrealized_pnl is not None
                                else None
                            ),
                        }
                        if pos
                        else None
                    ),
                    "bar": (
                        {
                            "trade_date": bar.trade_date.isoformat(),
                            "close": float(bar.close) if bar.close is not None else None,
                            "change_pct": (
                                float(bar.change_pct)
                                if bar.change_pct is not None
                                else None
                            ),
                        }
                        if bar
                        else None
                    ),
                    "score": (
                        {
                            "trade_date": score.trade_date.isoformat(),
                            "composite_score": (
                                float(score.composite_score)
                                if score.composite_score is not None
                                else None
                            ),
                            "rank_overall": score.rank_overall,
                        }
                        if score
                        else None
                    ),
                    "news": [dict(r) for r in news_rows],
                }
            )

        ctx.watchlist = {
            "primary_user": user.username,
            "codes": codes,
            "items": items,
        }

        lines = [
            f"主用户 {user.username} 自选 {len(fav_codes)} 只 + "
            f"持仓 {len(position_map)} 只，合计 {len(codes)} 只标的："
        ]
        for it in items:
            tags = []
            if it["is_favorite"]:
                tags.append("自选")
            if it["position"]:
                p = it["position"]
                pnl = p["unrealized_pnl"]
                pnl_txt = f"，浮盈亏 {pnl:+.2f}" if pnl is not None else ""
                tags.append(
                    f"持仓 {p['quantity']:g} 股 @ 成本 {p['avg_cost']:g}{pnl_txt}"
                )
            bar = it["bar"]
            if bar and bar["close"] is not None:
                chg = bar["change_pct"]
                chg_txt = f"{chg:+.2f}%" if chg is not None else "—"
                bar_txt = f"最新收盘 {bar['close']:g}（{chg_txt}，{bar['trade_date']}）"
            else:
                bar_txt = "无行情数据"
            sc = it["score"]
            score_txt = (
                f"综合评分 {sc['composite_score']:.1f}"
                f"（排名 {sc['rank_overall'] or '—'}，{sc['trade_date']}）"
                if sc and sc["composite_score"] is not None
                else "无评分"
            )
            lines.append(
                f"· {it['name']}({it['code']}，{it['market'] or '—'}) "
                f"[{'；'.join(tags) or '—'}] {bar_txt}｜{score_txt}"
            )
            for r in it["news"]:
                lines.append("    新闻：" + _render_news_line(r, with_market=False))
        ctx.facts["watchlist"] = "\n".join(lines)

    # ------------------------------------------------------------------
    # 7. 情绪（依赖 watchlist 标的）
    # ------------------------------------------------------------------

    def _collect_sentiment(self, ctx: DigestContext) -> None:
        from app.services.sentiment_service import SentimentService

        codes = (ctx.watchlist or {}).get("codes") or []
        if not codes:
            ctx.sentiment = []
            ctx.facts["sentiment"] = "（无标的，跳过情绪聚合）"
            return
        data = SentimentService(self.db).get_market_sentiment(
            codes, lookback_days=3
        )
        ctx.sentiment = data

        lines = []
        for s in data:
            lines.append(
                f"{s.get('name_zh') or s.get('name') or s.get('instrument_code')}"
                f"({s.get('instrument_code')})：{s.get('label')} "
                f"均值 {s.get('avg_score'):+.2f}"
                f"（正 {s.get('positive_count')}/负 {s.get('negative_count')}"
                f"/中 {s.get('neutral_count')}，近 {s.get('period_days')} 日）"
            )
        ctx.facts["sentiment"] = "\n".join(lines) if lines else "（窗口内无情绪数据）"

    # ------------------------------------------------------------------
    # 8. 卖方研报
    # ------------------------------------------------------------------

    def _collect_sellside(self, ctx: DigestContext) -> None:
        # publish_date 是 Date（无时刻）——窗口 24h 跨两个自然日，
        # 取 >= start.date() 覆盖两日，按日期倒序限量。
        rows = (
            self.db.execute(
                select(ResearchReport)
                .where(ResearchReport.publish_date >= ctx.window_start.date())
                .where(ResearchReport.publish_date <= ctx.window_end.date())
                .order_by(ResearchReport.publish_date.desc(), ResearchReport.id.desc())
                .limit(SELLSIDE_LIMIT)
            )
            .scalars()
            .all()
        )
        ctx.sellside = [
            {
                "title": r.title,
                "org_name": r.org_name,
                "name": r.name,
                "ts_code": r.ts_code,
                "rating": r.rating,
                "publish_date": r.publish_date.isoformat() if r.publish_date else None,
                "summary": r.summary,
                "key_points": r.key_points,
            }
            for r in rows
        ]

        lines = []
        for r in ctx.sellside:
            head = (
                f"· {r['title']}（{r['org_name']}，{r['name']}"
                f"{'，评级 ' + r['rating'] if r['rating'] else ''}，{r['publish_date']}）"
            )
            lines.append(head)
            if r["summary"]:
                lines.append(f"    摘要：{str(r['summary'])[:120]}")
            elif r["key_points"]:
                points = r["key_points"]
                if isinstance(points, list):
                    lines.append("    要点：" + "；".join(str(p)[:60] for p in points[:3]))
        ctx.facts["sellside"] = (
            "\n".join(lines) if lines else "（窗口内无卖方研报）"
        )


# ---------------------------------------------------------------------------
# 渲染辅助（模块级纯函数，便于单测）
# ---------------------------------------------------------------------------


def _fmt_yi(value: Any) -> str:
    """把元为单位的资金额格式化为亿元文本；None → "—"。"""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{v / 1e8:+.2f} 亿"


def _render_news_line(r: dict[str, Any], with_market: bool = True) -> str:
    """渲染一条资讯为紧凑事实行：标题（来源，情绪 label score，日期）。"""
    title = r.get("title_zh") or r.get("title") or ""
    label = r.get("sentiment_label")
    score = r.get("sentiment_score")
    senti = f"，{label} {score:+d}" if label and score is not None else (
        f"，{label}" if label else ""
    )
    published = r.get("published_at")
    date_txt = published.strftime("%m-%d %H:%M") if isinstance(published, datetime) else ""
    market_txt = f"{r.get('market')}/" if with_market and r.get("market") else ""
    summary = r.get("summary_zh")
    summary_txt = f"——{str(summary)[:80]}" if summary else ""
    return (
        f"{title}（{market_txt}{r.get('source') or '—'}{senti}，{date_txt}）"
        f"{summary_txt}"
    )
