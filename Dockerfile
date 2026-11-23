
# MediFlow Analytics — Python ETL container

FROM python:3.11-slim

# Prevent Python from generating .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Display Python logs immediately
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy project files into the container
COPY . .

# Run the ETL pipeline
CMD ["python", "run_pipeline.py"]
