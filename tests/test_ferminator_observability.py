from __future__ import annotations

import json
import logging

from ferminator.observability import JsonFormatter, safe_request_id


def test_json_formatter_emits_operational_fields() -> None:
    record = logging.LogRecord(
        name="ferminator.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_complete",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc"
    record.status_code = 200

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "request_complete"
    assert payload["request_id"] == "abc"
    assert payload["status_code"] == 200


def test_request_id_rejects_log_injection() -> None:
    assert safe_request_id("upstream-123") == "upstream-123"
    generated = safe_request_id("bad\nforged-log")
    assert generated != "bad\nforged-log"
    assert len(generated) == 32
