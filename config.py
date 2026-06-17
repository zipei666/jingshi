from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from logger import get_data_dir


KEYWORD_SPLIT_RE = re.compile(r"[\s,\uff0c]+")
MAX_SENT_MESSAGE_KEYS = 300


@dataclass(slots=True)
class AppSettings:
    keyword_text: str = ""
    keyword_filter_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_enabled: bool = False
    sent_message_keys: list[str] = field(default_factory=list)


def get_config_path() -> Path:
    return get_data_dir() / "settings.json"


def load_app_settings() -> AppSettings:
    config_path = get_config_path()
    if not config_path.exists():
        return AppSettings()

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()

    return AppSettings(
        keyword_text=str(raw.get("keyword_text", "")),
        keyword_filter_enabled=bool(raw.get("keyword_filter_enabled", False)),
        webhook_url=str(raw.get("webhook_url", "")).strip(),
        webhook_secret=str(raw.get("webhook_secret", "")).strip(),
        webhook_enabled=bool(raw.get("webhook_enabled", False)),
        sent_message_keys=_normalize_sent_keys(raw.get("sent_message_keys", [])),
    )


def save_app_settings(settings: AppSettings) -> Path:
    payload = asdict(settings)
    payload["sent_message_keys"] = _normalize_sent_keys(payload.get("sent_message_keys", []))
    config_path = get_config_path()
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def normalize_keywords(raw_text: str) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    for chunk in KEYWORD_SPLIT_RE.split(raw_text.replace("\r", "\n")):
        keyword = chunk.strip()
        if not keyword:
            continue

        normalized = keyword.casefold()
        if normalized in seen:
            continue

        seen.add(normalized)
        keywords.append(keyword)

    return keywords


def find_keyword_hits(content: str, keywords: list[str]) -> list[str]:
    # OR 匹配：只要正文命中任意一个关键词，就返回所有命中的关键词列表。
    if not content or not keywords:
        return []

    lowered_content = content.casefold()
    hits: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        normalized = keyword.casefold()
        if normalized and normalized in lowered_content and normalized not in seen:
            seen.add(normalized)
            hits.append(keyword)

    return hits


def _normalize_sent_keys(raw_keys) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    if not isinstance(raw_keys, list):
        return normalized

    for raw_key in raw_keys:
        key = str(raw_key).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)

    if len(normalized) > MAX_SENT_MESSAGE_KEYS:
        normalized = normalized[-MAX_SENT_MESSAGE_KEYS:]

    return normalized
