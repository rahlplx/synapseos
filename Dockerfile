FROM python:3.11-slim

WORKDIR /app

# ARM CPU tuning
ENV OMP_NUM_THREADS=4
ENV PYTHONUNBUFFERED=1
ENV DOCLING_CPU_ONLY=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
