# Tag plus the official multi-platform manifest digest: a reviewed base update
# is a repository diff, never an invisible mutable-tag rebuild.
FROM python:3.14.6-slim-bookworm@sha256:4c92ffcde4dd6f1ff72a24518f49fd4990b27134987dfa31a733badde66df9f8

WORKDIR /app

# One universal lock drives Vercel, CI, Docker, and Render. The server extra
# adds Uvicorn without installing the offline pandas/plotting toolchain.
ARG UV_VERSION=0.11.33
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir "uv==${UV_VERSION}" \
    && uv sync --locked --no-dev --extra server

ENV PATH="/app/.venv/bin:${PATH}"

# Keep Docker and Vercel on the same application entrypoint. The daily
# intelligence cron imports scripts/isd_intel.py at runtime, so scripts must be
# present in the image rather than only in the Vercel bundle.
COPY src ./src
COPY scripts ./scripts
COPY api ./api
COPY static ./static

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}"]
