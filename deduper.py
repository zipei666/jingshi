from __future__ import annotations

from collections import deque
from hashlib import sha1

from models import FlashNewsItem


class NewsDeduper:
    """\u7528\u4e8e\u53bb\u91cd\uff0c\u907f\u514d\u5df2\u7ecf\u5c55\u793a\u8fc7\u7684\u5feb\u8baf\u91cd\u590d\u51fa\u73b0\u3002"""

    def __init__(self, max_size: int = 5000) -> None:
        self.max_size = max_size
        self._seen: set[str] = set()
        self._order: deque[str] = deque()

    def clear(self) -> None:
        self._seen.clear()
        self._order.clear()

    def seed(self, items: list[FlashNewsItem]) -> None:
        for item in items:
            self.mark_seen(item)

    def mark_seen(self, item: FlashNewsItem) -> bool:
        key = self._build_key(item)
        if key in self._seen:
            return False

        self._seen.add(key)
        self._order.append(key)
        self._trim()
        return True

    def filter_new(self, items: list[FlashNewsItem]) -> list[FlashNewsItem]:
        new_items: list[FlashNewsItem] = []
        for item in items:
            if self.mark_seen(item):
                new_items.append(item)
        return new_items

    def _trim(self) -> None:
        while len(self._order) > self.max_size:
            old_key = self._order.popleft()
            self._seen.discard(old_key)

    @staticmethod
    def _build_key(item: FlashNewsItem) -> str:
        if item.uid:
            return item.uid

        raw = "|".join(
            [
                item.display_time,
                "1" if item.is_vip else "0",
                "1" if item.is_important else "0",
                item.content,
            ]
        )
        return sha1(raw.encode("utf-8")).hexdigest()
