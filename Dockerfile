FROM python:3.12-alpine

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

ARG APP_VERSION=0.1.0
ARG APP_REVISION=unknown
ENV APP_VERSION=$APP_VERSION
ENV APP_REVISION=$APP_REVISION
LABEL org.opencontainers.image.version=$APP_VERSION \
	org.opencontainers.image.revision=$APP_REVISION

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]