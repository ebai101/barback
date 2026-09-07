import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs


class BarbackLogger:
    """Centralized logging for Barback with structured output."""

    _instance: "BarbackLogger | None" = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.logger = logging.getLogger("barback")

        if self.logger.handlers:
            return

        # Log directory in user's home
        log_dir = self.get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file with rotation (10MB max, keep 5 backups)
        main_log = log_dir / "barback.log"
        file_handler = RotatingFileHandler(
            main_log,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )

        # Detailed formatter with timestamp, level, and context
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        self.logger.info(f"Barback logging initialized - logs at: {log_dir}")

    def get_logger(self):
        return self.logger

    def get_log_dir(self) -> Path:
        log_dir = Path(platformdirs.user_log_dir("barback"))
        return log_dir


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs - enables easy parsing for reproducibility."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=datetime.now().astimezone().tzinfo
            ).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "filepath"):
            log_data["filepath"] = str(record.filepath)
        if hasattr(record, "operation"):
            log_data["operation"] = str(record.operation)
        if hasattr(record, "duration"):
            log_data["duration"] = str(record.duration)

        return json.dumps(log_data)


_logger_instance = None


def get_logger() -> logging.Logger:
    """Get the Barback logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = BarbackLogger()
    return _logger_instance.get_logger()
