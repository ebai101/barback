import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class BarbackLogger:
    """Centralized logging for Barback with structured output."""

    _instance: Optional["BarbackLogger"] = None
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
        self.logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
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
        file_handler.setLevel(logging.DEBUG)

        # Detailed formatter with timestamp, level, and context
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Optional: JSON structured log for machine parsing
        json_log = log_dir / "barback_structured.jsonl"
        json_handler = RotatingFileHandler(
            json_log, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(json_handler)

        self.logger.info("=" * 80)
        self.logger.info(f"Barback logging initialized - logs at: {log_dir}")
        self.logger.info("=" * 80)

    def get_logger(self):
        return self.logger

    def get_log_dir(self) -> Path:
        return Path.home() / ".barback" / "logs"


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs - enables easy parsing for reproducibility."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra fields if they exist
        if hasattr(record, "filepath"):
            log_data["filepath"] = str(record.filepath)
        if hasattr(record, "operation"):
            log_data["operation"] = record.operation
        if hasattr(record, "duration"):
            log_data["duration"] = record.duration

        return json.dumps(log_data)


# Singleton instance
_logger_instance = None


def get_logger() -> logging.Logger:
    """Get the Barback logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = BarbackLogger()
    return _logger_instance.get_logger()
