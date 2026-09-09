FROM python:3.12-slim-bookworm

# git is required by Railway build context + some app-level metadata capture.
# Without it: 'Git clone failed (non-fatal): [Errno 2] No such file or directory: git'
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# No .pyc files inside the image — a deleted .py must fail at import, not
# silently resolve to stale bytecode (the feedback_loop orphan-.pyc class).
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install deps first (better layer caching)
COPY campaign-os/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app code
COPY campaign-os/ /app/campaign-os/
# Copy data dir (brands.json, voice_bible.json, etc. live at repo root in data/)
COPY data/ /app/data/
# Copy repo-root assets/ (campaign visuals, etc. — referenced by /assets/ route)
COPY assets/ /app/assets/
# Copy scripts/ (fetchers: fetch_ig_business.py, fetch_ubersuggest.py, etc.
# — referenced by the in-app /refresh endpoints)
COPY scripts/ /app/scripts/

# Module-gap visibility (Tier: deploy determinism, 2026-09-09).
# WARNING ONLY — must not fail the build while the 36 _lib modules are
# still absent from the remote. Flip --warn-only off once they land.
RUN python /app/scripts/check_lib_modules.py --warn-only \
      --source /app/campaign-os/app.py \
      --lib-dir /app/campaign-os/_lib

# Persistent data dir — Fly volume mounts here at runtime
# (mkdir only needed for local Docker; Fly will mount over it)
RUN mkdir -p /data/campaign-os
ENV DATA_DIR=/data/campaign-os

EXPOSE 8080

WORKDIR /app/campaign-os
CMD ["python", "app.py"]
