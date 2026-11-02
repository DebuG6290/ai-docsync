FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCSYNC_EMBEDDING_CACHE=/tmp/docsync-embedding-cache \
    DOCSYNC_HOSTED=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt requirements.lock LICENSE README.md ./
COPY docsync ./docsync
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini streamlit_app.py demo_app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 docsync
USER docsync

EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.address", "0.0.0.0"]
