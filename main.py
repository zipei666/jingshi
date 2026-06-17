from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from logger import setup_logging
from ui import Jin10FlashMonitorApp


def main() -> None:
    logger = setup_logging()
    root = tk.Tk()

    def report_callback_exception(exc, val, tb) -> None:
        logger.exception("Unhandled Tk exception.", exc_info=(exc, val, tb))
        messagebox.showerror("Application Error", f"{exc.__name__}: {val}")

    root.report_callback_exception = report_callback_exception
    logger.info("Application bootstrap finished.")
    Jin10FlashMonitorApp(root, logger)
    root.mainloop()


if __name__ == "__main__":
    main()
