FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 wheels are bundled; keep image slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep Docker and Vercel on the same application entrypoint. The daily
# intelligence cron imports scripts/isd_intel.py at runtime, so scripts must be
# present in the image rather than only in the Vercel bundle.
COPY src ./src
COPY scripts ./scripts
COPY api ./api
COPY static ./static

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}"]
