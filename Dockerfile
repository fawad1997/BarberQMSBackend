FROM python:3.11-slim

WORKDIR /app

# Set environment variables to avoid Python bytecode and ensure output is shown
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install PostgreSQL client for DB interaction (optional, if needed for debugging)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy and install the Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Run migrations (uncomment this line to ensure DB schema is updated)
#RUN alembic upgrade head

# Create static directories if required
RUN mkdir -p static/advertisements

# Expose the port the app runs on
EXPOSE 8000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
