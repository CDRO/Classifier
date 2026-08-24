FROM python:3.12-alpine

WORKDIR /app

COPY frontend/ ./frontend/
COPY app/ ./app/

RUN mkdir -p /data/source /data/destination /data/config
RUN pip install --no-cache-dir fastapi uvicorn

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]