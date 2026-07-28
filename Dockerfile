FROM python:3.12-slim

WORKDIR /app

# Install deps
COPY campaign-os/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app code
COPY campaign-os/ /app/campaign-os/
COPY data/ /app/data/

# Persistent data dir (Railway volume mounts at /data/campaign-os)
RUN mkdir -p /data/campaign-os
ENV DATA_DIR=/data/campaign-os
ENV PORT=8000

EXPOSE 8000

WORKDIR /app/campaign-os
CMD ["python", "app.py"]