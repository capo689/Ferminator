"""Bounded post-deploy and synthetic health verification."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable

import httpx


def _get_with_cold_start_retry(
    client: httpx.Client,
    url: str,
    *,
    attempts: int,
    retry_delay_seconds: float,
    sleep: Callable[[float], None],
) -> httpx.Response:
    """Wake a sleeping free-tier service without hiding a sustained outage."""
    last_error: httpx.TransportError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return client.get(url)
        except httpx.TransportError as exc:
            last_error = exc
            if attempt == attempts:
                break
            print(
                f"Wake-up attempt {attempt}/{attempts} failed with "
                f"{type(exc).__name__}; retrying in {retry_delay_seconds:g}s",
                file=sys.stderr,
            )
            sleep(retry_delay_seconds)
    assert last_error is not None
    raise last_error


def verify(
    base_url: str,
    *,
    password: str | None = None,
    attempts: int = 3,
    retry_delay_seconds: float = 10,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    base = base_url.rstrip("/")
    auth = ("alpha", password) if password else None
    passed = []
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        health = _get_with_cold_start_retry(
            client,
            f"{base}/healthz",
            attempts=attempts,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        health.raise_for_status()
        if health.json().get("status") != "ok":
            raise RuntimeError("Health endpoint returned a non-ok state")
        passed.append("healthz")

        ready = _get_with_cold_start_retry(
            client,
            f"{base}/readyz",
            attempts=attempts,
            retry_delay_seconds=retry_delay_seconds,
            sleep=sleep,
        )
        ready.raise_for_status()
        if ready.json().get("status") != "ready":
            raise RuntimeError("Readiness endpoint returned a non-ready state")
        passed.append("readyz")

        if password:
            dashboard = client.get(f"{base}/", auth=auth)
            dashboard.raise_for_status()
            if "Ferminator" not in dashboard.text:
                raise RuntimeError("Dashboard marker was absent")
            passed.append("dashboard")

            operations = client.get(f"{base}/ops", auth=auth)
            operations.raise_for_status()
            if operations.json().get("status") not in {"ok", "degraded"}:
                raise RuntimeError("Operations endpoint returned an invalid state")
            passed.append("ops")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--password")
    args = parser.parse_args()
    try:
        passed = verify(args.base_url, password=args.password)
    except Exception as exc:
        print(f"Deployment smoke failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Deployment smoke passed: {', '.join(passed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
