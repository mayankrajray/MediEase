# MediEase web image (M0-P5): Next.js standalone server.
#
# Build context: apps/web
#   docker build --build-arg API_INTERNAL_URL=http://api:8000 -t mediease-web:local apps/web
#
# Base pinned by tag (same Node as .nvmrc) and digest; Dependabot proposes updates.
ARG NODE_IMAGE=node:24.21.0-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe

# --- deps: exact versions from the lockfile ------------------------------------
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit

# --- build ---------------------------------------------------------------------
FROM ${NODE_IMAGE} AS build
WORKDIR /app
# `next build` writes the /api, /health and /ready rewrite destinations into the
# output, so the API address is fixed at build time (NEXT_STEPS_PLAN.md Task 5).
# The default matches the compose service name.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# --- runtime: the standalone server and its static assets only -----------------
FROM ${NODE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="mediease-web" \
      org.opencontainers.image.description="MediEase web app (Next.js)" \
      org.opencontainers.image.source="https://github.com/mayankrajray/MediEase"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Debian security fixes published after the pinned base image was built (the
# base stays pinned; only packages it already contains are upgraded, and the CI
# image scan fails on any fixed HIGH/CRITICAL vulnerability still present).
# Package managers are not needed to run the server; removing them shrinks the
# attack surface of the running container.
RUN apt-get update \
 && apt-get upgrade --yes --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
           /opt/yarn-* /usr/local/bin/yarn /usr/local/bin/yarnpkg

WORKDIR /app
# Files stay owned by root, so the unprivileged runtime user cannot modify them.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

# The node image's built-in unprivileged user (uid 1000).
USER node
EXPOSE 3000

CMD ["node", "server.js"]
