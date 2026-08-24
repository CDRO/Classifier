FROM python:3.12-alpine

ARG APP_VERSION=dev
LABEL org.opencontainers.image.version=$APP_VERSION
ENV APP_VERSION=$APP_VERSION

WORKDIR /app

RUN apk add --no-cache libstdc++ \
	tesseract-ocr \
	tesseract-ocr-data-eng \
	tesseract-ocr-data-deu \
	&& pip install --no-cache-dir fastapi uvicorn pymupdf httpx
RUN mkdir -p /data/source /data/destination /data/archive /data/config

COPY frontend/ ./frontend/
COPY app/ ./app/


EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]