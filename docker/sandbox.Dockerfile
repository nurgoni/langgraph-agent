# syntax=docker/dockerfile:1
# Image eksekusi kode model (F37, FR-49). Satu container sekali pakai per eksekusi, dijalankan
# `sandbox-runner` tanpa jaringan, rootfs read-only, dan user non-root. Library analisa data hanya
# ada di image ini, bukan di image service.
#   docker build -f docker/sandbox.Dockerfile -t agent-service-sandbox:local docker

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

# Versi dipin supaya hasil analisa bisa diulang; dirilis sebelum batas `exclude-newer` uv.
RUN pip install --no-cache-dir \
        numpy==2.3.4 \
        pandas==2.3.3 \
        matplotlib==3.10.7

# UID sama dengan SANDBOX_UID di sandbox/docker.py. `/workspace` milik user ini, jadi volume anonim
# yang dibuat runner mewarisi pemiliknya.
RUN useradd --create-home --uid 10001 sandbox \
    && mkdir /workspace \
    && chown 10001:10001 /workspace
USER 10001
WORKDIR /workspace
# Rootfs read-only: cache matplotlib dan HOME diarahkan ke tmpfs /tmp.
ENV HOME=/tmp \
    MPLCONFIGDIR=/tmp \
    MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
CMD ["python", "--version"]
