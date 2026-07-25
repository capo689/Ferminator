"""Structured, redacted application logging."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def safe_request_id(value: str | None) -> str:
    """Accept useful upstream correlation IDs without allowing log injection."""
    if value and _SAFE_REQUEST_ID.fullmatch(value):
        return value
    return __import__("uuid").uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "dependency",
            "event",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
