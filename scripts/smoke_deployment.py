"""Bounded post-deploy and synthetic health verification."""

from __future__ import annotations

import argparse
import sys

import httpx


def verify(base_url: str, *, password: str | None = None) -> list[str]:
    base = base_url.rstrip("/")
    auth = ("alpha", password) if password else None
    passed = []
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        health = client.get(f"{base}/healthz")
        health.raise_for_status()
        if health.json().get("status") != "ok":
            raise RuntimeError("Health endpoint returned a non-ok state")
        passed.append("healthz")

        ready = client.get(f"{base}/readyz")
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
