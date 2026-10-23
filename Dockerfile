FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY data data

ENV PYTHONPATH=/app/backend

CMD ["sh", "-c", "if ! ls /app/tmp/osm/*.graphml >/dev/null 2>&1; then cd /app/backend && python -m app.graph_loader; fi; cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]