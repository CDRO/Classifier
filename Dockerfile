FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn
RUN mkdir -p /data/source /data/destination /data/config

COPY frontend/ ./frontend/
COPY app/ ./app/


EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]