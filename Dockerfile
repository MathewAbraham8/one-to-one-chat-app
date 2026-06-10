# Use a slim Python official base image for a smaller footprint and secure defaults
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set working directory inside the container
WORKDIR /app

# Create a non-root group and user for security (minimizing container privileges)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Copy requirements file first to take advantage of Docker cache layer caching
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py /app/
COPY app/ /app/app/

# Create a data directory for the SQLite database and change owner to appuser
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the application port
EXPOSE 8000

# Start the application using uvicorn listening on 0.0.0.0 inside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
