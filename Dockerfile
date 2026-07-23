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
RUN pip install --prefix=/install --require-hashes -r requirements.lock

# Now install the package itself without re-resolving deps (they're locked).
COPY pyproject.toml README.md ./
COPY src/ src/
COPY profiles/ profiles/
COPY config/ config/
RUN pip install --prefix=/install --no-deps .

FROM python:3.13-slim@sha256:a0779d7c12fc20be6ec6b4ddc901a4fd7657b8a6bc9def9d3fde89ed5efe0a3d

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /build/profiles /app/profiles
COPY --from=builder /build/config /app/config

# Pin the runtime UID and keep the image read-only compatible.
RUN useradd --create-home --uid 1000 --shell /bin/bash ferminator
USER ferminator

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/healthz', timeout=3)"

CMD ["uvicorn", "ferminator.web:app", "--host", "0.0.0.0", "--port", "10000"]
