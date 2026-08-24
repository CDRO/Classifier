FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache libstdc++ \
	&& pip install --no-cache-dir fastapi uvicorn pymupdf httpx
RUN mkdir -p /data/source /data/destination /data/archive /data/config

COPY frontend/ ./frontend/
COPY app/ ./app/


EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]