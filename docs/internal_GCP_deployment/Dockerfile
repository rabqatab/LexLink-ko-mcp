# LexLink MCP Server - GCP Cloud Run Dockerfile
#
# NOTE: This is an APPENDIX option. The recommended approach is source-based
# deployment which requires no Dockerfile. See README.md for details.
#
# Use this only if you need:
# - Custom build steps or dependencies
# - Multi-stage builds for smaller images
# - Full control over the container environment
#
# USAGE: Run from project root with:
#   docker build -f docs/internal_GCP_deployment/Dockerfile -t lexlink .

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (production only)
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ ./src/

# -------------------------------------------------------------------
# Production image
# -------------------------------------------------------------------
FROM python:3.12-slim AS production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from builder
COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv

# Copy virtual environment and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"

# MCP Server configuration
# IMPORTANT: TRANSPORT=http (not sse) for non-streaming compatibility
ENV TRANSPORT=http
ENV PORT=8080
ENV HOST=0.0.0.0

# Response handling
# Set to 'true' only if your MCP client has context length limits
# For enterprise use, 'false' preserves full law text responses
ENV SLIM_RESPONSE=false

# HTTP timeout for law.go.kr API (can be slow)
ENV HTTP_TIMEOUT_S=60

# OC will be injected via Secret Manager at runtime
# Do NOT set a default here

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash lexlink
USER lexlink

# Expose Cloud Run default port
EXPOSE 8080

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the MCP server
CMD ["python", "-m", "lexlink.http_server"]
