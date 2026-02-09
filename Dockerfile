FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install .

# Production image
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash sharepoint-mirror

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY --chown=sharepoint-mirror:sharepoint-mirror src/ ./src/
COPY --chown=sharepoint-mirror:sharepoint-mirror database/ ./database/
COPY --chown=sharepoint-mirror:sharepoint-mirror wsgi.py ./
COPY --chown=sharepoint-mirror:sharepoint-mirror pyproject.toml ./

RUN mkdir -p /app/instance && chown sharepoint-mirror:sharepoint-mirror /app/instance

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER sharepoint-mirror

EXPOSE 5001

CMD ["python", "wsgi.py"]
