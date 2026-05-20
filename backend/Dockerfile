FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
# Устанавливаем только core-зависимости (без selenium/chromedriver — engine-режим в Docker не нужен)
RUN uv pip install --system --no-cache .

COPY src/ src/
COPY alembic.ini .

EXPOSE 8765

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8765"]
