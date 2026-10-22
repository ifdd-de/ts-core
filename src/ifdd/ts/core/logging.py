"""Loggers configured from the settings (level and format)."""

import logging
import sys
from typing import Optional

from .config import get_settings


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a logger that writes to stdout, configured once per name."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    settings = get_settings()
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper())
    logger.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    logger.addHandler(handler)
    return logger
