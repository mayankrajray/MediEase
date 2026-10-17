# MediEase API image (M0-P5).
# One image, two compose services: `migrate` (alembic upgrade head) and `api` (gunicorn).
#
# Build context: apps/api      docker build -t mediease-api:local apps/api
#
# Base pinned by tag and digest: the tag says what it is, the digest guarantees a
# rebuild cannot silently pull a changed image. Dependabot (docker) proposes updates.
ARG PYTHON_IMAGE=python:3.12.15-slim-trixie@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256

# --- build: install the package and its pinned dependencies into a venv --------
FROM ${PYTHON_IMAGE} AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
# Non-editable install: the package is copied into the venv's site-packages.
# psycopg's binary wheel bundles libpq, so no system packages or compiler.
RUN pip install --prefer-binary . \
 && pip uninstall --yes pip

# --- runtime: the venv, the migrations and nothing else ------------------------
FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="mediease-api" \
      org.opencontainers.image.description="MediEase API and migrations" \
      org.opencontainers.image.source="https://github.com/mayankrajray/MediEase"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    XDG_CACHE_HOME=/tmp
# XDG_CACHE_HOME: fontconfig's cache goes to the /tmp tmpfs (the root filesystem is read-only).

# Debian security fixes published after the pinned base image was built. The
# base stays pinned; this only upgrades packages it already contains, and the CI
# image scan fails if a fixed HIGH/CRITICAL vulnerability is still present.
#
# M4-P4: Pango, HarfBuzz and fontconfig for the in-house PDF renderer (WeasyPrint >= 70 needs
# Pango >= 1.44; trixie ships 1.56). Fonts are vendored in the package, not installed here.
RUN apt-get update \
 && apt-get upgrade --yes --no-install-recommends \
 && apt-get install --yes --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig \
 && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user (CLAUDE.md "Least privilege"). No home, no shell.
# The base image's pip is removed: nothing installs packages at runtime.
RUN groupadd --system app \
 && useradd --system --gid app --no-create-home --home-dir /app --shell /usr/sbin/nologin app \
 && python -m pip uninstall --yes --root-user-action ignore pip \
 && mkdir -p /var/lib/mediease/blobs \
 && chown app:app /var/lib/mediease/blobs
# Prescription PDFs (M4-P4, BLOB_STORAGE=local). Compose mounts the named volume blobs here;
# a new volume copies this directory's owner, so the app user can write to it.

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
# Migrations are baked into the image; nothing is bind-mounted at runtime.
COPY alembic.ini ./
COPY migrations ./migrations

USER app
EXPOSE 8000

# Configuration comes only from the environment.
# --preload: the app is built in the master before forking, so invalid settings
#   (CFG_INVALID) stop the container with exit 1 instead of a worker restart loop.
#   Safe because building the app opens no connections.
# --worker-tmp-dir /dev/shm: worker heartbeats go to shared memory, so the
#   container can run with a read-only root filesystem (compose read_only).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "--worker-tmp-dir", "/dev/shm", "mediease_api.wsgi:app"]
