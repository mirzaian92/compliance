FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY README.md .

# Non-root user for production runs
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default runs the full pipeline (fetch -> classify -> digest -> email).
# Configure via environment variables.
CMD ["python", "-m", "app.main", "run-daily"]
