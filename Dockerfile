FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY bot/ ./bot/

# Create directories
RUN mkdir -p /app/logs /app/data /app/temp

# Run bot
CMD ["python", "-m", "bot.main"]