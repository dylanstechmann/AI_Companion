# ---------------------------------------------------------------------------
# AI Companion – Backend Dockerfile
# Base: NVIDIA CUDA 11.8 + cuDNN 8 (Ubuntu 22.04)
# Provides: Python 3.11, ffmpeg, Node.js 20, pip dependencies
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- System packages + Python 3.11 (deadsnakes PPA) -----------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common curl gnupg2 ca-certificates && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev python3.11-distutils \
        ffmpeg && \
    # Make python3.11 the default python/python3
    update-alternatives --install /usr/bin/python  python  /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    # Install pip
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    # ---- Node.js 20 (nodesource) -------------------------------------------
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    # Clean up
    apt-get purge -y software-properties-common gnupg2 && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Python dependencies ---------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Playwright + Chromium (Phase 3: Browser Automation) -------------------
RUN playwright install chromium --with-deps

# ---- Application source ----------------------------------------------------
COPY . .

# ---- Sandbox directory (restricted execution area) -------------------------
RUN mkdir -p /app/sandbox && chmod 700 /app/sandbox

EXPOSE 8000

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
