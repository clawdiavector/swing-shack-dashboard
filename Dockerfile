FROM python:3.12-slim

# git is required by Railway build context + some app-level metadata capture.
# Without it: 'Git clone failed (non-fatal): [Errno 2] No such file or directory: git'
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (better layer caching)
COPY campaign-os/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app code
COPY campaign-os/ /app/campaign-os/
# Copy data dir (brands.json, voice_bible.json, etc. live at repo root in data/)
COPY data/ /app/data/

# Persistent data dir — Fly volume mounts here at runtime
# (mkdir only needed for local Docker; Fly will mount over it)
RUN mkdir -p /data/campaign-os
ENV DATA_DIR=/data/campaign-os
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

WORKDIR /app/campaign-os
CMD ["python", "app.py"]
