FROM python:3.11.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r worker/requirements.txt
COPY backend /app/backend
COPY worker /app/worker
RUN useradd --uid 10001 --create-home appuser && mkdir -p /data/runtime && chown -R appuser:appuser /app /data
USER appuser
CMD ["python", "/app/worker/run.py"]
