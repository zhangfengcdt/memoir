# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements files first for better Docker layer caching
COPY pyproject.toml README.md ./

# Create a minimal src structure for editable install
RUN mkdir -p src/memoir && touch src/memoir/__init__.py

# Install dependencies first (this layer will be cached if pyproject.toml doesn't change)
# This will compile prollytree once and cache it
RUN pip install --upgrade pip setuptools wheel && \
    pip install -e ".[dev]"

# Now copy the rest of the project (this won't trigger dependency rebuild)
COPY . .

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Create directories for memory store with proper permissions
RUN mkdir -p /app/data/memory_stores && \
    chmod 755 /app/data/memory_stores

# Initialize git config for the user (needed for versioned stores)
RUN git config --global user.email "memoir@docker.local" && \
    git config --global user.name "Memoir Docker"

# Expose port 8080 for the UI service
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080', timeout=5)" || exit 1

# Default command to run the UI server
CMD ["python", "-m", "src.memoir.ui.serve_ui"]  