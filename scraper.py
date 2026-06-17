from __future__ import annotations

import email.utils
import hashlib
import html
import json
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from queue import Empty, Queue
from typing import Any

import websocket

from models import FlashNewsItem, MonitorConfig


JIN10_HOME_URL = "https://www.jin10.com/"
JIN10_FLASH_WS_URL = "wss://wss-flash-2.jin10.com/"
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
FLASH_ID_RE = re.compile(r'id="(flash\d{14}\d*)"\s+class="jin-flash-item-container[^"]*"', re.DOTALL)
TIME_RE = re.compile(r'class="item-time[^"]*">\s*(.*?)\s*</div>', re.DOTALL)
TITLE_RE = re.compile(r'class="right-common-title">\s*(.*?)\s*</b>', re.DOTALL)
BODY_RE = re.compile(r'class="flash-text">\s*(.*?)\s*</div>', re.DOTALL)
DETAIL_LINK_RE = re.compile(r'href="(https://flash\.jin10\.com/detail/\d+)"', re.DOTALL)


class Jin10RssScraper:
    """优先从金十首页实时 HTML 拉取快讯，失败时退回 RSS Feed。"""

    def __init__(self, config: MonitorConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self._pending_items: Queue[FlashNewsItem] = Queue()
        self._ws_app: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_stop_event = threading.Event()
        self._ws_connected = False
        self._ws_key = ""
        self._has_loaded_initial_items = False
        self._last_fallback_fetch = 0.0

    def start(self) -> None:
        self.logger.info("Jin10 scraper initialized. home=%s rss=%s", JIN10_HOME_URL, self.config.url)
        self._start_websocket()

    def fetch_items(self, limit: int) -> list[FlashNewsItem]:
        self._start_websocket()

        queued_items = self._drain_pending_items(limit)
        if queued_items:
            return queued_items

        if not self._has_loaded_initial_items:
            items = self._fetch_homepage_items(limit)
            if items:
                self._has_loaded_initial_items = True
                return items

        if self._ws_connected or time.monotonic() - self._last_fallback_fetch < max(3.0, self.config.interval_seconds):
            return []

        self._last_fallback_fetch = time.monotonic()
        try:
            items = self._fetch_homepage_items(limit)
            if items:
                return items
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Homepage flash fetch failed, falling back to RSS: %s", exc)

        feed_xml = self._download_feed()
        raw_items = self._parse_feed(feed_xml)
        items = [self._build_item(raw_item) for raw_item in raw_items[:limit]]
        items = [item for item in items if item.display_time and item.content]

        if not items:
            raise RuntimeError("No RSS items were found in the feed.")

        return items

    def reload_page(self) -> None:
        self.logger.info("Scraper reload requested; next poll will fetch the latest source again.")

    def close(self) -> None:
        self._ws_stop_event.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:  # noqa: BLE001
                pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)

    def _start_websocket(self) -> None:
        if self._ws_thread and self._ws_thread.is_alive():
            return

        self._ws_stop_event.clear()
        self._ws_thread = threading.Thread(
            target=self._run_websocket_loop,
            name="Jin10FlashWebSocket",
            daemon=True,
        )
        self._ws_thread.start()

    def _run_websocket_loop(self) -> None:
        while not self._ws_stop_event.is_set():
            self._ws_connected = False
            self._ws_app = websocket.WebSocketApp(
                JIN10_FLASH_WS_URL,
                header=[
                    "Origin: https://www.jin10.com",
                    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
                ],
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close,
            )
            try:
                self._ws_app.run_forever(
                    ping_interval=10,
                    ping_timeout=5,
                    skip_utf8_validation=True,
                    suppress_origin=False,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Jin10 websocket loop failed: %s", exc)
            finally:
                self._ws_connected = False
                self._ws_key = ""

            if not self._ws_stop_event.wait(timeout=1.0):
                self.logger.info("Reconnecting Jin10 websocket.")

    def _on_ws_open(self, ws_app: websocket.WebSocketApp) -> None:
        self._ws_connected = True
        self.logger.info("Jin10 websocket connected.")

    def _on_ws_message(self, ws_app: websocket.WebSocketApp, message) -> None:
        if isinstance(message, str):
            return
        if not isinstance(message, (bytes, bytearray)) or len(message) < 2:
            return

        raw_message = bytes(message)
        if not self._ws_key:
            if len(raw_message) < 12:
                return
            reader = _BinaryReader(raw_message)
            reader.read_u32()
            first = reader.read_u32()
            second = reader.read_u32()
            self._ws_key = f"{second}.{first}"
            self.logger.info("Jin10 websocket handshake completed.")
            self._send_ws_binary(ws_app, self._build_login_packet())
            return

        reader = _BinaryReader(self._xor_ws_payload(raw_message, self._ws_key))
        msg_type = reader.read_i16()
        if msg_type == 1201:
            ws_app.send("")
            return

        try:
            if msg_type in (1000, 1100):
                payload = json.loads(reader.read_string())
                item = self._build_socket_item(payload)
                if item is not None:
                    self._pending_items.put(item)
            elif msg_type == 1200:
                self.logger.info("Ignored Jin10 websocket startup snapshot.")
            elif msg_type == 4002:
                self.logger.info("Jin10 websocket login response: %s", reader.read_string())
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Failed to parse Jin10 websocket message type=%s: %s", msg_type, exc)

    def _on_ws_error(self, _ws_app: websocket.WebSocketApp, error) -> None:
        self._ws_connected = False
        self.logger.warning("Jin10 websocket error: %s", error)

    def _on_ws_close(self, _ws_app: websocket.WebSocketApp, _status_code, _message) -> None:
        self._ws_connected = False
        self._ws_key = ""
        self.logger.info("Jin10 websocket closed.")

    def _drain_pending_items(self, limit: int) -> list[FlashNewsItem]:
        items: list[FlashNewsItem] = []
        for _ in range(max(1, limit)):
            try:
                items.append(self._pending_items.get_nowait())
            except Empty:
                break
        return items

    def _build_socket_item(self, payload: dict[str, Any]) -> FlashNewsItem | None:
        action = int(payload.get("action", 1) or 1)
        if action == 3:
            return None

        data = payload.get("data") or {}
        if isinstance(data, str):
            content = self._normalize_text(data)
        elif isinstance(data, dict):
            title = self._normalize_text(str(data.get("title", "")))
            content_text = self._normalize_text(str(data.get("content", "") or data.get("text", "")))
            content_parts = [title]
            if content_text and content_text.casefold() != title.casefold():
                content_parts.append(content_text)
            content = "\n".join(part for part in content_parts if part)
        else:
            content = ""

        if not content:
            return None

        raw_id = str(payload.get("id", "")).strip()
        published_at = self._parse_socket_time(str(payload.get("time", ""))) or self._parse_homepage_published_at(
            f"flash{raw_id}"
        )
        detail_url = f"https://flash.jin10.com/detail/{raw_id}" if raw_id else ""
        channels = payload.get("channel", [])

        return FlashNewsItem(
            uid=f"flash{raw_id}" if raw_id else hashlib.sha1(content.encode("utf-8")).hexdigest(),
            raw_id=f"flash{raw_id}" if raw_id else "",
            display_time=self._format_display_time(published_at),
            content=content,
            published_at=published_at,
            detail_url=detail_url,
            is_vip=bool(payload.get("vip") or payload.get("vip_level")),
            is_important=bool(payload.get("important")) or self._looks_important(content),
            selected_date=published_at.strftime("%m-%d") if published_at else "",
        )

    @staticmethod
    def _build_login_packet() -> bytes:
        writer = _BinaryWriter()
        writer.write_i16(4002)
        writer.write_i32(0)
        writer.write_string("")
        writer.write_string("chrome")
        writer.write_i32(0)
        writer.write_string("web")
        return writer.to_bytes()

    def _send_ws_binary(self, ws_app: websocket.WebSocketApp, payload: bytes) -> None:
        if self._ws_key:
            payload = self._xor_ws_payload(payload, self._ws_key)
        ws_app.send(payload, opcode=websocket.ABNF.OPCODE_BINARY)

    @staticmethod
    def _xor_ws_payload(payload: bytes, key: str) -> bytes:
        if not payload or not key:
            return payload
        key_offset = ord(key[0])
        key_bytes = key.encode("utf-8")
        key_length = len(key_bytes)
        return bytes(byte ^ key_bytes[(index + key_offset) % key_length] for index, byte in enumerate(payload))

    @staticmethod
    def _parse_socket_time(raw_value: str) -> datetime | None:
        raw_value = raw_value.strip()
        if not raw_value:
            return None
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(raw_value, pattern)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone().replace(tzinfo=None)
                return parsed
            except ValueError:
                continue
        return None

    def _fetch_homepage_items(self, limit: int) -> list[FlashNewsItem]:
        html_text = self._download_text(JIN10_HOME_URL)
        raw_items = self._parse_homepage(html_text, limit)
        items = [self._build_homepage_item(raw_item) for raw_item in raw_items]
        return [item for item in items if item.display_time and item.content]

    def _download_text(self, url: str) -> str:
        timeout_seconds = max(1.0, self.config.timeout_ms / 1000)
        cache_buster = int(datetime.now().timestamp())
        separator = "&" if "?" in url else "?"
        req = urllib.request.Request(
            f"{url}{separator}_={cache_buster}",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                ),
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Homepage request failed with HTTP {exc.code}: {url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Homepage request failed: {exc.reason}") from exc

    def _parse_homepage(self, html_text: str, limit: int) -> list[dict[str, Any]]:
        matches = list(FLASH_ID_RE.finditer(html_text))
        raw_items: list[dict[str, Any]] = []

        for index, match in enumerate(matches[:limit]):
            block_start = match.start()
            block_end = matches[index + 1].start() if index + 1 < len(matches) else len(html_text)
            block = html_text[block_start:block_end]
            raw_id = match.group(1)
            title = self._match_text(TITLE_RE, block)
            body = self._match_text(BODY_RE, block)
            raw_items.append(
                {
                    "uid": raw_id,
                    "raw_id": raw_id,
                    "time": self._match_text(TIME_RE, block),
                    "title": title,
                    "description": body,
                    "link": self._match_text(DETAIL_LINK_RE, block)
                    or f"https://flash.jin10.com/detail/{raw_id.removeprefix('flash')}",
                    "is_important": 'class="jin-flash-item flash is-important' in block
                    or 'important-icon' in block
                    or self._looks_important(title),
                    "is_vip": 'class="jin-flash-item flash is-vip' in block or ">VIP<" in block,
                }
            )

        return raw_items

    def _build_homepage_item(self, raw_item: dict[str, Any]) -> FlashNewsItem:
        title = self._normalize_text(str(raw_item.get("title", "")))
        description = self._normalize_text(str(raw_item.get("description", "")))
        content_parts = [title]
        if description and description.casefold() != title.casefold():
            content_parts.append(description)
        content = "\n".join(part for part in content_parts if part)
        raw_id = str(raw_item.get("raw_id", ""))
        published_at = self._parse_homepage_published_at(raw_id)

        return FlashNewsItem(
            uid=str(raw_item.get("uid", "")).strip() or raw_id,
            raw_id=raw_id,
            display_time=str(raw_item.get("time", "")).strip() or self._format_display_time(published_at),
            content=content,
            published_at=published_at,
            detail_url=str(raw_item.get("link", "")).strip(),
            is_vip=bool(raw_item.get("is_vip", False)),
            is_important=bool(raw_item.get("is_important", False)) or self._looks_important(content),
            selected_date=published_at.strftime("%m-%d") if published_at else "",
        )

    def _download_feed(self) -> bytes:
        timeout_seconds = max(1.0, self.config.timeout_ms / 1000)
        req = urllib.request.Request(
            self.config.url,
            headers={
                "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                ),
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"RSS feed request failed with HTTP {exc.code}: {self.config.url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"RSS feed request failed: {exc.reason}") from exc

    def _parse_feed(self, feed_xml: bytes) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(feed_xml)
        except ET.ParseError as exc:
            raise RuntimeError("RSS feed XML could not be parsed.") from exc

        rss_items = root.findall(".//channel/item")
        if rss_items:
            return [self._parse_rss_item(item) for item in rss_items]

        atom_entries = [
            element
            for element in root.iter()
            if self._local_name(element.tag) == "entry"
        ]
        if atom_entries:
            return [self._parse_atom_entry(entry) for entry in atom_entries]

        return []

    def _parse_rss_item(self, item: ET.Element) -> dict[str, Any]:
        return {
            "uid": self._first_text(item, ("guid", "id")),
            "title": self._first_text(item, ("title",)),
            "description": self._first_text(item, ("description", "encoded")),
            "link": self._first_text(item, ("link",)),
            "published": self._first_text(item, ("pubDate", "published", "updated", "date")),
        }

    def _parse_atom_entry(self, entry: ET.Element) -> dict[str, Any]:
        link = ""
        for child in entry:
            if self._local_name(child.tag) == "link":
                link = child.attrib.get("href", "") or (child.text or "")
                if link:
                    break

        return {
            "uid": self._first_text(entry, ("id", "guid")),
            "title": self._first_text(entry, ("title",)),
            "description": self._first_text(entry, ("summary", "content")),
            "link": link,
            "published": self._first_text(entry, ("published", "updated", "pubDate")),
        }

    def _build_item(self, raw_item: dict[str, Any]) -> FlashNewsItem:
        title = self._normalize_text(str(raw_item.get("title", "")))
        description = self._normalize_text(str(raw_item.get("description", "")))
        link = str(raw_item.get("link", "")).strip()
        published_at = self._parse_published_at(str(raw_item.get("published", "")))

        content_parts = [title]
        if description and description.casefold() != title.casefold():
            content_parts.append(description)
        content = "\n".join(part for part in content_parts if part)

        uid = str(raw_item.get("uid", "")).strip() or link
        if not uid:
            uid = hashlib.sha1(f"{published_at}|{content}".encode("utf-8")).hexdigest()

        return FlashNewsItem(
            uid=uid,
            raw_id=uid,
            display_time=self._format_display_time(published_at),
            content=content,
            published_at=published_at,
            detail_url=link,
            is_vip="VIP" in content.upper(),
            is_important=self._looks_important(content),
            selected_date=published_at.strftime("%m-%d") if published_at else "",
        )

    @staticmethod
    def _match_text(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _first_text(parent: ET.Element, names: tuple[str, ...]) -> str:
        wanted = {name.casefold() for name in names}
        for element in parent.iter():
            if element is parent:
                continue
            if Jin10RssScraper._local_name(element.tag).casefold() in wanted:
                return "".join(element.itertext()).strip()
        return ""

    @staticmethod
    def _parse_homepage_published_at(raw_id: str) -> datetime | None:
        match = re.search(r"flash(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", raw_id)
        if not match:
            return None
        try:
            return datetime(
                year=int(match.group(1)),
                month=int(match.group(2)),
                day=int(match.group(3)),
                hour=int(match.group(4)),
                minute=int(match.group(5)),
                second=int(match.group(6)),
            )
        except ValueError:
            return None

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = html.unescape(text.strip())
        cdata_match = CDATA_RE.fullmatch(text)
        if cdata_match:
            text = cdata_match.group(1)
        text = HTML_TAG_RE.sub("\n", text)
        lines = []
        for line in text.splitlines():
            cleaned = WHITESPACE_RE.sub(" ", html.unescape(line)).strip()
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)

    @staticmethod
    def _parse_published_at(raw_value: str) -> datetime | None:
        raw_value = raw_value.strip()
        if not raw_value:
            return None

        try:
            parsed = email.utils.parsedate_to_datetime(raw_value)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            pass

        for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(raw_value, pattern)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone().replace(tzinfo=None)
                return parsed
            except ValueError:
                continue

        return None

    @staticmethod
    def _format_display_time(published_at: datetime | None) -> str:
        return published_at.strftime("%H:%M:%S") if published_at else datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _looks_important(content: str) -> bool:
        first_line = content.splitlines()[0] if content else ""
        return first_line.startswith(("【", "[重要]", "重要")) or "重要快讯" in content


class _BinaryWriter:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def write_i16(self, value: int) -> None:
        self._buffer.extend(int(value).to_bytes(2, "little", signed=True))

    def write_i32(self, value: int) -> None:
        self._buffer.extend(int(value).to_bytes(4, "little", signed=True))

    def write_string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self._buffer.extend(len(encoded).to_bytes(2, "little", signed=False))
        self._buffer.extend(encoded)

    def to_bytes(self) -> bytes:
        return bytes(self._buffer)


class _BinaryReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read_i16(self) -> int:
        value = int.from_bytes(self._data[self._pos : self._pos + 2], "little", signed=True)
        self._pos += 2
        return value

    def read_i32(self) -> int:
        value = int.from_bytes(self._data[self._pos : self._pos + 4], "little", signed=True)
        self._pos += 4
        return value

    def read_u32(self) -> int:
        value = int.from_bytes(self._data[self._pos : self._pos + 4], "little", signed=False)
        self._pos += 4
        return value

    def read_string(self) -> str:
        length = int.from_bytes(self._data[self._pos : self._pos + 2], "little", signed=False)
        self._pos += 2
        value = self._data[self._pos : self._pos + length].decode("utf-8", errors="replace")
        self._pos += length
        return value
