# MediEase API image — minimal version (M0-P3).
# Used by two compose services: `migrate` (alembic upgrade head) and `api`
# (gunicorn). M0-P5 hardens it into a multi-stage build.
#
# Build context: apps/api      docker build -t mediease-api:local apps/api

# Exact patch and Debian release, so a rebuild cannot silently change Python.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged runtime user (CLAUDE.md "Least privilege"). No home, no shell.
RUN groupadd --system app \
 && useradd --system --gid app --no-create-home --home-dir /app --shell /usr/sbin/nologin app

# Install the package (non-editable) with its pinned dependencies. psycopg's
# binary wheel bundles libpq, so no system packages are needed.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --prefer-binary . && rm -rf src build

# Migrations are baked into the image; nothing is bind-mounted at runtime.
COPY alembic.ini ./
COPY migrations ./migrations

USER app
EXPOSE 8000

# Configuration comes only from the environment. --preload imports the app in
# the gunicorn master before forking, so invalid settings (CFG_INVALID) stop the
# whole process with exit 1; without it each worker fails alone and the master
# restarts it forever. Safe because building the app opens no connections.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "mediease_api.wsgi:app"]
