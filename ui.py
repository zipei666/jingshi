from __future__ import annotations

import csv
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    pystray = None
    Image = None
    ImageDraw = None

from config import AppSettings, find_keyword_hits, load_app_settings, normalize_keywords, save_app_settings
from logger import copy_log_to, get_exports_dir
from models import FlashNewsItem, MonitorConfig, MonitorEvent, MonitorEventType, SOURCE_URL
from monitor import MonitorController
from news_analyzer import NewsAnalyzer
from notifier import DingTalkNotifier, DingTalkPushConfig, NotificationResult


TEXT = {
    "popup_title": "\u91d1\u5341\u5e02\u573a\u5feb\u8baf",
    "popup_hint": "\u5355\u51fb\u6253\u5f00\u8be6\u60c5 / \u5355\u51fb\u5173\u95ed",
    "badge_important": "\u91cd\u8981",
    "open_detail": "\u6253\u5f00\u8be6\u60c5",
    "placeholder_wait": "\u6682\u65e0\u5feb\u8baf\uff0c\u7b49\u5f85\u5f00\u59cb\u76d1\u63a7\u3002",
    "placeholder_empty": "\u5f53\u524d\u6ca1\u6709\u53ef\u663e\u793a\u7684\u5feb\u8baf\u3002",
    "tray_show": "\u663e\u793a\u4e3b\u7a97\u53e3",
    "tray_start": "\u5f00\u59cb\u76d1\u63a7",
    "tray_stop": "\u505c\u6b62\u76d1\u63a7",
    "tray_exit": "\u9000\u51fa\u7a0b\u5e8f",
    "app_title": "\u91d1\u5341\u5e02\u573a\u5feb\u8baf\u76d1\u63a7",
    "status_stopped": "\u5df2\u505c\u6b62",
    "status_starting": "\u6b63\u5728\u542f\u52a8...",
    "status_stopping": "\u6b63\u5728\u505c\u6b62...",
    "status_running": "\u8fd0\u884c\u4e2d",
    "status_retrying": "\u8fd0\u884c\u4e2d\uff08\u81ea\u52a8\u91cd\u8bd5\u4e2d\uff09",
    "label_status": "\u8fd0\u884c\u72b6\u6001\uff1a",
    "label_last_refresh": "\u4e0a\u6b21\u5237\u65b0\uff1a",
    "label_stats": "\u7edf\u8ba1\u4fe1\u606f\uff1a",
    "label_url": "\u76d1\u63a7\u7f51\u5740\uff1a",
    "label_error": "\u9519\u8bef\u72b6\u6001\uff1a",
    "label_keywords": "\u5173\u952e\u8bcd\uff1a",
    "label_dingtalk": "\u9489\u9489 Webhook\uff1a",
    "label_dingtalk_status": "\u63a8\u9001\u72b6\u6001\uff1a",
    "btn_start": "\u5f00\u59cb\u76d1\u63a7",
    "btn_stop": "\u505c\u6b62\u76d1\u63a7",
    "btn_clear": "\u6e05\u7a7a\u5217\u8868",
    "btn_copy": "\u590d\u5236\u9009\u4e2d\u5feb\u8baf",
    "btn_txt": "\u4fdd\u5b58\u5230 TXT",
    "btn_csv": "\u4fdd\u5b58\u5230 CSV",
    "btn_log": "\u5bfc\u51fa\u65e5\u5fd7",
    "btn_save_keywords": "\u4fdd\u5b58\u5173\u952e\u8bcd",
    "btn_save_webhook": "\u4fdd\u5b58 Webhook",
    "btn_test_webhook": "\u6d4b\u8bd5\u53d1\u9001",
    "label_interval": "\u5237\u65b0\u9891\u7387\uff1a",
    "check_important": "\u53ea\u770b\u91cd\u8981\u5feb\u8baf",
    "check_sound": "\u58f0\u97f3\u63d0\u9192",
    "check_popup": "\u5f39\u7a97\u901a\u77e5",
    "check_keyword_filter": "\u542f\u7528\u5173\u952e\u8bcd\u8fc7\u6ee4",
    "check_dingtalk": "\u542f\u7528\u9489\u9489\u63a8\u9001",
    "keyword_hint": "\u652f\u6301\u4e2d\u6587\u9017\u53f7\u3001\u82f1\u6587\u9017\u53f7\u3001\u7a7a\u683c\u6216\u6362\u884c\u5206\u9694",
    "keyword_hits": "\u547d\u4e2d\u5173\u952e\u8bcd\uff1a",
    "keyword_empty": "\u672a\u8bbe\u7f6e",
    "webhook_empty": "\u672a\u914d\u7f6e Webhook",
    "webhook_saved": "Webhook \u5df2\u4fdd\u5b58",
    "webhook_enabled_without_url": "\u5df2\u542f\u7528\u9489\u9489\u63a8\u9001\uff0c\u4f46 Webhook \u672a\u914d\u7f6e",
    "tray_hint": "\u63d0\u793a\uff1a\u6700\u5c0f\u5316\u540e\u4f1a\u8fdb\u5165\u7cfb\u7edf\u6258\u76d8\u5e76\u7ee7\u7eed\u540e\u53f0\u76d1\u63a7\u3002",
    "count_suffix": "\u6761",
    "clear_placeholder": "\u5217\u8868\u5df2\u6e05\u7a7a\uff0c\u7b49\u5f85\u65b0\u7684\u5feb\u8baf\u5230\u6765\u3002",
    "copy_title": "\u590d\u5236\u9009\u4e2d\u5feb\u8baf",
    "copy_pick_one": "\u8bf7\u5148\u5355\u51fb\u9009\u4e2d\u4e00\u6761\u5feb\u8baf\u3002",
    "copy_done": "\u5df2\u590d\u5236\u5230\u526a\u8d34\u677f\u3002",
    "save_txt_title": "\u4fdd\u5b58\u5230 TXT",
    "save_csv_title": "\u4fdd\u5b58\u5230 CSV",
    "save_empty": "\u5f53\u524d\u6ca1\u6709\u53ef\u5bfc\u51fa\u7684\u5feb\u8baf\u3002",
    "save_txt_dialog": "\u4fdd\u5b58\u5feb\u8baf\u5230 TXT",
    "save_csv_dialog": "\u4fdd\u5b58\u5feb\u8baf\u5230 CSV",
    "save_done": "\u5bfc\u51fa\u5b8c\u6210\uff1a\n{path}",
    "export_log_title": "\u5bfc\u51fa\u65e5\u5fd7",
    "export_log_dialog": "\u5bfc\u51fa\u65e5\u5fd7\u6587\u4ef6",
    "export_log_done": "\u65e5\u5fd7\u5df2\u5bfc\u51fa\u5230\uff1a\n{path}",
    "exit_title": "\u9000\u51fa\u7a0b\u5e8f",
    "exit_confirm": "\u9000\u51fa\u540e\u5c06\u505c\u6b62\u76d1\u63a7\u5e76\u5173\u95ed\u6d4f\u89c8\u5668\u8fdb\u7a0b\uff0c\u662f\u5426\u7ee7\u7eed\uff1f",
    "csv_time": "\u53d1\u5e03\u65f6\u95f4",
    "csv_content": "\u5feb\u8baf\u5185\u5bb9",
    "csv_vip": "VIP",
    "csv_important": "\u91cd\u8981",
    "csv_url": "\u8be6\u60c5\u94fe\u63a5",
    "yes": "\u662f",
    "no": "\u5426",
    "detail_link": "\u8be6\u60c5\u94fe\u63a5\uff1a",
    "tag_vip": "[VIP]",
    "tag_important": "[\u91cd\u8981]",
    "hero_subtitle": "\u5b9e\u65f6\u76ef\u76d8 \u00b7 \u589e\u91cf\u66f4\u65b0 \u00b7 \u5c3d\u91cf\u4e0d\u6253\u6270\u4f60\u7684\u64cd\u4f5c\u8282\u594f",
    "list_title": "\u5e02\u573a\u5feb\u8baf",
    "list_subtitle": "\u6309\u53d1\u5e03\u65f6\u95f4\u5012\u5e8f\u6392\u5217\uff0c\u6700\u65b0\u6d88\u606f\u56fa\u5b9a\u5728\u6700\u4e0a\u65b9",
    "section_actions": "\u64cd\u4f5c\u4e2d\u5fc3",
    "section_actions_desc": "\u5e38\u7528\u64cd\u4f5c\u96c6\u4e2d\u5728\u8fd9\u91cc\uff0c\u65b9\u4fbf\u5feb\u901f\u5f00\u59cb\u3001\u5bfc\u51fa\u548c\u6574\u7406\u3002",
    "section_preferences": "\u76d1\u63a7\u504f\u597d",
    "section_preferences_desc": "\u8c03\u6574\u5237\u65b0\u9891\u7387\u3001\u63d0\u793a\u65b9\u5f0f\u548c\u663e\u793a\u8303\u56f4\u3002",
    "section_keywords_title": "\u5173\u952e\u8bcd\u76d1\u63a7",
    "section_keywords_desc": "\u652f\u6301\u9017\u53f7\u3001\u7a7a\u683c\u6216\u6362\u884c\u5206\u9694\uff0c\u547d\u4e2d\u4efb\u610f\u4e00\u4e2a\u5173\u952e\u8bcd\u5c31\u4f1a\u89e6\u53d1\u3002",
    "section_dingtalk_title": "\u9489\u9489\u63a8\u9001\u8bbe\u7f6e",
    "section_dingtalk_desc": "\u53ea\u6709\u547d\u4e2d\u5173\u952e\u8bcd\u65f6\u624d\u4f1a\u5c1d\u8bd5\u63a8\u9001\uff0c\u53d1\u9001\u5728\u540e\u53f0\u8fdb\u884c\u3002",
    "section_controls_title": "\u64cd\u4f5c\u4e0e\u8bbe\u7f6e",
    "section_controls_desc": "\u5e38\u7528\u6309\u94ae\u3001\u663e\u793a\u504f\u597d\u3001\u5173\u952e\u8bcd\u548c\u9489\u9489\u914d\u7f6e\u90fd\u6536\u5728\u8fd9\u91cc\u3002",
    "tab_actions": "\u64cd\u4f5c",
    "tab_preferences": "\u504f\u597d",
    "tab_keywords": "\u5173\u952e\u8bcd",
    "tab_dingtalk": "\u9489\u9489",
    "error_ok": "\u5f53\u524d\u65e0\u5f02\u5e38\uff0c\u76d1\u63a7\u4f1a\u5728\u540e\u53f0\u6301\u7eed\u5237\u65b0\u3002",
}

