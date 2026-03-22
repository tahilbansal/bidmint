 # Use the official Playwright Python image — includes Chromium + all system deps pre-installed
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers are already baked into the base image (no install needed)
# But we still need to set the correct browser path env var
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy application code
COPY . .

# Default command (overridden per service in render.yaml)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
