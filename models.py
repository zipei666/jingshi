from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


APP_NAME = "Jin10FlashMonitor"
DEFAULT_RSS_URL = "https://rsshub.rssforever.com/jin10"
SOURCE_URL = os.environ.get("JIN10_RSS_URL", DEFAULT_RSS_URL).strip() or DEFAULT_RSS_URL


class MonitorEventType(str, Enum):
    STATUS = "status"
    INITIAL_ITEMS = "initial_items"
    NEW_ITEMS = "new_items"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(slots=True)
class FlashNewsItem:
    uid: str
    display_time: str
    content: str
    published_at: Optional[datetime] = None
    detail_url: str = ""
    is_vip: bool = False
    is_important: bool = False
    raw_id: str = ""
    selected_date: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)
    arrival_index: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    analysis_level: str = "C"
    analysis_markets: list[str] = field(default_factory=list)
    analysis_direction: str = "不确定"
    analysis_reason: str = ""
    analysis_rule_hits: list[str] = field(default_factory=list)

    def display_text(self) -> str:
        prefix = "[VIP] " if self.is_vip else ""
        return f"{prefix}[{self.display_time}] {self.content}".strip()

    def effective_published_at(self) -> datetime:
        return self.published_at or self.fetched_at

    def sort_key(self) -> tuple[float, int]:
        # 主排序键使用发布时间倒序，同秒内再按抓取到的次序排序。
        return (-self.effective_published_at().replace(microsecond=0).timestamp(), self.arrival_index)


@dataclass(slots=True)
class MonitorConfig:
    url: str = SOURCE_URL
    interval_seconds: float = 2.0
    initial_limit: int = 25
    steady_limit: int = 12
    headless: bool = True
    timeout_ms: int = 15000


@dataclass(slots=True)
class MonitorEvent:
    event_type: MonitorEventType
    message: str = ""
    items: list[FlashNewsItem] = field(default_factory=list)
    is_running: bool = False
    last_refresh: Optional[datetime] = None
    error: str = ""
