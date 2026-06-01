"""ETF market scanner service.

Automatically discovers new, delisted, and changed ETFs by comparing
akshare's latest ETF list with the database.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.models.etf_scan_log import ETFScanLog


class ETFScannerService:
    """Service for scanning the ETF market for changes."""

    def __init__(self, db: Session):
        self.db = db

    def scan_market(self) -> Dict[str, Any]:
        """Scan the ETF market and detect changes.

        Returns:
            Dict with new, delisted, and changed ETFs.
        """
        try:
            from app.data.providers.akshare_provider import AkshareProvider

            provider = AkshareProvider()
            latest_etfs = provider.fetch_etf_list()
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch ETF list: {e}",
                "new": [],
                "delisted": [],
                "changed": [],
            }

        # Build maps
        latest_map: Dict[str, Any] = {}
        for etf in latest_etfs:
            latest_map[etf.code] = etf

        db_etfs = self.db.query(ETFInfo).all()
        db_map: Dict[str, ETFInfo] = {e.code: e for e in db_etfs}

        # Find new ETFs
        new_etfs: List[Dict[str, Any]] = []
        for code, etf in latest_map.items():
            if code not in db_map:
                new_etfs.append({
                    "code": code,
                    "name": etf.name,
                    "market": etf.market,
                    "exchange": etf.exchange,
                    "category": etf.category,
                })

        # Find delisted ETFs (active in DB but not in latest)
        delisted_etfs: List[Dict[str, Any]] = []
        for code, db_etf in db_map.items():
            if code not in latest_map and db_etf.status == "active":
                delisted_etfs.append({
                    "code": code,
                    "name": db_etf.name,
                    "market": db_etf.market,
                })

        # Find changed ETFs
        changed_etfs: List[Dict[str, Any]] = []
        for code, db_etf in db_map.items():
            if code in latest_map:
                latest = latest_map[code]
                changes: Dict[str, Any] = {}
                if latest.name != db_etf.name:
                    changes["name"] = {"old": db_etf.name, "new": latest.name}
                if latest.category != db_etf.category:
                    changes["category"] = {"old": db_etf.category, "new": latest.category}
                if latest.market != db_etf.market:
                    changes["market"] = {"old": db_etf.market, "new": latest.market}
                if changes:
                    changed_etfs.append({
                        "code": code,
                        "changes": changes,
                    })

        # Log the scan
        scan_log = ETFScanLog(
            scan_date=date.today(),
            new_count=len(new_etfs),
            delisted_count=len(delisted_etfs),
            changed_count=len(changed_etfs),
            details={
                "new": new_etfs,
                "delisted": delisted_etfs,
                "changed": changed_etfs,
            },
            status="success",
        )
        self.db.add(scan_log)
        self.db.commit()

        return {
            "success": True,
            "new": new_etfs,
            "delisted": delisted_etfs,
            "changed": changed_etfs,
            "scan_date": date.today().isoformat(),
        }

    def get_scan_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get scan history logs."""
        logs = (
            self.db.query(ETFScanLog)
            .order_by(ETFScanLog.scan_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": log.id,
                "scan_date": log.scan_date.isoformat() if log.scan_date else None,
                "new_count": log.new_count,
                "delisted_count": log.delisted_count,
                "changed_count": log.changed_count,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
