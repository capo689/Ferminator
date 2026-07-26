import httpx

from scripts.smoke_deployment import verify


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/healthz"):
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))
        if url.endswith("/readyz"):
            return httpx.Response(
                200,
                json={"status": "ready"},
                request=httpx.Request("GET", url),
            )
        if url.endswith("/ops"):
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            text="<title>Ferminator</title>",
            request=httpx.Request("GET", url),
        )


class ColdStartClient(FakeClient):
    health_attempts = 0

    def get(self, url, **kwargs):
        if url.endswith("/healthz"):
            self.health_attempts += 1
            if self.health_attempts < 3:
                raise httpx.ReadTimeout(
                    "sleeping service",
                    request=httpx.Request("GET", url),
                )
        return super().get(url, **kwargs)


def test_deployment_smoke_checks_authenticated_operational_path(monkeypatch):
    monkeypatch.setattr(httpx, "Client", FakeClient)

    assert verify("https://example.com/", password="secret") == [
        "healthz",
        "readyz",
        "dashboard",
        "ops",
    ]


def test_deployment_smoke_tolerates_bounded_cold_start(monkeypatch):
    monkeypatch.setattr(httpx, "Client", ColdStartClient)
    delays = []

    assert verify(
        "https://example.com/",
        attempts=4,
        retry_delay_seconds=10,
        sleep=delays.append,
    ) == ["healthz", "readyz"]
    assert delays == [10, 10]


def test_deployment_smoke_still_fails_after_retry_budget(monkeypatch):
    class SleepingClient(FakeClient):
        def get(self, url, **kwargs):
            raise httpx.ReadTimeout(
                "still sleeping",
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "Client", SleepingClient)
    delays = []

    try:
        verify(
            "https://example.com/",
            attempts=3,
            retry_delay_seconds=5,
            sleep=delays.append,
        )
    except httpx.ReadTimeout:
        pass
    else:
        raise AssertionError("Expected retry exhaustion to preserve the outage")

    assert delays == [5, 5]
