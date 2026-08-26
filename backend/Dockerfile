# ── Build stage ──────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (Docker layer caching — faster rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create data directory for SQLite volume
RUN mkdir -p /app/data

# Environment defaults
ENV DB_PATH=/app/data/aurora.db
ENV MLFLOW_TRACKING_URI=http://mlflow:5001

EXPOSE 8000

# Health check — Docker uses this to know if the app is alive
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with uvicorn (production ASGI server)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