PALETTE = {
    "window_bg": "#edf7f2",
    "surface": "#fbfffd",
    "surface_alt": "#f5fcf9",
    "panel_bg": "#f2faf6",
    "card_bg": "#fcfffd",
    "card_border": "#d6ebe3",
    "card_shadow": "#e6f2ed",
    "accent": "#2f9e8f",
    "accent_dark": "#247c70",
    "accent_soft": "#d9f1ea",
    "accent_pale": "#ebf8f4",
    "heading": "#173b37",
    "text": "#26433f",
    "muted": "#6c8a85",
    "link": "#2c7da0",
    "warning_bg": "#fff7db",
    "warning_border": "#e7c76f",
    "warning_text": "#8a6110",
    "danger_bg": "#fff1f1",
    "danger_border": "#efb3b3",
    "danger_text": "#a33f3f",
    "vip_bg": "#fff7ef",
    "vip_border": "#f0c88c",
    "important_bg": "#fff4f4",
    "important_border": "#efb1b1",
    "selected_bg": "#e5f6f0",
    "selected_border": "#58ac9f",
    "highlight_bg": "#fff7cf",
    "highlight_border": "#e0bb56",
    "hit_bg": "#eef8d7",
    "hit_text": "#55752b",
    "input_bg": "#ffffff",
    "input_border": "#c8e0d8",
    "button_soft_bg": "#ffffff",
    "button_soft_hover": "#f2fbf7",
    "button_soft_disabled": "#eef4f1",
    "button_soft_text": "#214540",
    "error_surface": "#fff7f5",
}

FONTS = {
    "hero_title": ("Microsoft YaHei UI", 18, "bold"),
    "hero_subtitle": ("Microsoft YaHei UI", 10),
    "section_title": ("Microsoft YaHei UI", 11, "bold"),
    "section_subtitle": ("Microsoft YaHei UI", 9),
    "metric_title": ("Microsoft YaHei UI", 9),
    "metric_value": ("Microsoft YaHei UI", 10, "bold"),
    "body": ("Microsoft YaHei UI", 10),
    "small": ("Microsoft YaHei UI", 9),
    "tiny": ("Microsoft YaHei UI", 8),
    "button": ("Microsoft YaHei UI", 9, "bold"),
}

MAX_RENDERED_NEWS_CARDS = 120
MAX_STORED_NEWS_ITEMS = 2500
RESIZE_DEBOUNCE_MS = 120


