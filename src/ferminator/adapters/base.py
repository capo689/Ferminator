"""Base HTTP behavior shared by public ATS adapters."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ferminator.domain import ATSProvider, BoardRef, NormalizedJob

USER_AGENT = "Ferminator/0.2 (+https://github.com/capo689/Ferminator)"


class AdapterError(RuntimeError):
    """Safe provider error that can be logged without response payloads."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BaseAdapter(ABC):
    provider: ATSProvider
    timeout_seconds = 25.0
    max_attempts = 3
    max_response_bytes = 25 * 1024 * 1024

    def __init__(self, client: httpx.Client | None = None):
        self._owned_client = client is None
        self.client = client or httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def __enter__(self) -> BaseAdapter:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get_json(self, url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.get(url)
                if response.status_code == 429 and attempt < self.max_attempts - 1:
                    retry_after = min(float(response.headers.get("Retry-After", "1")), 10)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                if len(response.content) > self.max_response_bytes:
                    raise AdapterError("response_too_large", "Provider response exceeded limit")
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_attempts - 1:
                    time.sleep((2**attempt) + random.uniform(0, 0.25))
        raise AdapterError("provider_request_failed", str(last_error)) from last_error

    @abstractmethod
    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        raise NotImplementedError

