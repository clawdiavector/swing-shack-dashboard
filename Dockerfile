FROM python:3.12-slim

WORKDIR /app

# Install deps first (better layer caching)
COPY campaign-os/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app code (includes data/ inside campaign-os/)
COPY campaign-os/ /app/campaign-os/

# Persistent data dir — Fly volume mounts here at runtime
# (mkdir only needed for local Docker; Fly will mount over it)
RUN mkdir -p /data/campaign-os
ENV DATA_DIR=/data/campaign-os
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

WORKDIR /app/campaign-os
CMD ["python", "app.py"]
