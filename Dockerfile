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

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY src/ ./src/
COPY database/ ./database/
COPY wsgi.py ./
COPY pyproject.toml ./

RUN mkdir -p /app/instance

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5001

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:5001", "--workers", "2", "--preload", "--timeout", "600"]
