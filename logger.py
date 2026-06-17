from __future__ import annotations

import logging
import os
import shutil
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from models import APP_NAME


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    fallback_dir = get_runtime_root() / "data"

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data) / APP_NAME
        else:
            base_dir = fallback_dir
    else:
        base_dir = fallback_dir

    try:
        return _ensure_directory(base_dir)
    except OSError:
        return _ensure_directory(fallback_dir)


def get_logs_dir() -> Path:
    logs_dir = get_data_dir() / "logs"
    return _ensure_directory(logs_dir)


def get_exports_dir() -> Path:
    exports_dir = get_data_dir() / "exports"
    return _ensure_directory(exports_dir)


def get_log_file_path() -> Path:
    return get_logs_dir() / "jin10_flash_monitor.log"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        get_log_file_path(),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False

    logger.info("Logging is ready.")
    logger.info("Runtime root: %s", get_runtime_root())
    logger.info("Data directory: %s", get_data_dir())
    return logger


def copy_log_to(target_path: str | Path) -> Path:
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_log_file_path(), target)
    return target
