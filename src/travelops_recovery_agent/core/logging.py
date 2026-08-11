"""Explicit application logging configuration."""

import json
import logging
from datetime import UTC, datetime

from travelops_recovery_agent.core.config import LogLevel
from travelops_recovery_agent.core.context import current_request_id

LOGGER_NAME = "travelops_recovery_agent"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = current_request_id.get()
        if request_id is not None:
            payload["request_id"] = request_id

        for field in ("http_method", "http_path", "http_status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: LogLevel) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    application_logger = logging.getLogger(LOGGER_NAME)
    application_logger.handlers.clear()
    application_logger.addHandler(handler)
    application_logger.setLevel(log_level.value)
    application_logger.propagate = False
