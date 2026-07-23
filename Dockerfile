# syntax=docker/dockerfile:1.7

# Both stages use the same pinned base image. Dependabot keeps the digest
# fresh weekly via .github/dependabot.yml.
FROM python:3.13-slim@sha256:a0779d7c12fc20be6ec6b4ddc901a4fd7657b8a6bc9def9d3fde89ed5efe0a3d AS builder

WORKDIR /build

# Install all transitive deps from the hash-pinned lockfile FIRST. This layer
# caches independently of source changes and is byte-reproducible across
# rebuilds. --require-hashes refuses any package whose sha256 isn't in the
# lockfile. Regenerate with:
#   uv pip compile pyproject.toml -o requirements.lock --generate-hashes
COPY requirements.lock .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --require-hashes -r requirements.lock

# Now install the package itself without re-resolving deps (they're locked).
COPY pyproject.toml README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install --no-deps .

FROM python:3.13-slim@sha256:a0779d7c12fc20be6ec6b4ddc901a4fd7657b8a6bc9def9d3fde89ed5efe0a3d

WORKDIR /app
COPY --from=builder /install /usr/local

# Pin UID so bind-mounts (if ever used) match host ownership predictably.
RUN useradd --create-home --uid 1000 --shell /bin/bash tracker \
    && mkdir -p /data && chown tracker:tracker /data
USER tracker

VOLUME /data

ENV TRACKER_DB=/data/tracker.db \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# HEALTHCHECK is intentionally NOT defined here. It only makes sense for
# the long-running web service; CLI runs (fetch, dashboard, summary, etc.)
# would fail it. Healthcheck lives in docker-compose.yml on the web service.

ENTRYPOINT ["tracker"]
CMD ["fetch"]
