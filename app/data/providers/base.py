from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import pandas as pd


@dataclass
class ETFInfo:
    code: str
    name: str
    market: str = ""
    exchange: str = ""
    category: str = ""
    manager: str = ""
    currency: str = "CNY"
    is_qdii: bool = False
    underlying_index: str = ""
    inception_date: Optional[date] = None


@dataclass
class MarketHours:
    open_time: str = "09:30"
    close_time: str = "15:00"
    timezone: str = "Asia/Shanghai"


class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def fetch_etf_list(self) -> List[ETFInfo]:
        pass

    @abstractmethod
    def fetch_daily_bars(
        self, codes: List[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def fetch_realtime_quotes(self, codes: List[str]) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_market_hours(self) -> MarketHours:
        pass

    def check_health(self) -> bool:
        return True
