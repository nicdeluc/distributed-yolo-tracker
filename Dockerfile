# Base image
FROM python:3.10-slim

# Install system dependencies needed for OpenCV
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libgl1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install packages, including the lightweight (CPU-only) version of PyTorch
RUN pip install --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code and configuration files
COPY src/ /app/src/
COPY config/ /app/config/

# Command provided by docker-compose.yaml