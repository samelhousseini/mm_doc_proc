FROM python:3.10-slim

WORKDIR /app

# Install essential packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements_aca_job.txt .
RUN pip install --no-cache-dir -r requirements_aca_job.txt

# Copy the application code
COPY . .

# Set the entrypoint to run the processing job
CMD ["python", "processing/jobs/main.py"]
