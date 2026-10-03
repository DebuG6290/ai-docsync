FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCSYNC_EMBEDDING_CACHE=/tmp/docsync-embedding-cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY docsync ./docsync
COPY config ./config
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "docsync.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
