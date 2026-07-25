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


def test_deployment_smoke_checks_authenticated_operational_path(monkeypatch):
    monkeypatch.setattr(httpx, "Client", FakeClient)

    assert verify("https://example.com/", password="secret") == [
        "healthz",
        "readyz",
        "dashboard",
        "ops",
    ]
