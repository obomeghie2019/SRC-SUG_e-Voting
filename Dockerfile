FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt cryptography

COPY . .

EXPOSE 8001 8002

# The command is set per service in docker-compose.yml
CMD ["uvicorn", "api_web.main:app", "--host", "0.0.0.0", "--port", "8001"]
