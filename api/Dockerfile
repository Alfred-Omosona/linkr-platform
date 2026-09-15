# syntax=docker/dockerfile:1

# ---------- Stage 1: BUILDER, installs the dependencies ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /venv

ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: RUNTIME, the image that ships ----------
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

ARG GIT_SHA=unknown
ARG VERSION=0.1.0
ENV LINKR_GIT_SHA=$GIT_SHA
ENV LINKR_VERSION=$VERSION

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

COPY app/ app/

RUN adduser --disabled-password --gecos "" --uid 10001 appuser

EXPOSE 8000

USER 10001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


