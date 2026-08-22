# Tag plus the official multi-platform manifest digest: a reviewed base update
# is a repository diff, never an invisible mutable-tag rebuild.
FROM python:3.14.7-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52

WORKDIR /app

# One universal lock drives Vercel, CI, Docker, and Render. The server extra
# adds Uvicorn without installing the offline pandas/plotting toolchain.
ARG UV_VERSION=0.11.33
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir "uv==${UV_VERSION}" \
    && uv sync --locked --no-dev --extra server

ENV PATH="/app/.venv/bin:${PATH}"

COPY src ./src
COPY static ./static

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