class PopupNotificationManager:
    """\u8f7b\u91cf\u5f39\u7a97\u63d0\u9192\u7ba1\u7406\u5668\u3002"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.popups: list[tk.Toplevel] = []

    def show(self, item: FlashNewsItem, on_open) -> None:
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg="#0f172a")

        frame = tk.Frame(popup, bg="#0f172a", bd=1, relief="solid")
        frame.pack(fill="both", expand=True)

        title = tk.Label(
            frame,
            text=TEXT["popup_title"],
            font=("Microsoft YaHei UI", 10, "bold"),
            fg="#f8fafc",
            bg="#0f172a",
            anchor="w",
        )
        title.pack(fill="x", padx=12, pady=(10, 4))

        content_text = item.display_text().replace("\n", " ")
        if len(content_text) > 120:
            content_text = content_text[:117] + "..."

        body = tk.Label(
            frame,
            text=content_text,
            justify="left",
            wraplength=340,
            fg="#e2e8f0",
            bg="#0f172a",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        body.pack(fill="x", padx=12, pady=(0, 8))

        hint = tk.Label(
            frame,
            text=TEXT["popup_hint"],
            fg="#93c5fd",
            bg="#0f172a",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        )
        hint.pack(fill="x", padx=12, pady=(0, 10))

        def close_popup(_event=None) -> None:
            if popup.winfo_exists():
                popup.destroy()
            self._reflow()

        def open_popup(_event=None) -> None:
            close_popup()
            on_open(item)

        click_handler = open_popup if item.detail_url else close_popup
        for widget in (frame, title, body, hint):
            widget.bind("<Button-1>", click_handler)

        popup.update_idletasks()
        width = max(340, popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        offset = sum(
            window.winfo_height() + 12
            for window in self.popups
            if window.winfo_exists()
        )
        x = screen_width - width - 28
        y = max(40, screen_height - height - 56 - offset)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.after(5000, close_popup)

        self.popups.insert(0, popup)
        self._reflow()

    def _reflow(self) -> None:
        valid = [window for window in self.popups if window.winfo_exists()]
        self.popups = valid
        offset = 0
        for popup in valid:
            popup.update_idletasks()
            width = popup.winfo_width()
            height = popup.winfo_height()
            screen_width = popup.winfo_screenwidth()
            screen_height = popup.winfo_screenheight()
            x = screen_width - width - 28
            y = max(40, screen_height - height - 56 - offset)
            popup.geometry(f"{width}x{height}+{x}+{y}")
            offset += height + 12


class NewsCard:
    def __init__(self, panel, item: FlashNewsItem) -> None:
        self.panel = panel
        self.item = item
        self.frame = tk.Frame(panel.content_frame, bd=1, relief="solid", cursor="hand2")
        self.inner_frame = tk.Frame(self.frame)
        self.inner_frame.pack(fill="both", expand=True, padx=1, pady=1)

        self.header = tk.Frame(self.inner_frame)
        self.header.pack(fill="x", padx=12, pady=(10, 6))

        self.badge_frame = tk.Frame(self.header)
        self.badge_frame.pack(side="left")
        self.badge_labels: list[tk.Label] = []

        if item.is_vip:
            self.badge_labels.append(self._create_badge("VIP", "#fff7ed", "#c2410c"))
        if item.is_important:
            self.badge_labels.append(
                self._create_badge(TEXT["badge_important"], "#fef2f2", "#b91c1c")
            )

        self.time_label = tk.Label(
            self.header,
            text=f"[{item.display_time}]",
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        )
        self.time_label.pack(side="left", padx=(0, 10))

        self.link_label = tk.Label(
            self.header,
            text=TEXT["open_detail"] if item.detail_url else "",
            fg="#2563eb",
            cursor="hand2" if item.detail_url else "arrow",
            font=("Microsoft YaHei UI", 9, "underline"),
        )
        self.link_label.pack(side="right")

        self.content_label = tk.Label(
            self.inner_frame,
            text=item.content,
            justify="left",
            anchor="w",
            font=("Microsoft YaHei UI", 10),
            wraplength=820,
        )
        self.content_label.pack(fill="x", padx=12, pady=(0, 8))

        self.hit_label: tk.Label | None = None
        if item.matched_keywords:
            self.hit_label = tk.Label(
                self.inner_frame,
                text=f"{TEXT['keyword_hits']} {', '.join(item.matched_keywords)}",
                anchor="w",
                justify="left",
                font=("Microsoft YaHei UI", 8, "bold"),
                padx=8,
                pady=3,
            )
            self.hit_label.pack(fill="x", padx=12, pady=(0, 8))

        self.meta_label = tk.Label(
            self.inner_frame,
            text=self._build_meta_text(item),
            anchor="w",
            justify="left",
            font=("Microsoft YaHei UI", 8),
        )
        self.meta_label.pack(fill="x", padx=12, pady=(0, 10))

        self._bind_widget(self.frame)
        self._bind_widget(self.inner_frame)
        self._bind_widget(self.header)
        self._bind_widget(self.badge_frame)
        self._bind_widget(self.time_label)
        self._bind_widget(self.content_label)
        self._bind_widget(self.meta_label)
        if self.hit_label is not None:
            self._bind_widget(self.hit_label)
        for label in self.badge_labels:
            self._bind_widget(label)

        if item.detail_url:
            self.link_label.bind("<Button-1>", lambda _event: self.panel.on_open(self.item))
        self.apply_style(selected=False, highlighted=False)

    def update_wraplength(self, width: int) -> None:
        wraplength = max(360, width - 96)
        self.content_label.configure(wraplength=wraplength)
        self.meta_label.configure(wraplength=wraplength)
        if self.hit_label is not None:
            self.hit_label.configure(wraplength=wraplength)

    def apply_style(self, selected: bool, highlighted: bool) -> None:
        if highlighted:
            bg_color = "#fff7bf"
            border_color = "#f59e0b"
        elif selected:
            bg_color = "#dbeafe"
            border_color = "#2563eb"
        elif self.item.is_vip:
            bg_color = "#fff8ef"
            border_color = "#fdba74"
        elif self.item.is_important:
            bg_color = "#fff5f5"
            border_color = "#fca5a5"
        else:
            bg_color = "#ffffff"
            border_color = "#d0d7de"

        self.frame.configure(bg=border_color)
        self.inner_frame.configure(bg=bg_color)
        for widget in (
            self.header,
            self.badge_frame,
            self.time_label,
            self.content_label,
            self.meta_label,
            self.link_label,
        ):
            widget.configure(bg=bg_color)

        self.time_label.configure(fg="#0f172a")
        self.content_label.configure(fg="#111827")
        self.meta_label.configure(fg="#64748b")

        if self.hit_label is not None:
            hit_bg = "#fde68a" if highlighted else "#fef3c7"
            self.hit_label.configure(bg=hit_bg, fg="#92400e")

    def _create_badge(self, text: str, bg_color: str, fg_color: str) -> tk.Label:
        label = tk.Label(
            self.badge_frame,
            text=text,
            bg=bg_color,
            fg=fg_color,
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=8,
            pady=2,
        )
        label.pack(side="left", padx=(0, 6))
        return label

    def _build_meta_text(self, item: FlashNewsItem) -> str:
        parts = []
        analysis_parts = self._build_rule_analysis_parts(item)
        if analysis_parts:
            parts.append("规则：" + " / ".join(analysis_parts))
        if item.published_at:
            parts.append(item.published_at.strftime("%Y-%m-%d %H:%M:%S"))
        elif item.selected_date:
            parts.append(f"{item.selected_date} {item.display_time}")
        if item.detail_url:
            parts.append(item.detail_url)
        return " | ".join(parts)

    @staticmethod
    def _build_rule_analysis_parts(item: FlashNewsItem) -> list[str]:
        parts: list[str] = []
        if item.analysis_level:
            parts.append(f"等级{item.analysis_level}")
        if item.analysis_markets:
            parts.append("影响：" + "、".join(item.analysis_markets[:4]))
        if item.analysis_direction and item.analysis_direction != "不确定":
            parts.append(item.analysis_direction)
        return parts

    def _bind_widget(self, widget: tk.Widget) -> None:
        widget.bind("<Button-1>", lambda _event: self.panel.on_select(self.item))
        widget.bind("<Double-Button-1>", lambda _event: self.panel.on_open(self.item))


class NewsListPanel(tk.Frame):
    def __init__(self, master, on_select, on_open) -> None:
        super().__init__(master, bg="#eef2f7")
        self.on_select = on_select
        self.on_open = on_open

        self.canvas = tk.Canvas(self, bg="#eef2f7", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content_frame = tk.Frame(self.canvas, bg="#eef2f7")
        self.window_id = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.cards: dict[str, NewsCard] = {}
        self.selected_uid: str | None = None
        self.highlighted_uids: set[str] = set()
        self.placeholder_label: tk.Label | None = None
        self._pending_wrap_width: int | None = None
        self._last_wrap_width: int | None = None
        self._wrap_after_id: str | None = None

        self.content_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.show_placeholder(TEXT["placeholder_wait"])

    def show_placeholder(self, text: str) -> None:
        self.clear()
        self.placeholder_label = tk.Label(
            self.content_frame,
            text=text,
            bg="#eef2f7",
            fg="#64748b",
            font=("Microsoft YaHei UI", 11),
            pady=24,
        )
        self.placeholder_label.pack(fill="both", expand=True)

    def set_items(
        self,
        items: list[FlashNewsItem],
        selected_uid: str | None = None,
        preserve_scroll: bool = False,
    ) -> None:
        scroll_position = self.get_scroll_fraction() if preserve_scroll else 0.0
        keep_highlights = set(self.highlighted_uids)
        visible_uids = {item.uid for item in items}

        self.clear(reset_state=False)
        self.selected_uid = selected_uid if selected_uid in visible_uids else None
        self.highlighted_uids = {uid for uid in keep_highlights if uid in visible_uids}

        if not items:
            self.placeholder_label = tk.Label(
                self.content_frame,
                text=TEXT["placeholder_empty"],
                bg="#eef2f7",
                fg="#64748b",
                font=("Microsoft YaHei UI", 11),
                pady=24,
            )
            self.placeholder_label.pack(fill="both", expand=True)
            self.after_idle(self._on_frame_configure)
            if not preserve_scroll:
                self.scroll_to_top()
            return

        for item in items:
            self._insert_card(item)
        self._refresh_styles()

        if preserve_scroll:
            self.after_idle(lambda position=scroll_position: self._restore_scroll(position))
        else:
            self.after_idle(self.scroll_to_top)

    def clear(self, reset_state: bool = True) -> None:
        if self._wrap_after_id is not None:
            self.after_cancel(self._wrap_after_id)
            self._wrap_after_id = None
        for child in list(self.content_frame.winfo_children()):
            child.destroy()
        self.cards.clear()
        self.placeholder_label = None
        if reset_state:
            self.highlighted_uids.clear()
            self.selected_uid = None

    def highlight(self, uid: str) -> None:
        if uid not in self.cards:
            return
        self.highlighted_uids.add(uid)
        self._refresh_styles()
        self.after(5000, lambda item_uid=uid: self.clear_highlight(item_uid))

    def clear_highlight(self, uid: str) -> None:
        if uid in self.highlighted_uids:
            self.highlighted_uids.discard(uid)
            self._refresh_styles()

    def set_selected(self, uid: str | None) -> None:
        self.selected_uid = uid
        self._refresh_styles()

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def get_scroll_fraction(self) -> float:
        try:
            return float(self.canvas.yview()[0])
        except Exception:
            return 0.0

    def is_near_top(self) -> bool:
        return self.get_scroll_fraction() <= 0.02

    def _restore_scroll(self, position: float) -> None:
        self._on_frame_configure()
        self.canvas.yview_moveto(max(0.0, min(position, 1.0)))

    def _insert_card(self, item: FlashNewsItem) -> NewsCard:
        card = NewsCard(self, item)
        card.frame.pack(fill="x", padx=12, pady=(12, 0))
        width = self._pending_wrap_width or self.canvas.winfo_width()
        card.update_wraplength(width)
        self.cards[item.uid] = card
        return card

    def _refresh_styles(self) -> None:
        for uid, card in self.cards.items():
            card.apply_style(
                selected=(uid == self.selected_uid),
                highlighted=(uid in self.highlighted_uids),
            )

    def _on_frame_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        width = max(1, int(event.width))
        self.canvas.itemconfigure(self.window_id, width=width)
        self._pending_wrap_width = width

        if width == self._last_wrap_width:
            return

        if self._wrap_after_id is not None:
            self.after_cancel(self._wrap_after_id)
        self._wrap_after_id = self.after(RESIZE_DEBOUNCE_MS, self._apply_pending_wraplengths)

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _apply_pending_wraplengths(self) -> None:
        self._wrap_after_id = None
        if self._pending_wrap_width is None or self._pending_wrap_width == self._last_wrap_width:
            return

        self._last_wrap_width = self._pending_wrap_width
        for card in self.cards.values():
            card.update_wraplength(self._pending_wrap_width)


class SystemTrayManager:
    def __init__(self, app) -> None:
        self.app = app
        self.icon = None
        self.thread = None

    def show(self) -> None:
        if pystray is None or Image is None or ImageDraw is None:
            return

        if self.icon is None:
            image = self._build_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem(
                    TEXT["tray_show"],
                    lambda _icon, _item: self.app.root.after(0, self.app.restore_from_tray),
                ),
                pystray.MenuItem(
                    TEXT["tray_start"],
                    lambda _icon, _item: self.app.root.after(0, self.app.start_monitoring),
                ),
                pystray.MenuItem(
                    TEXT["tray_stop"],
                    lambda _icon, _item: self.app.root.after(0, self.app.stop_monitoring),
                ),
                pystray.MenuItem(
                    TEXT["tray_exit"],
                    lambda _icon, _item: self.app.root.after(0, self.app.exit_application),
                ),
            )
            self.icon = pystray.Icon(
                "jin10_flash_monitor",
                image,
                TEXT["app_title"],
                menu=menu,
            )
            self.thread = self._start_icon_thread()
        else:
            self.icon.visible = True

    def hide(self) -> None:
        if self.icon is not None:
            self.icon.visible = False

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def _start_icon_thread(self):
        import threading

        thread = threading.Thread(target=self.icon.run, name="TrayIconThread", daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _build_icon_image():
        image = Image.new("RGBA", (64, 64), (237, 247, 242, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(47, 158, 143, 255))
        draw.rounded_rectangle((16, 15, 48, 25), radius=4, fill=(251, 255, 253, 255))
        draw.rounded_rectangle((16, 30, 40, 38), radius=4, fill=(235, 248, 244, 255))
        draw.rounded_rectangle((16, 43, 52, 51), radius=4, fill=(251, 255, 253, 255))
        return image


class Jin10FlashMonitorApp:
    def __init__(self, root: tk.Tk, logger) -> None:
        self.root = root
        self.logger = logger
        self.root.title(TEXT["app_title"])
        self.root.geometry("1120x780")
        self.root.minsize(860, 560)
        self.root.configure(bg="#f8fafc")

        self.event_queue: Queue = Queue()
        self.monitor = MonitorController(
            self.event_queue,
            logger,
            MonitorConfig(interval_seconds=2.0, initial_limit=40, headless=True),
        )

        self.items: list[FlashNewsItem] = []
        self.items_by_uid: dict[str, FlashNewsItem] = {}
        self.selected_uid: str | None = None
        self.is_exiting = False
        self.is_hidden_to_tray = False
        self._arrival_counter = 0

        self.settings = load_app_settings()
        self.keywords = normalize_keywords(self.settings.keyword_text)
        self.news_analyzer = NewsAnalyzer(logger)
        self.notifier = DingTalkNotifier(
            logger,
            initial_sent_keys=self.settings.sent_message_keys,
        )

        self.status_var = tk.StringVar(value=TEXT["status_stopped"])
        self.last_refresh_var = tk.StringVar(value="--")
        self.url_var = tk.StringVar(value=SOURCE_URL)
        self.error_var = tk.StringVar(value="")
        self.error_display_var = tk.StringVar(value=TEXT["error_ok"])
        self.count_var = tk.StringVar(value="")
        self.dingtalk_status_var = tk.StringVar(
            value=TEXT["webhook_empty"] if not self.settings.webhook_url else TEXT["webhook_saved"]
        )
        self.interval_var = tk.StringVar(value="2")
        self.important_only_var = tk.BooleanVar(value=False)
        self.sound_var = tk.BooleanVar(value=True)
        self.popup_var = tk.BooleanVar(value=True)
        self.keyword_filter_var = tk.BooleanVar(value=self.settings.keyword_filter_enabled)
        self.webhook_url_var = tk.StringVar(value=self.settings.webhook_url)
        self.webhook_enabled_var = tk.BooleanVar(value=self.settings.webhook_enabled)

        self.popup_manager = PopupNotificationManager(root)
        self.tray_manager = SystemTrayManager(self)
        self.keyword_input: tk.Text | None = None
        self.status_badge_label: tk.Label | None = None
        self.error_value_label: tk.Label | None = None

        self.status_var.trace_add("write", self._refresh_status_badge)
        self.error_var.trace_add("write", self._refresh_error_display)

        self._build_ui()
        self._load_settings_into_ui()
        self._update_count_label()
        self._sync_button_states(False)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Unmap>", self._on_minimize)
        self.root.after(200, self._poll_monitor_events)
        self.root.after(800, self.start_monitoring)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        top_frame = ttk.Frame(self.root, padding=(12, 12, 12, 8))
        top_frame.pack(fill="x")
        top_frame.columnconfigure(1, weight=1)
        top_frame.columnconfigure(3, weight=1)

        ttk.Label(top_frame, text=TEXT["label_status"]).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(top_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

        ttk.Label(top_frame, text=TEXT["label_last_refresh"]).grid(row=0, column=2, sticky="w", padx=(18, 6))
        ttk.Label(top_frame, textvariable=self.last_refresh_var).grid(row=0, column=3, sticky="w")

        ttk.Label(top_frame, text=TEXT["label_stats"]).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Label(top_frame, textvariable=self.count_var).grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(top_frame, text=TEXT["label_url"]).grid(row=1, column=2, sticky="w", padx=(18, 6), pady=(8, 0))
        ttk.Label(top_frame, textvariable=self.url_var).grid(row=1, column=3, sticky="w", pady=(8, 0))

        ttk.Label(top_frame, text=TEXT["label_error"]).grid(row=2, column=0, sticky="nw", padx=(0, 6), pady=(8, 0))
        ttk.Label(top_frame, textvariable=self.error_var, foreground="#b91c1c").grid(
            row=2,
            column=1,
            columnspan=3,
            sticky="w",
            pady=(8, 0),
        )

        center_frame = ttk.Frame(self.root, padding=(12, 0, 12, 0))
        center_frame.pack(fill="both", expand=True)
        self.news_panel = NewsListPanel(
            center_frame,
            on_select=self._on_select_item,
            on_open=self._open_item_detail,
        )
        self.news_panel.pack(fill="both", expand=True)

        bottom_frame = ttk.Frame(self.root, padding=12)
        bottom_frame.pack(fill="x")

        button_row = ttk.Frame(bottom_frame)
        button_row.pack(fill="x")

        self.start_button = ttk.Button(button_row, text=TEXT["btn_start"], command=self.start_monitoring)
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(button_row, text=TEXT["btn_stop"], command=self.stop_monitoring)
        self.stop_button.pack(side="left", padx=(0, 8))

        ttk.Button(button_row, text=TEXT["btn_clear"], command=self.clear_list).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text=TEXT["btn_copy"], command=self.copy_selected_item).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text=TEXT["btn_txt"], command=self.save_to_txt).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text=TEXT["btn_csv"], command=self.save_to_csv).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text=TEXT["btn_log"], command=self.export_log).pack(side="left")

        option_row = ttk.Frame(bottom_frame)
        option_row.pack(fill="x", pady=(10, 0))

        ttk.Label(option_row, text=TEXT["label_interval"]).pack(side="left")
        interval_box = ttk.Combobox(
            option_row,
            width=6,
            state="readonly",
            textvariable=self.interval_var,
            values=["1", "2", "5", "10"],
        )
        interval_box.pack(side="left", padx=(0, 14))
        interval_box.bind("<<ComboboxSelected>>", self._on_interval_change)

        ttk.Checkbutton(
            option_row,
            text=TEXT["check_important"],
            variable=self.important_only_var,
            command=self._on_display_filter_change,
        ).pack(side="left", padx=(0, 14))

        ttk.Checkbutton(option_row, text=TEXT["check_sound"], variable=self.sound_var).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(option_row, text=TEXT["check_popup"], variable=self.popup_var).pack(side="left", padx=(0, 14))

        ttk.Label(option_row, text=TEXT["tray_hint"], foreground="#475569").pack(side="right")

        keyword_row = ttk.Frame(bottom_frame)
        keyword_row.pack(fill="x", pady=(10, 0))
        keyword_row.columnconfigure(1, weight=1)

        ttk.Label(keyword_row, text=TEXT["label_keywords"]).grid(row=0, column=0, sticky="nw", padx=(0, 8), pady=(3, 0))

        self.keyword_input = tk.Text(
            keyword_row,
            height=3,
            wrap="word",
            relief="solid",
            bd=1,
            font=("Microsoft YaHei UI", 10),
        )
        self.keyword_input.grid(row=0, column=1, sticky="ew")

        keyword_actions = ttk.Frame(keyword_row)
        keyword_actions.grid(row=0, column=2, sticky="nw", padx=(12, 0))

        ttk.Button(keyword_actions, text=TEXT["btn_save_keywords"], command=self._save_keywords).pack(anchor="w")
        ttk.Checkbutton(
            keyword_actions,
            text=TEXT["check_keyword_filter"],
            variable=self.keyword_filter_var,
            command=self._on_keyword_filter_toggle,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(keyword_actions, text=TEXT["keyword_hint"], foreground="#64748b").pack(anchor="w", pady=(8, 0))

        dingtalk_row = ttk.Frame(bottom_frame)
        dingtalk_row.pack(fill="x", pady=(10, 0))
        dingtalk_row.columnconfigure(1, weight=1)

        ttk.Label(dingtalk_row, text=TEXT["label_dingtalk"]).grid(row=0, column=0, sticky="w", padx=(0, 8))
        webhook_entry = ttk.Entry(dingtalk_row, textvariable=self.webhook_url_var)
        webhook_entry.grid(row=0, column=1, sticky="ew")

        dingtalk_actions = ttk.Frame(dingtalk_row)
        dingtalk_actions.grid(row=0, column=2, sticky="nw", padx=(12, 0))

        ttk.Button(
            dingtalk_actions,
            text=TEXT["btn_save_webhook"],
            command=self._save_dingtalk_settings,
        ).pack(anchor="w")
        ttk.Checkbutton(
            dingtalk_actions,
            text=TEXT["check_dingtalk"],
            variable=self.webhook_enabled_var,
            command=self._on_dingtalk_toggle,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Button(
            dingtalk_actions,
            text=TEXT["btn_test_webhook"],
            command=self._send_test_webhook,
        ).pack(anchor="w", pady=(8, 0))

        dingtalk_meta_row = ttk.Frame(bottom_frame)
        dingtalk_meta_row.pack(fill="x", pady=(8, 0))
        dingtalk_meta_row.columnconfigure(1, weight=1)

        ttk.Label(dingtalk_meta_row, text=TEXT["label_dingtalk_status"]).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(dingtalk_meta_row, textvariable=self.dingtalk_status_var, foreground="#0f766e").grid(
            row=0,
            column=1,
            sticky="w",
        )

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.option_add("*TCombobox*Listbox.font", "Microsoft YaHei UI 10")

        style.configure("TFrame", background=PALETTE["window_bg"])
        style.configure(
            "Primary.TButton",
            font=FONTS["button"],
            padding=(14, 8),
            background=PALETTE["accent"],
            foreground="#ffffff",
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", PALETTE["accent_dark"]),
                ("pressed", PALETTE["accent_dark"]),
                ("disabled", PALETTE["button_soft_disabled"]),
            ],
            foreground=[("disabled", "#9ab1ac")],
        )
        style.configure(
            "Soft.TButton",
            font=FONTS["button"],
            padding=(14, 8),
            background=PALETTE["button_soft_bg"],
            foreground=PALETTE["button_soft_text"],
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Soft.TButton",
            background=[
                ("active", PALETTE["button_soft_hover"]),
                ("pressed", PALETTE["button_soft_hover"]),
                ("disabled", PALETTE["button_soft_disabled"]),
            ],
            foreground=[("disabled", "#97aaa6")],
        )
        style.configure(
            "Surface.TCheckbutton",
            background=PALETTE["surface"],
            foreground=PALETTE["text"],
            font=FONTS["body"],
        )
        style.map(
            "Surface.TCheckbutton",
            background=[("active", PALETTE["surface"])],
            foreground=[("disabled", "#97aaa6")],
        )
        style.configure(
            "Surface.TEntry",
            fieldbackground=PALETTE["input_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["input_border"],
            lightcolor=PALETTE["input_border"],
            darkcolor=PALETTE["input_border"],
            padding=8,
        )
        style.configure(
            "Surface.TCombobox",
            fieldbackground=PALETTE["input_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["input_border"],
            lightcolor=PALETTE["input_border"],
            darkcolor=PALETTE["input_border"],
            padding=6,
        )
        style.map(
            "Surface.TCombobox",
            fieldbackground=[("readonly", PALETTE["input_bg"])],
            selectbackground=[("readonly", PALETTE["accent_pale"])],
            selectforeground=[("readonly", PALETTE["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=PALETTE["accent_soft"],
            troughcolor=PALETTE["panel_bg"],
            bordercolor=PALETTE["panel_bg"],
            arrowcolor=PALETTE["accent_dark"],
        )
        style.configure(
            "Fresh.TNotebook",
            background=PALETTE["surface"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "Fresh.TNotebook.Tab",
            font=FONTS["small"],
            padding=(14, 8),
            background=PALETTE["accent_pale"],
            foreground=PALETTE["text"],
            borderwidth=0,
        )
        style.map(
            "Fresh.TNotebook.Tab",
            background=[
                ("selected", PALETTE["surface_alt"]),
                ("active", PALETTE["accent_soft"]),
            ],
            foreground=[
                ("selected", PALETTE["heading"]),
                ("active", PALETTE["heading"]),
            ],
        )

    def _create_surface(self, parent, padx: int = 18, pady: int = 18) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=PALETTE["surface"],
            highlightthickness=1,
            highlightbackground=PALETTE["card_border"],
            padx=padx,
            pady=pady,
        )
        return frame

    @staticmethod
    def _create_section_header(parent, title: str, subtitle: str) -> None:
        tk.Label(
            parent,
            text=title,
            font=FONTS["section_title"],
            fg=PALETTE["heading"],
            bg=PALETTE["surface"],
        ).pack(anchor="w")
        tk.Label(
            parent,
            text=subtitle,
            font=FONTS["section_subtitle"],
            fg=PALETTE["muted"],
            bg=PALETTE["surface"],
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

    def _create_metric_tile(
        self,
        parent,
        title: str,
        variable: tk.StringVar,
        row: int,
        column: int,
    ) -> None:
        tile = tk.Frame(
            parent,
            bg=PALETTE["surface_alt"],
            highlightthickness=1,
            highlightbackground=PALETTE["card_border"],
        )
        tile.grid(row=row, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0), pady=(0, 10))
        tk.Label(
            tile,
            text=title,
            font=FONTS["metric_title"],
            fg=PALETTE["muted"],
            bg=PALETTE["surface_alt"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Label(
            tile,
            textvariable=variable,
            font=FONTS["metric_value"],
            fg=PALETTE["heading"],
            bg=PALETTE["surface_alt"],
            justify="left",
            wraplength=420,
        ).pack(anchor="w", fill="x", padx=14, pady=(0, 12))

    def _refresh_status_badge(self, *_args) -> None:
        if self.status_badge_label is None:
            return

        status_text = self.status_var.get()
        if status_text == TEXT["status_running"]:
            bg_color = PALETTE["accent_soft"]
            fg_color = PALETTE["accent_dark"]
        elif status_text == TEXT["status_retrying"]:
            bg_color = PALETTE["warning_bg"]
            fg_color = PALETTE["warning_text"]
        elif status_text == TEXT["status_stopped"]:
            bg_color = "#eef4f1"
            fg_color = PALETTE["muted"]
        else:
            bg_color = PALETTE["surface_alt"]
            fg_color = PALETTE["heading"]

        self.status_badge_label.configure(bg=bg_color, fg=fg_color)

    def _refresh_error_display(self, *_args) -> None:
        if self.error_value_label is None:
            self.error_display_var.set(self.error_var.get() or TEXT["error_ok"])
            return

        error_text = self.error_var.get().strip()
        if error_text:
            self.error_display_var.set(error_text)
            self.error_value_label.configure(fg=PALETTE["danger_text"])
        else:
            self.error_display_var.set(TEXT["error_ok"])
            self.error_value_label.configure(fg=PALETTE["muted"])

    def start_monitoring(self) -> None:
        if self.monitor.is_running:
            return

        self.status_var.set(TEXT["status_starting"])
        self.error_var.set("")
        self.monitor.start()
        self._sync_button_states(True)

    def stop_monitoring(self) -> None:
        if not self.monitor.is_running:
            return

        self.status_var.set(TEXT["status_stopping"])
        self.monitor.stop(wait=False)
        self._sync_button_states(False)

    def clear_list(self) -> None:
        self.items.clear()
        self.items_by_uid.clear()
        self.selected_uid = None
        self._arrival_counter = 0
        self.news_panel.show_placeholder(TEXT["clear_placeholder"])
        self._update_count_label()

    def copy_selected_item(self) -> None:
        item = self._get_selected_item()
        if item is None:
            messagebox.showinfo(TEXT["copy_title"], TEXT["copy_pick_one"])
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(self._format_item_for_text(item))
        self.root.update()
        messagebox.showinfo(TEXT["copy_title"], TEXT["copy_done"])

    def save_to_txt(self) -> None:
        items = self._get_visible_items()
        if not items:
            messagebox.showinfo(TEXT["save_txt_title"], TEXT["save_empty"])
            return

        exports_dir = get_exports_dir()
        default_name = f"jin10_flash_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path = filedialog.asksaveasfilename(
            title=TEXT["save_txt_dialog"],
            initialdir=str(exports_dir),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
        )
        if not path:
            return

        Path(path).write_text(
            "\n\n".join(self._format_item_for_text(item) for item in items),
            encoding="utf-8",
        )
        messagebox.showinfo(TEXT["save_txt_title"], TEXT["save_done"].format(path=path))

    def save_to_csv(self) -> None:
        items = self._get_visible_items()
        if not items:
            messagebox.showinfo(TEXT["save_csv_title"], TEXT["save_empty"])
            return

        exports_dir = get_exports_dir()
        default_name = f"jin10_flash_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = filedialog.asksaveasfilename(
            title=TEXT["save_csv_dialog"],
            initialdir=str(exports_dir),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    TEXT["csv_time"],
                    TEXT["csv_content"],
                    TEXT["csv_vip"],
                    TEXT["csv_important"],
                    TEXT["csv_url"],
                ],
            )
            writer.writeheader()
            for item in items:
                writer.writerow(
                    {
                        TEXT["csv_time"]: self._get_item_time_text(item),
                        TEXT["csv_content"]: item.content.replace("\n", " "),
                        TEXT["csv_vip"]: TEXT["yes"] if item.is_vip else TEXT["no"],
                        TEXT["csv_important"]: TEXT["yes"] if item.is_important else TEXT["no"],
                        TEXT["csv_url"]: item.detail_url,
                    }
                )

        messagebox.showinfo(TEXT["save_csv_title"], TEXT["save_done"].format(path=path))

    def export_log(self) -> None:
        exports_dir = get_exports_dir()
        default_name = f"jin10_flash_monitor_log_{datetime.now():%Y%m%d_%H%M%S}.log"
        path = filedialog.asksaveasfilename(
            title=TEXT["export_log_dialog"],
            initialdir=str(exports_dir),
            initialfile=default_name,
            defaultextension=".log",
            filetypes=[("Log Files", "*.log")],
        )
        if not path:
            return

        copy_log_to(path)
        messagebox.showinfo(TEXT["export_log_title"], TEXT["export_log_done"].format(path=path))

    def restore_from_tray(self) -> None:
        if not self.is_hidden_to_tray:
            return

        self.is_hidden_to_tray = False
        self.tray_manager.hide()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def minimize_to_tray(self) -> None:
        if pystray is None or self.is_hidden_to_tray:
            return
        self.is_hidden_to_tray = True
        self.root.withdraw()
        self.tray_manager.show()

    def on_close(self) -> None:
        if self.is_exiting:
            return

        if not messagebox.askokcancel(TEXT["exit_title"], TEXT["exit_confirm"]):
            return
        self.exit_application()

    def exit_application(self) -> None:
        if self.is_exiting:
            return

        self.is_exiting = True
        self._save_settings()
        self.monitor.shutdown()
        self.notifier.shutdown()
        self.tray_manager.stop()
        self.root.destroy()

    def _poll_monitor_events(self) -> None:
        while True:
            try:
                event: MonitorEvent = self.event_queue.get_nowait()
            except Empty:
                break
            self._handle_monitor_event(event)

        self._poll_notifier_results()

        if not self.is_exiting and self.root.winfo_exists():
            self.root.after(200, self._poll_monitor_events)

    def _handle_monitor_event(self, event: MonitorEvent) -> None:
        if event.last_refresh:
            self.last_refresh_var.set(event.last_refresh.strftime("%Y-%m-%d %H:%M:%S"))

        if event.event_type == MonitorEventType.INITIAL_ITEMS:
            self.error_var.set("")
            self.status_var.set(TEXT["status_running"])
            self._replace_items(event.items)
        elif event.event_type == MonitorEventType.NEW_ITEMS:
            self.error_var.set("")
            self.status_var.set(TEXT["status_running"])
            self._prepend_items(event.items)
        elif event.event_type == MonitorEventType.STATUS:
            self.status_var.set(TEXT["status_running"])
            self.error_var.set("")
        elif event.event_type == MonitorEventType.ERROR:
            self.status_var.set(TEXT["status_retrying"])
            self.error_var.set(event.error or event.message)
        elif event.event_type == MonitorEventType.STOPPED:
            self.status_var.set(TEXT["status_stopped"])
            self._sync_button_states(False)

    def _replace_items(self, items: list[FlashNewsItem]) -> None:
        self.items.clear()
        self.items_by_uid.clear()
        self.selected_uid = None
        self._arrival_counter = 0

        self._ingest_items(items, allow_ai=False)
        self._sort_items()
        self._refresh_news_list(preserve_scroll=False)

    def _prepend_items(self, items: list[FlashNewsItem]) -> None:
        if not items:
            return

        preserve_scroll = bool(self.news_panel.cards) and not self.news_panel.is_near_top()
        new_items = self._ingest_items(items, allow_ai=True)
        if not new_items:
            return

        self._sort_items()
        new_item_uids = {item.uid for item in new_items}
        visible_new_items = [item for item in self._get_visible_items() if item.uid in new_item_uids]
        self._refresh_news_list(
            preserve_scroll=preserve_scroll,
            highlight_uids={item.uid for item in visible_new_items},
        )

        if visible_new_items:
            self._notify_new_items(visible_new_items)

    def _ingest_items(self, items: list[FlashNewsItem], allow_ai: bool) -> list[FlashNewsItem]:
        added_items: list[FlashNewsItem] = []
        for item in items:
            if item.uid in self.items_by_uid:
                continue

            self._arrival_counter += 1
            item.arrival_index = self._arrival_counter
            item.matched_keywords = find_keyword_hits(item.content, self.keywords)
            self.news_analyzer.apply_rules_to_item(item)
            self.items.append(item)
            self.items_by_uid[item.uid] = item
            added_items.append(item)
        return added_items

    def _sort_items(self) -> None:
        # 先去重入库，再对全部快讯按发布时间倒序重排。
        self.items.sort(key=lambda item: item.sort_key())
        self.items_by_uid = {item.uid: item for item in self.items}

    def _refresh_news_list(
        self,
        preserve_scroll: bool,
        highlight_uids: set[str] | None = None,
    ) -> None:
        visible_items = self._get_visible_items()
        render_items = self._get_render_items(visible_items)
        render_uids = {item.uid for item in render_items}
        if self.selected_uid and self.selected_uid not in render_uids:
            self.selected_uid = None

        self.news_panel.set_items(
            render_items,
            selected_uid=self.selected_uid,
            preserve_scroll=preserve_scroll,
        )

        for uid in highlight_uids or set():
            if uid in render_uids:
                self.news_panel.highlight(uid)

        self._update_count_label()

    def _notify_new_items(self, items: list[FlashNewsItem]) -> None:
        if self.sound_var.get():
            self._play_sound()
        if self.popup_var.get():
            for item in items[:3]:
                self.popup_manager.show(item, self._open_item_detail)
        self._send_items_to_dingtalk(items)

    def _play_sound(self) -> None:
        try:
            if winsound is not None:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                self.root.bell()
        except Exception:
            self.root.bell()

    def _send_items_to_dingtalk(self, items: list[FlashNewsItem]) -> None:
        config = self._get_saved_dingtalk_config()
        keyword_filter_enabled = self.keyword_filter_var.get()
        sent_any = False

        for item in items:
            queued, message = self.notifier.enqueue_flash(
                item=item,
                config=config,
                keyword_filter_enabled=keyword_filter_enabled,
            )
            if message == TEXT["webhook_empty"]:
                self.dingtalk_status_var.set(message)
                self.error_var.set(message)
            if queued:
                sent_any = True

        if sent_any:
            self._save_settings()

    def _poll_notifier_results(self) -> None:
        for result in self.notifier.poll_results():
            self._handle_notifier_result(result)

    def _handle_notifier_result(self, result: NotificationResult) -> None:
        self.dingtalk_status_var.set(result.message)
        if result.success:
            self.error_var.set("")
        else:
            self.error_var.set(result.message)

    def _get_saved_dingtalk_config(self) -> DingTalkPushConfig:
        return DingTalkPushConfig(
            webhook_url=self.settings.webhook_url,
            webhook_secret="",
            enabled=self.settings.webhook_enabled,
            timeout_seconds=8.0,
        )

    def _get_live_dingtalk_config(self) -> DingTalkPushConfig:
        return DingTalkPushConfig(
            webhook_url=self.webhook_url_var.get().strip(),
            webhook_secret="",
            enabled=self.webhook_enabled_var.get(),
            timeout_seconds=8.0,
        )

    def _save_dingtalk_settings(self) -> None:
        config = self._get_live_dingtalk_config()
        self.settings.webhook_url = config.webhook_url
        self.settings.webhook_secret = ""
        self.settings.webhook_enabled = config.enabled
        self._save_settings()

        if not config.webhook_url:
            self.dingtalk_status_var.set(TEXT["webhook_empty"])
        elif config.enabled:
            self.dingtalk_status_var.set(TEXT["webhook_saved"])
        else:
            self.dingtalk_status_var.set(TEXT["webhook_saved"])

    def _on_dingtalk_toggle(self) -> None:
        self.settings.webhook_enabled = self.webhook_enabled_var.get()
        self._save_settings()
        if self.webhook_enabled_var.get() and not self.webhook_url_var.get().strip():
            self.dingtalk_status_var.set(TEXT["webhook_enabled_without_url"])
            self.error_var.set(TEXT["webhook_empty"])
        elif not self.webhook_url_var.get().strip():
            self.dingtalk_status_var.set(TEXT["webhook_empty"])
        else:
            self.dingtalk_status_var.set(TEXT["webhook_saved"])

    def _send_test_webhook(self) -> None:
        config = self._get_live_dingtalk_config()
        queued, message = self.notifier.enqueue_test(config)
        if not queued:
            self.dingtalk_status_var.set(message)
            self.error_var.set(message)
            return

        self.dingtalk_status_var.set("\u6b63\u5728\u53d1\u9001\u6d4b\u8bd5\u6d88\u606f...")
        self.error_var.set("")

    def _on_interval_change(self, _event=None) -> None:
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            interval = 2.0
            self.interval_var.set("2")
        self.monitor.update_interval(interval)

    def _on_display_filter_change(self) -> None:
        preserve_scroll = bool(self.news_panel.cards) and not self.news_panel.is_near_top()
        self._refresh_news_list(preserve_scroll=preserve_scroll)

    def _on_keyword_filter_toggle(self) -> None:
        self._apply_keywords_from_input(normalize_text=False, persist=True)

    def _save_keywords(self) -> None:
        self._apply_keywords_from_input(normalize_text=True, persist=True)

    def _apply_keywords_from_input(self, normalize_text: bool, persist: bool) -> None:
        raw_text = self._get_keyword_input_text()
        normalized_keywords = normalize_keywords(raw_text)
        normalized_text = ", ".join(normalized_keywords)
        keywords_changed = normalized_keywords != self.keywords

        self.keywords = normalized_keywords
        if normalize_text:
            self._set_keyword_input_text(normalized_text)

        if keywords_changed:
            # 关键词过滤只影响显示与提醒，不影响内存里的历史快讯。
            self._refresh_keyword_matches()

        if persist:
            self._save_settings()

        preserve_scroll = bool(self.news_panel.cards) and not self.news_panel.is_near_top()
        self._refresh_news_list(preserve_scroll=preserve_scroll)

    def _refresh_keyword_matches(self) -> None:
        for item in self.items:
            item.matched_keywords = find_keyword_hits(item.content, self.keywords)

    def _save_settings(self) -> None:
        settings = AppSettings(
            keyword_text=", ".join(self.keywords),
            keyword_filter_enabled=self.keyword_filter_var.get(),
            webhook_url=self.webhook_url_var.get().strip(),
            webhook_secret="",
            webhook_enabled=self.webhook_enabled_var.get(),
            sent_message_keys=self.notifier.export_sent_keys(),
        )
        try:
            save_app_settings(settings)
            self.settings = settings
            self.logger.info(
                "Application settings saved. keywords=%s keyword_filter_enabled=%s webhook_enabled=%s sent_keys=%s",
                settings.keyword_text,
                settings.keyword_filter_enabled,
                settings.webhook_enabled,
                len(settings.sent_message_keys),
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Failed to save keyword settings.")
            self.error_var.set(f"{type(exc).__name__}: {exc}")

    def _load_settings_into_ui(self) -> None:
        self._set_keyword_input_text(self.settings.keyword_text)
        self.webhook_url_var.set(self.settings.webhook_url)
        self.webhook_enabled_var.set(self.settings.webhook_enabled)
        if not self.settings.webhook_url:
            self.dingtalk_status_var.set(TEXT["webhook_empty"])
        elif self.settings.webhook_enabled:
            self.dingtalk_status_var.set(TEXT["webhook_saved"])
        else:
            self.dingtalk_status_var.set(TEXT["webhook_saved"])

    def _on_select_item(self, item: FlashNewsItem) -> None:
        self.selected_uid = item.uid
        self.news_panel.set_selected(item.uid)

    def _open_item_detail(self, item: FlashNewsItem) -> None:
        if item.detail_url:
            webbrowser.open(item.detail_url)

    def _on_minimize(self, _event=None) -> None:
        if self.is_exiting:
            return
        if self.root.state() == "iconic":
            self.root.after(0, self.minimize_to_tray)

    def _get_visible_items(self) -> list[FlashNewsItem]:
        return [item for item in self.items if self._should_display(item)]

    @staticmethod
    def _get_render_items(items: list[FlashNewsItem]) -> list[FlashNewsItem]:
        # 只在界面中渲染最近一部分卡片，避免长时间运行后 Tk 控件过多导致窗口拖动卡顿。
        return items[:MAX_RENDERED_NEWS_CARDS]

    def _should_display(self, item: FlashNewsItem) -> bool:
        if self.important_only_var.get() and not item.is_important:
            return False
        if (
            self._is_keyword_filter_active()
            and not item.matched_keywords
        ):
            return False
        return True

    def _is_keyword_filter_active(self) -> bool:
        return self.keyword_filter_var.get() and bool(self.keywords)

    def _get_selected_item(self) -> FlashNewsItem | None:
        if not self.selected_uid:
            return None
        return self.items_by_uid.get(self.selected_uid)

    def _update_count_label(self) -> None:
        keyword_text = ", ".join(self.keywords) if self.keywords else TEXT["keyword_empty"]
        total_count = len(self.items)
        visible_items = self._get_visible_items()
        visible_count = len(visible_items)
        rendered_count = len(self._get_render_items(visible_items))
        self.count_var.set(
            f"\u5f53\u524d\u603b\u6570\uff1a{total_count} {TEXT['count_suffix']} | "
            f"\u5f53\u524d\u663e\u793a\uff1a{visible_count} {TEXT['count_suffix']} | "
            f"\u754c\u9762\u6e32\u67d3\uff1a{rendered_count} {TEXT['count_suffix']} | "
            f"\u5173\u952e\u8bcd\uff1a{keyword_text}"
        )

    def _sync_button_states(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _get_keyword_input_text(self) -> str:
        if self.keyword_input is None:
            return ""
        return self.keyword_input.get("1.0", "end").strip()

    def _set_keyword_input_text(self, value: str) -> None:
        if self.keyword_input is None:
            return
        self.keyword_input.delete("1.0", "end")
        if value:
            self.keyword_input.insert("1.0", value)

    def _sort_items(self) -> None:
        # Re-sort the full in-memory list by published time descending.
        self.items.sort(key=lambda item: item.sort_key())
        self.items_by_uid = {item.uid: item for item in self.items}

    def _apply_keywords_from_input(self, normalize_text: bool, persist: bool) -> None:
        raw_text = self._get_keyword_input_text()
        normalized_keywords = normalize_keywords(raw_text)
        normalized_text = ", ".join(normalized_keywords)
        keywords_changed = normalized_keywords != self.keywords

        self.keywords = normalized_keywords
        if normalize_text:
            self._set_keyword_input_text(normalized_text)

        if keywords_changed:
            # Keep unmatched items in memory so toggling the filter can show them again.
            self._refresh_keyword_matches()

        if persist:
            self._save_settings()

        preserve_scroll = bool(self.news_panel.cards) and not self.news_panel.is_near_top()
        self._refresh_news_list(preserve_scroll=preserve_scroll)

    @staticmethod
    def _get_item_time_text(item: FlashNewsItem) -> str:
        if item.published_at:
            return item.published_at.strftime("%Y-%m-%d %H:%M:%S")
        if item.selected_date:
            return f"{item.selected_date} {item.display_time}"
        return item.display_time

    def _format_item_for_text(self, item: FlashNewsItem) -> str:
        tags = []
        if item.is_vip:
            tags.append(TEXT["tag_vip"])
        if item.is_important:
            tags.append(TEXT["tag_important"])

        text = f"{''.join(tags)}[{self._get_item_time_text(item)}] {item.content.replace(chr(10), ' ')}"
        analysis_line = self._format_analysis_for_text(item)
        if analysis_line:
            text += f"\n{analysis_line}"
        if item.matched_keywords:
            text += f"\n{TEXT['keyword_hits']} {', '.join(item.matched_keywords)}"
        if item.detail_url:
            text += f"\n{TEXT['detail_link']} {item.detail_url}"
        return text

    @staticmethod
    def _format_analysis_for_text(item: FlashNewsItem) -> str:
        parts = []
        if item.analysis_level:
            parts.append(f"规则等级：{item.analysis_level}")
        if item.analysis_markets:
            parts.append("影响市场：" + "、".join(item.analysis_markets))
        if item.analysis_direction:
            parts.append("方向：" + item.analysis_direction)
        if item.analysis_rule_hits:
            parts.append("命中规则：" + "、".join(item.analysis_rule_hits))
        return " | ".join(parts)

    @staticmethod
    def _get_render_items(items: list[FlashNewsItem]) -> list[FlashNewsItem]:
        # 只在界面中渲染最近一部分卡片，避免长时间运行后 Tk 控件过多导致拖动卡顿。
        return items[:MAX_RENDERED_NEWS_CARDS]

    def _sort_items(self) -> None:
        # 内存里只保留最近一段历史，避免长时间运行后排序与内存占用持续增大。
        self.items.sort(key=lambda item: item.sort_key())
        if len(self.items) > MAX_STORED_NEWS_ITEMS:
            dropped_count = len(self.items) - MAX_STORED_NEWS_ITEMS
            dropped_uids = {item.uid for item in self.items[MAX_STORED_NEWS_ITEMS:]}
            self.items = self.items[:MAX_STORED_NEWS_ITEMS]
            if self.selected_uid in dropped_uids:
                self.selected_uid = None
            self.logger.info(
                "Trimmed in-memory news history. kept=%s dropped=%s",
                len(self.items),
                dropped_count,
            )
        self.items_by_uid = {item.uid: item for item in self.items}
