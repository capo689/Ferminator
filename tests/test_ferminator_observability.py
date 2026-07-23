from __future__ import annotations

import json
import logging

from ferminator.observability import JsonFormatter


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
