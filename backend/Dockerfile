# Build from the repository root:  docker build -f backend/Dockerfile -t kinema-api .
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app

# dependencies first (cached unless they change); constraints.txt pins the exact versions the tests ran on
COPY backend/requirements.txt backend/constraints.txt backend/
RUN pip install -r backend/requirements.txt -c backend/constraints.txt

COPY backend backend
COPY reports reports

# MovieLens is downloaded at build time (its licence does not allow re-hosting the files) and validated
RUN cd backend && python -m scripts.setup_data

RUN useradd --create-home --uid 10001 app && mkdir -p /app/data/cache && chown -R app /app/data
USER app

WORKDIR /app/backend
EXPOSE 10000
# Render injects $PORT. --proxy-headers: the visitor's address comes from the host's proxy (used by the rate limiter)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
