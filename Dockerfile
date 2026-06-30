# ── Build stage ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies in a separate layer for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ────────────────────────────────────────────────────────
FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Environment variables for Python behavior
# Actual config (BOT_TOKEN, TIMEZONE, etc.) comes from .env at runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Volume for persistent SQLite data
VOLUME ["/app/data"]

# Health check: verify the Python process is running
# Telegram bots don't expose HTTP ports, so we check the PID file written by bot.py
# The start-period gives the bot time to initialize and write the PID file
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os; f=open('/app/data/.pid'); pid=int(f.read().strip()); f.close(); os.kill(pid, 0)" || exit 1

# Signal handling: PID 1 receives signals properly
STOPSIGNAL SIGTERM

ENTRYPOINT ["python", "bot.py"]
