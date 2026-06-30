"""Report generation business logic service.

Provides HTML/Markdown report generation for ETF pools with data
aggregation from indicators, scores, and pool metadata.
"""

import os
from datetime import date, datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo
from app.models.pool import ETFPools, PoolMember
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate


class ReportService:
    """Service for generating AD-Research reports."""

    # Risk score thresholds for classification
    RISK_HIGH = 6.0
    RISK_MID_HIGH = 4.0
    RISK_MID = 2.5

    def __init__(self, db: Session):
        self.db = db
        self.reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "reports",
        )
        os.makedirs(self.reports_dir, exist_ok=True)

        # Set up Jinja2 environment
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
        )
        self.jinja_env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    # ------------------------------------------------------------------
    # Main generation entry point
    # ------------------------------------------------------------------

    def generate_pool_report(
        self,
        pool_id: int,
        report_type: str = "pool_weekly",
        format: str = "html",
        template_id: int | None = None,
    ) -> ReportMetadata:
        """Generate a report for an ETF pool.

        Creates a ReportMetadata record, generates the report content,
        saves it to disk, and updates the record with the file path.

        Args:
            pool_id: The ETF pool ID.
            report_type: Type of report (e.g. "pool_weekly").
            format: Output format ("html" or "markdown").
            template_id: Score template ID for scoring data.

        Returns:
            The ReportMetadata record.
        """
        report_date = date.today()

        # Create metadata record
        metadata = ReportMetadata(
            report_type=report_type,
            report_date=report_date,
            pool_id=pool_id,
            template_id=template_id,
            status="running",
            format=format,
            started_at=datetime.now(),
        )
        self.db.add(metadata)
        self.db.commit()
        self.db.refresh(metadata)

        try:
            if format == "html":
                content = self._generate_pool_html(pool_id, template_id)
            elif format == "markdown":
                content = self._generate_pool_markdown(pool_id, template_id)
            else:
                content = self._generate_pool_html(pool_id, template_id)

            # Save to file
            filename = f"report_{report_type}_{pool_id}_{report_date.isoformat()}.{format}"
            file_path = os.path.join(self.reports_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            file_size = os.path.getsize(file_path)

            # Update metadata
            metadata.status = "done"
            metadata.file_path = file_path
            metadata.file_size = file_size
            metadata.finished_at = datetime.now()
            self.db.commit()
            self.db.refresh(metadata)

        except Exception as e:
            metadata.status = "failed"
            metadata.error_msg = str(e)
            metadata.finished_at = datetime.now()
            self.db.commit()
            self.db.refresh(metadata)
            raise

        return metadata

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    def _generate_pool_html(
        self, pool_id: int, template_id: int | None = None
    ) -> str:
        """Generate HTML report for a pool using Jinja2 templates."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        # Get active members
        members = (
            self.db.query(PoolMember)
            .filter(PoolMember.pool_id == pool_id, PoolMember.removed_at.is_(None))
            .all()
        )
        codes = [m.etf_code for m in members]

        # Get ETF info
        etf_info = (
            self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        )
        etf_name_map = {e.code: e.name for e in etf_info}
        etf_cat_map = {e.code: e.category for e in etf_info}

        # Get latest indicators
        indicators = self._get_latest_indicators(codes)
        ind_map = {ind.etf_code: ind for ind in indicators}

        # Get scores
        scores = self._get_latest_scores(codes, template_id)
        score_map = {s.etf_code: s for s in scores}

        # Build report data
        overview_data = []
        returns_data = []
        risk_data = []
        scores_data = []

        up_count = 0
        down_count = 0
        total_score = 0.0
        score_count = 0

        for code in codes:
            ind = ind_map.get(code)
            score = score_map.get(code)
            name = etf_name_map.get(code, code)
            category = etf_cat_map.get(code)

            # Returns data
            return_1w = float(ind.return_1w) if ind and ind.return_1w else 0.0
            return_1m = float(ind.return_1m) if ind and ind.return_1m else 0.0
            return_3m = float(ind.return_3m) if ind and ind.return_3m else 0.0
            return_6m = float(ind.return_6m) if ind and ind.return_6m else 0.0
            return_1y = float(ind.return_1y) if ind and ind.return_1y else 0.0

            if return_1w > 0:
                up_count += 1
            elif return_1w < 0:
                down_count += 1

            # Risk data
            volatility_20d = float(ind.volatility_20d) if ind and ind.volatility_20d else 0.0
            max_drawdown_1y = float(ind.max_drawdown_1y) if ind and ind.max_drawdown_1y else 0.0
            sharpe_1y = float(ind.sharpe_1y) if ind and ind.sharpe_1y else 0.0

            risk_level = self._classify_risk_level(sharpe_1y)
            risk_badge = self._risk_badge_html(risk_level)

            overview_data.append({
                "etf_code": code,
                "etf_name": name,
                "category": category,
                "return_1w": return_1w,
                "return_1m": return_1m,
                "return_1y": return_1y,
                "risk_badge": risk_badge,
            })

            returns_data.append({
                "etf_code": code,
                "etf_name": name,
                "return_1w": return_1w,
                "return_1m": return_1m,
                "return_3m": return_3m,
                "return_6m": return_6m,
                "return_1y": return_1y,
            })

            risk_data.append({
                "etf_code": code,
                "etf_name": name,
                "volatility_20d": volatility_20d,
                "max_drawdown_1y": max_drawdown_1y,
                "sharpe_1y": sharpe_1y,
                "risk_badge": risk_badge,
            })

            # Scores data
            if score:
                composite = float(score.composite_score) if score.composite_score else 0.0
                total_score += composite
                score_count += 1

                scores_data.append({
                    "etf_code": code,
                    "etf_name": name,
                    "rank": score.rank_overall or 0,
                    "composite_score": composite,
                    "score_return": float(score.score_return) if score.score_return else 0.0,
                    "score_risk": float(score.score_risk) if score.score_risk else 0.0,
                    "score_sharpe": float(score.score_sharpe) if score.score_sharpe else 0.0,
                    "score_liquidity": float(score.score_liquidity) if score.score_liquidity else 0.0,
                    "score_trend": float(score.score_trend) if score.score_trend else 0.0,
                    "score_return_class": self._score_class(float(score.score_return) if score.score_return else 0),
                    "score_risk_class": self._score_class(float(score.score_risk) if score.score_risk else 0),
                    "score_sharpe_class": self._score_class(float(score.score_sharpe) if score.score_sharpe else 0),
                    "score_liquidity_class": self._score_class(float(score.score_liquidity) if score.score_liquidity else 0),
                    "score_trend_class": self._score_class(float(score.score_trend) if score.score_trend else 0),
                })

        # Sort scores by rank
        scores_data.sort(key=lambda x: x["rank"])

        # Reassign sequential ranks after sorting
        for i, item in enumerate(scores_data, 1):
            item["rank"] = i

        avg_score = total_score / score_count if score_count > 0 else 0.0

        template = self.jinja_env.get_template("reports/pool_weekly.html")
        return template.render(
            pool_name=pool.name,
            report_date=date.today().isoformat(),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            member_count=len(members),
            up_count=up_count,
            down_count=down_count,
            avg_score=avg_score,
            overview_data=overview_data,
            returns_data=returns_data,
            risk_data=risk_data,
            scores_data=scores_data,
        )

    # ------------------------------------------------------------------
    # Markdown generation
    # ------------------------------------------------------------------

    def _generate_pool_markdown(
        self, pool_id: int, template_id: int | None = None
    ) -> str:
        """Generate Markdown report for a pool."""
        pool = self.db.query(ETFPools).filter(ETFPools.id == pool_id).first()
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        members = (
            self.db.query(PoolMember)
            .filter(PoolMember.pool_id == pool_id, PoolMember.removed_at.is_(None))
            .all()
        )
        codes = [m.etf_code for m in members]

        etf_info = self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        etf_name_map = {e.code: e.name for e in etf_info}

        indicators = self._get_latest_indicators(codes)
        ind_map = {ind.etf_code: ind for ind in indicators}

        lines = [
            f"# {pool.name} - 池周报",
            "",
            f"**报告日期**: {date.today().isoformat()}",
            f"**成员数**: {len(members)}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 概览",
            "",
            "| 代码 | 名称 | 周收益 | 月收益 | 年收益 |",
            "|------|------|--------|--------|--------|",
        ]

        for code in codes:
            ind = ind_map.get(code)
            name = etf_name_map.get(code, code)
            # Stored as decimals; multiply by 100 for percentage display.
            r1w = f"{float(ind.return_1w) * 100:.2f}%" if ind and ind.return_1w else "-"
            r1m = f"{float(ind.return_1m) * 100:.2f}%" if ind and ind.return_1m else "-"
            r1y = f"{float(ind.return_1y) * 100:.2f}%" if ind and ind.return_1y else "-"
            lines.append(f"| {code} | {name} | {r1w} | {r1m} | {r1y} |")

        lines.extend(["", "## 风险分析", ""])
        lines.append("| 代码 | 名称 | 波动率 | 最大回撤 | 夏普比率 | 风险等级 |")
        lines.append("|------|------|--------|----------|----------|----------|")

        for code in codes:
            ind = ind_map.get(code)
            name = etf_name_map.get(code, code)
            # Stored as decimals; multiply by 100 for percentage display.
            vol = f"{float(ind.volatility_20d) * 100:.2f}%" if ind and ind.volatility_20d else "-"
            mdd = f"{float(ind.max_drawdown_1y) * 100:.2f}%" if ind and ind.max_drawdown_1y else "-"
            sharpe = f"{float(ind.sharpe_1y):.2f}" if ind and ind.sharpe_1y else "-"
            risk = self._classify_risk_level(float(ind.sharpe_1y) if ind and ind.sharpe_1y else 0)
            lines.append(f"| {code} | {name} | {vol} | {mdd} | {sharpe} | {risk} |")

        lines.extend(["", "---", "", f"*Generated by AD-Research at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"])

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Data builders
    # ------------------------------------------------------------------

    def _build_returns_data(self, codes: list[str]) -> list[dict[str, Any]]:
        """Build returns analysis data from indicators."""
        indicators = self._get_latest_indicators(codes)
        etf_info = self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        name_map = {e.code: e.name for e in etf_info}

        data = []
        for ind in indicators:
            data.append({
                "etf_code": ind.etf_code,
                "etf_name": name_map.get(ind.etf_code, ind.etf_code),
                "return_1w": float(ind.return_1w) if ind.return_1w else 0.0,
                "return_1m": float(ind.return_1m) if ind.return_1m else 0.0,
                "return_3m": float(ind.return_3m) if ind.return_3m else 0.0,
                "return_6m": float(ind.return_6m) if ind.return_6m else 0.0,
                "return_1y": float(ind.return_1y) if ind.return_1y else 0.0,
            })
        return data

    def _build_risk_data(self, codes: list[str]) -> list[dict[str, Any]]:
        """Build risk analysis data with level classification."""
        indicators = self._get_latest_indicators(codes)
        etf_info = self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        name_map = {e.code: e.name for e in etf_info}

        data = []
        for ind in indicators:
            sharpe = float(ind.sharpe_1y) if ind and ind.sharpe_1y else 0.0
            risk_level = self._classify_risk_level(sharpe)
            data.append({
                "etf_code": ind.etf_code,
                "etf_name": name_map.get(ind.etf_code, ind.etf_code),
                "volatility_20d": float(ind.volatility_20d) if ind.volatility_20d else 0.0,
                "max_drawdown_1y": float(ind.max_drawdown_1y) if ind.max_drawdown_1y else 0.0,
                "sharpe_1y": sharpe,
                "risk_level": risk_level,
                "risk_badge": self._risk_badge_html(risk_level),
            })
        return data

    def _build_scores_data(
        self, codes: list[str], template_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Build composite scoring data with progress bar classes."""
        scores = self._get_latest_scores(codes, template_id)
        etf_info = self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        name_map = {e.code: e.name for e in etf_info}

        data = []
        for score in scores:
            data.append({
                "etf_code": score.etf_code,
                "etf_name": name_map.get(score.etf_code, score.etf_code),
                "rank": score.rank_overall or 0,
                "composite_score": float(score.composite_score) if score.composite_score else 0.0,
                "score_return": float(score.score_return) if score.score_return else 0.0,
                "score_risk": float(score.score_risk) if score.score_risk else 0.0,
                "score_sharpe": float(score.score_sharpe) if score.score_sharpe else 0.0,
                "score_liquidity": float(score.score_liquidity) if score.score_liquidity else 0.0,
                "score_trend": float(score.score_trend) if score.score_trend else 0.0,
                "score_return_class": self._score_class(float(score.score_return) if score.score_return else 0),
                "score_risk_class": self._score_class(float(score.score_risk) if score.score_risk else 0),
                "score_sharpe_class": self._score_class(float(score.score_sharpe) if score.score_sharpe else 0),
                "score_liquidity_class": self._score_class(float(score.score_liquidity) if score.score_liquidity else 0),
                "score_trend_class": self._score_class(float(score.score_trend) if score.score_trend else 0),
            })

        data.sort(key=lambda x: x["rank"])
        return data

    # ------------------------------------------------------------------
    # Risk classification
    # ------------------------------------------------------------------

    def _classify_risk_level(self, risk_score: float) -> str:
        """Classify risk level based on risk score (using Sharpe as proxy).

        Higher Sharpe = lower risk (better risk-adjusted return).
        We invert the logic: lower Sharpe = higher risk.

        Args:
            risk_score: The risk metric value (typically Sharpe ratio).

        Returns:
            Risk level string: 高风险, 中高风险, 中风险, or 低风险.
        """
        if risk_score > self.RISK_HIGH:
            return "低风险"
        elif risk_score > self.RISK_MID_HIGH:
            return "中风险"
        elif risk_score > self.RISK_MID:
            return "中高风险"
        else:
            return "高风险"

    def _risk_badge_html(self, risk_level: str) -> str:
        """Generate HTML badge for risk level."""
        badge_class = {
            "低风险": "badge-success",
            "中风险": "badge-info",
            "中高风险": "badge-warning",
            "高风险": "badge-danger",
        }.get(risk_level, "badge-primary")
        return f'<span class="badge {badge_class}">{risk_level}</span>'

    def _score_class(self, score: float) -> str:
        """Return CSS class for score bar based on value."""
        if score >= 60:
            return "high"
        elif score >= 40:
            return "medium"
        else:
            return "low"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _get_latest_indicators(self, codes: list[str]) -> list[ETFIndicator]:
        """Get the latest indicator for each ETF code."""
        if not codes:
            return []

        latest_subq = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .filter(ETFIndicator.etf_code.in_(codes))
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        return (
            self.db.query(ETFIndicator)
            .join(
                latest_subq,
                (ETFIndicator.etf_code == latest_subq.c.etf_code)
                & (ETFIndicator.trade_date == latest_subq.c.latest_date),
            )
            .all()
        )

    def _get_latest_scores(
        self, codes: list[str], template_id: int | None = None
    ) -> list[ETFScore]:
        """Get the latest scores for given ETF codes."""
        if not codes:
            return []

        if template_id is None:
            default = (
                self.db.query(ScoreTemplate)
                .filter(ScoreTemplate.is_default.is_(True))
                .first()
            )
            template_id = default.id if default else None

        query = self.db.query(ETFScore).filter(ETFScore.etf_code.in_(codes))

        if template_id:
            query = query.filter(ETFScore.template_id == template_id)

        # Get the latest trade date per ETF (not global) so we never silently
        # omit ETFs whose latest score is one day behind the pack.
        latest_score_subq = (
            self.db.query(
                ETFScore.etf_code,
                func.max(ETFScore.trade_date).label("latest_score_date"),
            )
            .filter(ETFScore.etf_code.in_(codes))
            .filter(ETFScore.template_id == template_id)
            .group_by(ETFScore.etf_code)
            .subquery()
        )
        query = query.join(
            latest_score_subq,
            (ETFScore.etf_code == latest_score_subq.c.etf_code)
            & (ETFScore.trade_date == latest_score_subq.c.latest_score_date),
        )

        return query.order_by(ETFScore.rank_overall.asc().nullslast()).all()

    # ------------------------------------------------------------------
    # Report listing and status
    # ------------------------------------------------------------------

    def get_reports(
        self,
        report_type: str | None = None,
        pool_id: int | None = None,
        limit: int = 50,
    ) -> list[ReportMetadata]:
        """Get a list of generated reports with optional filtering."""
        query = self.db.query(ReportMetadata)

        if report_type:
            query = query.filter(ReportMetadata.report_type == report_type)
        if pool_id is not None:
            query = query.filter(ReportMetadata.pool_id == pool_id)

        return (
            query.order_by(ReportMetadata.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_report_status(self, report_id: int) -> ReportMetadata | None:
        """Get the status of a report generation job."""
        return (
            self.db.query(ReportMetadata)
            .filter(ReportMetadata.id == report_id)
            .first()
        )
