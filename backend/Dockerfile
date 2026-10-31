FROM python:3.11.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLASK_APP=wsgi:app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY backend /app/backend
COPY scripts /app/scripts
COPY backend/entrypoint.sh /app/entrypoint.sh
ENV PYTHONPATH=/app/backend
RUN mkdir -p /data/runtime /data/models && chown -R appuser:appuser /app /data && chmod +x /app/entrypoint.sh
USER appuser
WORKDIR /app/backend
EXPOSE 5000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
