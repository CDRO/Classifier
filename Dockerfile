FROM python:3.12-alpine

WORKDIR /app

COPY frontend/ ./frontend/

RUN mkdir -p /data/source /data/destination

EXPOSE 3000

CMD ["python", "-m", "http.server", "3000", "--directory", "/app/frontend"]