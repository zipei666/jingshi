from __future__ import annotations

import threading
from datetime import datetime
from queue import Queue

from deduper import NewsDeduper
from models import MonitorConfig, MonitorEvent, MonitorEventType
from scraper import Jin10RssScraper


class MonitorController:
    """\u540e\u53f0\u76d1\u63a7\u7ebf\u7a0b\uff0c\u8d1f\u8d23\u6293\u53d6\u3001\u53bb\u91cd\u548c\u72b6\u6001\u4e0a\u62a5\u3002"""

    def __init__(self, event_queue: Queue, logger, config: MonitorConfig | None = None) -> None:
        self.event_queue = event_queue
        self.logger = logger
        self._config = config or MonitorConfig()
        self._config_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running:
            return False

        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="Jin10MonitorThread",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, wait: bool = False) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=10)

    def shutdown(self) -> None:
        self.stop(wait=True)

    def update_interval(self, seconds: float) -> None:
        with self._config_lock:
            self._config.interval_seconds = max(1.0, float(seconds))
        self._wake_event.set()
        self.logger.info("Refresh interval updated to %.1f seconds.", seconds)

    def get_config_snapshot(self) -> MonitorConfig:
        with self._config_lock:
            return MonitorConfig(
                url=self._config.url,
                interval_seconds=self._config.interval_seconds,
                initial_limit=self._config.initial_limit,
                steady_limit=self._config.steady_limit,
                headless=self._config.headless,
                timeout_ms=self._config.timeout_ms,
            )

    def _run_loop(self) -> None:
        config = self.get_config_snapshot()
        scraper = Jin10RssScraper(config, self.logger)
        deduper = NewsDeduper(max_size=5000)
        has_loaded_initial_items = False
        error_count = 0

        self.logger.info(
            "Monitor thread started. url=%s interval=%.1f",
            config.url,
            config.interval_seconds,
        )

        try:
            scraper.start()

            while not self._stop_event.is_set():
                config = self.get_config_snapshot()
                try:
                    # 首次启动时多拿一些初始快讯，后续轮询只保留较小窗口，
                    # 可以明显降低 DOM 提取、去重和排序的开销。
                    current_limit = config.initial_limit if not has_loaded_initial_items else config.steady_limit
                    items = scraper.fetch_items(limit=current_limit)
                    now = datetime.now()

                    if not items:
                        self._emit(
                            MonitorEvent(
                                event_type=MonitorEventType.STATUS,
                                message="heartbeat",
                                is_running=True,
                                last_refresh=now,
                            )
                        )
                        error_count = 0
                        interval_seconds = self.get_config_snapshot().interval_seconds
                        self._wake_event.wait(timeout=interval_seconds)
                        self._wake_event.clear()
                        continue

                    if not has_loaded_initial_items:
                        deduper.clear()
                        deduper.seed(items)
                        has_loaded_initial_items = True
                        self._emit(
                            MonitorEvent(
                                event_type=MonitorEventType.INITIAL_ITEMS,
                                message="initial-items-loaded",
                                items=items,
                                is_running=True,
                                last_refresh=now,
                            )
                        )
                        self.logger.info("Initial items loaded: %s", len(items))
                    else:
                        new_items = deduper.filter_new(items)
                        if new_items:
                            self._emit(
                                MonitorEvent(
                                    event_type=MonitorEventType.NEW_ITEMS,
                                    message=f"new-items:{len(new_items)}",
                                    items=new_items,
                                    is_running=True,
                                    last_refresh=now,
                                )
                            )
                            self.logger.info("New items found: %s", len(new_items))
                        else:
                            self._emit(
                                MonitorEvent(
                                    event_type=MonitorEventType.STATUS,
                                    message="heartbeat",
                                    is_running=True,
                                    last_refresh=now,
                                )
                            )

                    error_count = 0
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    self.logger.exception("Monitor loop failed.")
                    self._emit(
                        MonitorEvent(
                            event_type=MonitorEventType.ERROR,
                            message="monitor-error",
                            error=f"{type(exc).__name__}: {exc}",
                            is_running=True,
                            last_refresh=datetime.now(),
                        )
                    )

                    if error_count >= 2:
                        try:
                            scraper.reload_page()
                        except Exception:  # noqa: BLE001
                            self.logger.exception("Page reload failed; browser will be recreated if needed.")

                    if error_count >= 4:
                        scraper.close()
                        scraper = Jin10RssScraper(config, self.logger)
                        scraper.start()
                        error_count = 0

                if self._stop_event.is_set():
                    break

                interval_seconds = self.get_config_snapshot().interval_seconds
                self._wake_event.wait(timeout=interval_seconds)
                self._wake_event.clear()
        finally:
            scraper.close()
            self.logger.info("Monitor thread stopped.")
            self._emit(
                MonitorEvent(
                    event_type=MonitorEventType.STOPPED,
                    message="stopped",
                    is_running=False,
                    last_refresh=datetime.now(),
                )
            )

    def _emit(self, event: MonitorEvent) -> None:
        self.event_queue.put(event)
