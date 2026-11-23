FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-render.txt ./requirements-render.txt
RUN pip install --no-cache-dir -r requirements-render.txt

COPY . .
RUN mkdir -p /app/data

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
