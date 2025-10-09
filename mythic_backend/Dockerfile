FROM python:3.11-slim

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  curl wget && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --upgrade pip && \
  pip install --no-cache-dir -r requirements.txt

  COPY . .

# Создаем папку для данных
RUN mkdir -p /usr/src/app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-keep-alive", "120", "--timeout-graceful-shutdown", "30"]
