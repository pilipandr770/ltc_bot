import os
import multiprocessing

# Server socket - используем переменную PORT от Render
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"
backlog = 2048

# Worker processes - ограничиваем для free tier
workers = 1  # Используем 1 worker для free tier Render
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 5

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "bnb_trading_bot"

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None
