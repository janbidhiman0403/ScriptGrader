"""Structured logging configuration, applied once at app startup."""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if configure_logging() runs more than once
    # (e.g. under a reloader).
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    # Quiet noisy third-party loggers unless something's actually wrong.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
