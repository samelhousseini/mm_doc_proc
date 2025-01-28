# Use the official Python 3.11 image from the Docker Hub
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Update and install basic dependencies
RUN apt-get update && apt-get install -y git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


# Copy requirements.txt to the container
COPY app_requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r app_requirements.txt

# Copy the app code to the container
COPY . .

# Expose the port the app runs on
EXPOSE 80

# Starting commands for various solutions:
# Uncomment the desired command to use that solution.

# FastAPI with Uvicorn (default)
CMD ["python", "sample.py"]
