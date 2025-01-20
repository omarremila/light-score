FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgdal-dev \
    libexpat1 \
    gdal-bin \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]