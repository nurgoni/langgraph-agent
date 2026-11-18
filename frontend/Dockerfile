# syntax=docker/dockerfile:1
# Image `web` (F32): build statis Vite dengan Node 24 + pnpm (corepack), lalu disajikan nginx
# non-root yang juga mem-proxy /api ke service. Build context: folder frontend/.
#   docker build -t agent-service-web frontend

ARG NODE_VERSION=24

FROM node:${NODE_VERSION}-alpine AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app
RUN corepack enable
# Dependency dulu, supaya layer ini tetap ter-cache selama lockfile tidak berubah. Store pnpm di
# cache mount BuildKit: saat lockfile berubah, hanya paket baru yang diunduh (registry npm lambat).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store
COPY . .
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS web
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://agent-service:8080
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
