FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# hatchling собирает пакет из src/, поэтому исходники нужны до установки.
# Ставятся только core-зависимости (без selenium/chromedriver — engine-режим в Docker не нужен).
COPY pyproject.toml alembic.ini ./
COPY src/ src/
RUN uv pip install --system --no-cache .

RUN useradd --create-home --uid 10001 app \
    && mkdir /data && chown app:app /data
USER app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2).status == 200 else 1)"

CMD ["lms-tool", "run"]
