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
    total_deadline_seconds = 45.0

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
        return self.request_json("GET", url)

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        return self.request_json("POST", url, json=payload)

    def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        deadline = time.monotonic() + self.total_deadline_seconds
        last_code = "provider_request_failed"
        for attempt in range(self.max_attempts):
            if time.monotonic() >= deadline:
                last_code = "provider_deadline_exceeded"
                break
            try:
                response = self.client.request(method, url, **kwargs)
                retryable = response.status_code == 429 or response.status_code >= 500
                if retryable and attempt < self.max_attempts - 1:
                    try:
                        retry_after = float(response.headers.get("Retry-After", "1"))
                    except ValueError:
                        retry_after = 1.0
                    remaining = max(0.0, deadline - time.monotonic())
                    time.sleep(min(retry_after, 10.0, remaining))
                    continue
                response.raise_for_status()
                if len(response.content) > self.max_response_bytes:
                    raise AdapterError("response_too_large", "Provider response exceeded limit")
                content_type = response.headers.get("content-type", "").casefold()
                if "json" not in content_type:
                    raise AdapterError(
                        "unexpected_content_type",
                        "Provider did not return JSON",
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise AdapterError(
                        "invalid_json",
                        "Provider returned malformed JSON",
                    ) from exc
            except AdapterError:
                raise
            except httpx.TimeoutException:
                last_code = "provider_timeout"
            except httpx.HTTPStatusError as exc:
                last_code = f"provider_http_{exc.response.status_code}"
                if exc.response.status_code < 500 and exc.response.status_code != 429:
                    break
            except httpx.HTTPError:
                last_code = "provider_transport_error"
            if attempt < self.max_attempts - 1:
                remaining = max(0.0, deadline - time.monotonic())
                time.sleep(min((2**attempt) + random.uniform(0, 0.25), remaining))
        raise AdapterError(last_code, "Provider request failed safely")

    def get_text(self, url: str) -> str:
        """Fetch bounded HTML used by ATS pages with embedded public JSON."""
        try:
            response = self.client.get(url, headers={"Accept": "text/html"})
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AdapterError("provider_timeout", "Provider request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                f"provider_http_{exc.response.status_code}",
                "Provider request failed safely",
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(
                "provider_transport_error",
                "Provider request failed safely",
            ) from exc
        if len(response.content) > self.max_response_bytes:
            raise AdapterError("response_too_large", "Provider response exceeded limit")
        content_type = response.headers.get("content-type", "").casefold()
        if "html" not in content_type:
            raise AdapterError("unexpected_content_type", "Provider did not return HTML")
        return response.text

    @abstractmethod
    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        raise NotImplementedError
