# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System runtime libs for Pillow and image codecs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libjpeg62-turbo \
       zlib1g \
       libpng16-16 \
       libtiff6 \
       libopenjp2-7 \
       libwebp7 \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package
RUN pip install --upgrade pip setuptools wheel \
    && pip install .

# Create default data mount points
RUN mkdir -p /data/in /data/out

EXPOSE 5000

# Optional healthcheck to ensure the app responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5000/ || exit 1

# Start the web UI on container start
CMD ["photo-normalizer-web", "--host", "0.0.0.0", "--port", "5000", "--no-debug"]


