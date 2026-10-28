# Build context: repository root (see docker-compose.yml) so the ai_engine package is available.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY ai_engine /srv/ai_engine
COPY knowledge_engine /srv/knowledge_engine
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install -r /srv/backend/requirements.txt /srv/ai_engine /srv/knowledge_engine

COPY backend /srv/backend
WORKDIR /srv/backend

RUN useradd --system --uid 10001 --no-create-home dhanz \
    && mkdir -p /srv/data/uploads && chown -R dhanz /srv/backend /srv/data
USER dhanz

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"

# Apply migrations, then serve. --proxy-headers trusts X-Forwarded-For only from FORWARDED_ALLOW_IPS.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers ${WEB_CONCURRENCY:-2}"]
