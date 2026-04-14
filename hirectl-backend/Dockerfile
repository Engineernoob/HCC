FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python package
COPY pyproject.toml .
COPY hirectl/ hirectl/
RUN pip install --no-cache-dir -e "."

# Create non-root user
RUN useradd -m -u 1000 hirectl && chown -R hirectl:hirectl /app
USER hirectl

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD sh -c 'curl -f http://localhost:${PORT:-8000}/healthz || exit 1'

CMD ["sh", "-c", "hirectl api --host 0.0.0.0 --port ${PORT:-8000}"]
