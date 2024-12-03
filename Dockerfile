FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static/advertisements

# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


#docker build -t fastapi .
#docker run --rm -it -p 8000 fastapi bash
#docker-compose up --build
#docker-compose down
#docker-compose down -v