"""Logging configuration module."""

import logging
import sys
from app.core.config import settings


def setup_logging() -> logging.Logger:
    """Configures structured application logging."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger("zamp_app")
    logger.setLevel(log_level)
    return logger


logger = setup_logging()
