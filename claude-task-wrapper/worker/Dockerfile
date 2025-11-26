# Worker Dockerfile with Claude Code CLI
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Node.js for Claude Code
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Verify Claude Code installation
RUN claude --version || echo "Claude Code installed"

# Copy requirements and install Python dependencies
COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy worker code
COPY worker /app/worker

# Set Python path
ENV PYTHONPATH=/app

# Create workspace directory
RUN mkdir -p /workspace

# Run worker
CMD ["python", "-m", "worker.main"]
