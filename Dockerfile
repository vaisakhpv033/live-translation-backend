# Use an official lightweight Python image
FROM python:3.12-slim

# Install system dependencies (ffmpeg for audio transcoding, espeak-ng for phonetics)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Copy the uv binary from the official image for fast installations
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory inside the container
WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml ./

# Install CPU-optimized PyTorch first, then project dependencies using uv
RUN uv pip install --system --no-cache torch --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy the rest of the application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Run FastAPI via uvicorn with 1 worker to protect 4GB RAM ceiling
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
