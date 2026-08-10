"""
Gunicorn configuration for production.

Uvicorn's own `--reload` dev server (used locally) is single-process and
not meant to take real traffic. Gunicorn manages multiple uvicorn worker
processes instead — if one worker crashes or hangs on a slow model call,
the others keep serving.
"""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Vision-model grading requests are I/O-bound (waiting on the Anthropic
# API) rather than CPU-bound, so a modest worker count handles concurrency
# fine without needing one worker per core. Override via WEB_CONCURRENCY
# if you need to tune this for your actual traffic.
workers = int(os.environ.get("WEB_CONCURRENCY", min(multiprocessing.cpu_count(), 4)))

worker_class = "uvicorn.workers.UvicornWorker"

# Grading involves two sequential model calls (draft + verify) that can
# each take tens of seconds on slow handwriting — give workers real room
# rather than gunicorn's 30s default killing an in-progress grade.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30

max_requests = 1000  # recycle workers periodically to bound memory growth
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
