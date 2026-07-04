# Use an official lightweight Python image
FROM python:3.12-slim

# Copy the uv binary from the official image for fast installations
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory inside the container
WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml ./

# Install dependencies using uv (installs package dependencies directly to system context inside the container)
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy the rest of the application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Run FastAPI via uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
