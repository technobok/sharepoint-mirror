FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libldap2-dev \
    libsasl2-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install git+https://github.com/technobok/gatekeeper.git && \
    uv pip install --no-sources .

# Production image
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-common \
    libmagic1 \
    libsasl2-2 \
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

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:5001", "--workers", "2", "--preload"]
