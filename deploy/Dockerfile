# syntax=docker/dockerfile:1
# Image layanan eutopos (FastAPI + hloc). Dibangun dari akar repo: lihat deploy/compose.yaml.
# Bawaan PyTorch CPU (klaim latensi diukur tanpa GPU). Varian GPU: deploy/compose.gpu.yaml.

ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

# ---- builder: pasang semua dependensi ke /opt/venv ----
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Jaringan lab lambat: roda CUDA ratusan MB per berkas (torch cu130 total ±3 GB). Batas baca 30 s
# bawaan uv dan puluhan unduhan paralel membuat build gagal timeout (PC lab, 2026-10-01).
ENV UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=4
RUN uv venv /opt/venv

# Setiap "uv pip install" memakai cache mount: berkas yang sudah selesai diunduh tidak diunduh ulang
# kalau build gagal di tengah (pola dokumentasi uv untuk Docker, butuh UV_LINK_MODE=copy).

# 1. PyTorch paling jarang berubah dan paling besar, jadi lapisan pertama.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv torch==2.14.0 torchvision==0.29.0 --index-url ${TORCH_INDEX}

# 2. hloc dipin ke commit yang sama dengan spike (docs/spike-plan.md).
ARG HLOC_COMMIT=c13273bd0ecc2917a35910fd843712a1c6243193
RUN --mount=type=cache,target=/root/.cache/uv \
    git clone https://github.com/cvg/Hierarchical-Localization.git /tmp/hloc \
 && git -C /tmp/hloc checkout ${HLOC_COMMIT} \
 && uv pip install --python /opt/venv /tmp/hloc \
 && rm -rf /tmp/hloc

# 3. Dependensi layanan, versinya dari uv.lock.
COPY pyproject.toml uv.lock /src/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /src \
 && uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
 && uv pip install --python /opt/venv -r /tmp/requirements.txt

# ---- web: dashboard Next.js static export ----
FROM node:24.21.0-bookworm-slim AS web
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY web/ ./
RUN npm run build

# ---- runtime: hanya venv, kode layanan, dan pustaka sistem yang dibutuhkan OpenCV ----
FROM ${PYTHON_IMAGE} AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 eutopos \
 && mkdir -p /cache && chown eutopos:eutopos /cache
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    TORCH_HOME=/cache/torch \
    HF_HOME=/cache/huggingface
WORKDIR /app
COPY --chown=eutopos:eutopos server ./server
COPY --chown=eutopos:eutopos spike ./spike
COPY --from=web --chown=eutopos:eutopos /web/out ./web/out
USER eutopos
EXPOSE 8000
# Memuat model dan peta butuh waktu, jadi start-period panjang.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"
CMD ["sh", "-c", "alembic -c server/alembic.ini upgrade head && uvicorn server.app:app --host 0.0.0.0 --port 8000"]

# ---- test: unit test di dalam image yang dikirim (CI: docs/ci-cd.md) ----
# Bukan image layanan: compose.yaml memilih target runtime. Build tahap ini gagal kalau ada tes yang
# gagal: docker build -f deploy/Dockerfile --target test .
FROM runtime AS test
USER root
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock /src/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /src \
 && uv export --frozen --only-group dev --no-emit-project --no-hashes -o /tmp/dev.txt \
 && uv pip install --python /opt/venv -r /tmp/dev.txt
COPY --chown=eutopos:eutopos pyproject.toml ./
COPY --chown=eutopos:eutopos tests ./tests
USER eutopos
RUN pytest -q -p no:cacheprovider
