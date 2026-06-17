from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from queue import Empty, Queue
from typing import Literal
from urllib import error, parse, request

from models import FlashNewsItem


NotificationKind = Literal["flash", "test"]


@dataclass(slots=True)
class DingTalkPushConfig:
    webhook_url: str = ""
    webhook_secret: str = ""
    enabled: bool = False
    timeout_seconds: float = 8.0


@dataclass(slots=True)
class NotificationResult:
    kind: NotificationKind
    success: bool
    message: str
    happened_at: datetime
    message_key: str = ""


@dataclass(slots=True)
class _NotificationTask:
    kind: NotificationKind
    config: DingTalkPushConfig
    payload: dict
    message_key: str = ""


class SentMessageCache:
    """Manage recent push keys and avoid duplicate DingTalk delivery."""

    def __init__(self, max_size: int = 300, initial_keys: list[str] | None = None) -> None:
        self.max_size = max_size
        self._seen: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

        for key in initial_keys or []:
            self.remember(key)

    def remember(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return False

            self._seen.add(key)
            self._order.append(key)
            self._trim()
            return True

    def export(self) -> list[str]:
        with self._lock:
            return list(self._order)

    def _trim(self) -> None:
        while len(self._order) > self.max_size:
            old_key = self._order.popleft()
            self._seen.discard(old_key)


class DingTalkNotifier:
    """Send DingTalk messages in a background thread."""

    def __init__(self, logger, initial_sent_keys: list[str] | None = None, max_cache_size: int = 300) -> None:
        self.logger = logger
        self.sent_cache = SentMessageCache(max_size=max_cache_size, initial_keys=initial_sent_keys)
        self._task_queue: Queue[_NotificationTask | None] = Queue()
        self._result_queue: Queue[NotificationResult] = Queue()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="DingTalkNotifierThread",
            daemon=True,
        )
        self._thread.start()

    def enqueue_flash(
        self,
        item: FlashNewsItem,
        config: DingTalkPushConfig,
        keyword_filter_enabled: bool,
    ) -> tuple[bool, str]:
        if not config.enabled:
            return False, ""
        if not item.matched_keywords:
            return False, ""
        if not config.webhook_url.strip():
            return False, "Webhook \u672a\u914d\u7f6e"

        message_key = self.build_message_key(item)
        if not self.sent_cache.remember(message_key):
            return False, ""

        self._task_queue.put(
            _NotificationTask(
                kind="flash",
                config=self._normalize_config(config),
                payload=self._build_flash_payload(item),
                message_key=message_key,
            )
        )
        return True, message_key

    def enqueue_test(self, config: DingTalkPushConfig) -> tuple[bool, str]:
        if not config.webhook_url.strip():
            return False, "Webhook \u672a\u914d\u7f6e"

        self._task_queue.put(
            _NotificationTask(
                kind="test",
                config=self._normalize_config(config),
                payload=self._build_test_payload(),
            )
        )
        return True, ""

    def poll_results(self) -> list[NotificationResult]:
        results: list[NotificationResult] = []
        while True:
            try:
                results.append(self._result_queue.get_nowait())
            except Empty:
                return results

    def export_sent_keys(self) -> list[str]:
        return self.sent_cache.export()

    def shutdown(self) -> None:
        self._task_queue.put(None)
        self._thread.join(timeout=5)

    @staticmethod
    def build_message_key(item: FlashNewsItem) -> str:
        if item.detail_url:
            return item.detail_url

        if item.published_at:
            time_text = item.published_at.strftime("%Y-%m-%d %H:%M:%S")
        elif item.selected_date:
            time_text = f"{item.selected_date} {item.display_time}"
        else:
            time_text = item.display_time

        raw = f"{time_text}|{item.content}"
        return sha1(raw.encode("utf-8")).hexdigest()

    def _worker_loop(self) -> None:
        while True:
            task = self._task_queue.get()
            if task is None:
                return

            happened_at = datetime.now()
            try:
                self._send(task.config, task.payload)
                if task.kind == "test":
                    message = f"\u6d4b\u8bd5\u53d1\u9001\u6210\u529f\uff1a{happened_at:%H:%M:%S}"
                else:
                    message = f"\u63a8\u9001\u6210\u529f\uff1a{happened_at:%H:%M:%S}"
                self.logger.info("DingTalk notification sent successfully. kind=%s key=%s", task.kind, task.message_key)
                self._result_queue.put(
                    NotificationResult(
                        kind=task.kind,
                        success=True,
                        message=message,
                        happened_at=happened_at,
                        message_key=task.message_key,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                if task.kind == "test":
                    message = f"\u6d4b\u8bd5\u53d1\u9001\u5931\u8d25\uff1a{exc}"
                else:
                    message = f"\u63a8\u9001\u5931\u8d25\uff1a{exc}"
                self.logger.exception("DingTalk notification failed. kind=%s key=%s", task.kind, task.message_key)
                self._result_queue.put(
                    NotificationResult(
                        kind=task.kind,
                        success=False,
                        message=message,
                        happened_at=happened_at,
                        message_key=task.message_key,
                    )
                )

    def _send(self, config: DingTalkPushConfig, payload: dict) -> None:
        webhook_url = self._build_signed_webhook_url(config.webhook_url, config.webhook_secret)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=config.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", response.getcode())
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(str(reason)) from exc

        if status_code != 200:
            raise RuntimeError(f"HTTP {status_code}: {body}")

        try:
            response_json = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"\u54cd\u5e94\u4e0d\u662f\u5408\u6cd5 JSON: {body}") from exc

        errcode = response_json.get("errcode")
        if errcode not in (0, "0", None):
            raise RuntimeError(response_json.get("errmsg", f"errcode={errcode}"))

    @staticmethod
    def _normalize_config(config: DingTalkPushConfig) -> DingTalkPushConfig:
        return DingTalkPushConfig(
            webhook_url=config.webhook_url.strip(),
            webhook_secret=config.webhook_secret.strip(),
            enabled=config.enabled,
            timeout_seconds=max(5.0, float(config.timeout_seconds)),
        )

    @staticmethod
    def _build_flash_payload(item: FlashNewsItem) -> dict:
        if item.published_at:
            time_text = item.published_at.strftime("%Y-%m-%d %H:%M:%S")
        elif item.selected_date:
            time_text = f"{item.selected_date} {item.display_time}"
        else:
            time_text = item.display_time

        keywords_text = ", ".join(item.matched_keywords) if item.matched_keywords else "无"
        lines = [
            "### \u91d1\u5341\u5173\u952e\u8bcd\u5feb\u8baf",
            "",
            f"- \u65f6\u95f4\uff1a{time_text}",
            f"- \u547d\u4e2d\u5173\u952e\u8bcd\uff1a{keywords_text}",
            f"- \u5185\u5bb9\uff1a{item.content.replace(chr(10), ' ')}",
        ]
        if item.detail_url:
            lines.append(f"- \u94fe\u63a5\uff1a{item.detail_url}")
        lines.append(f"- \u63a8\u9001\u65f6\u95f4\uff1a{datetime.now():%Y-%m-%d %H:%M:%S}")

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "\u91d1\u5341\u5173\u952e\u8bcd\u5feb\u8baf",
                "text": "\n".join(lines),
            },
        }

    @staticmethod
    def _build_test_payload() -> dict:
        return {
            "msgtype": "text",
            "text": {
                "content": (
                    "\u3010\u91d1\u5341\u5feb\u8baf\u76d1\u63a7\u3011\n"
                    "\u9489\u9489\u673a\u5668\u4eba\u6d4b\u8bd5\u53d1\u9001\u6210\u529f\n"
                    f"\u53d1\u9001\u65f6\u95f4\uff1a{datetime.now():%Y-%m-%d %H:%M:%S}"
                )
            },
        }

    @staticmethod
    def _build_signed_webhook_url(webhook_url: str, secret: str) -> str:
        if not secret:
            return webhook_url.strip()

        timestamp = str(int(datetime.now().timestamp() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(digest).decode("utf-8")

        parsed = parse.urlparse(webhook_url.strip())
        query = parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key not in {"timestamp", "sign"}]
        query.extend([("timestamp", timestamp), ("sign", sign)])
        return parse.urlunparse(parsed._replace(query=parse.urlencode(query)))
