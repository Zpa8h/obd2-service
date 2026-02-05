# OBD2 Data Pipeline Service - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not create virtual environments
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --only main

# Copy application code
COPY app/ ./app/
COPY static/ ./static/
COPY sql/ ./sql/

# Create data directories
RUN mkdir -p /data/csv_uploads /data/csv_uploads/processed

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
