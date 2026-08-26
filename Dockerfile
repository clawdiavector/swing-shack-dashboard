FROM python:3.12-slim

WORKDIR /app

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

# Persistent data dir — Fly volume mounts here at runtime
# (mkdir only needed for local Docker; Fly will mount over it)
RUN mkdir -p /data/campaign-os
ENV DATA_DIR=/data/campaign-os
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

WORKDIR /app/campaign-os
CMD ["python", "app.py"]
