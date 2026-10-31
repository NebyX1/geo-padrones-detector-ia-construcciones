import os

bind = "0.0.0.0:5000"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = 4
worker_class = "gthread"
timeout = 60
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
preload_app = False
accesslog = None  # Request URLs may contain sensitive search terms.
errorlog = "-"
loglevel = "info"
