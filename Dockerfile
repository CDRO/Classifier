# Pinned: base image by digest, Python packages exactly. An unpinned `pip install` pulled
# PyMuPDF 2.1, which has no musllinux wheel, and the build failed trying to compile it.
# 1.28.2 is the newest PyMuPDF with a musllinux x86_64 wheel. Bump deliberately.
FROM python:3.12.16-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89

WORKDIR /app

RUN apk add --no-cache libstdc++ \
	tesseract-ocr \
	tesseract-ocr-data-eng \
	tesseract-ocr-data-deu \
	&& pip install --no-cache-dir --only-binary=:all: fastapi==0.165.0 uvicorn==0.54.0 pymupdf==1.28.2 httpx==0.28.1
RUN mkdir -p /data/source /data/destination /data/archive /data/config

COPY frontend/ ./frontend/
COPY app/ ./app/

EXPOSE 3000

ARG APP_VERSION=0.10.0
ARG APP_REVISION=unknown
ENV APP_VERSION=$APP_VERSION
ENV APP_REVISION=$APP_REVISION
ENV OCR_RENDER_SCALE=2
LABEL org.opencontainers.image.version=$APP_VERSION \
	org.opencontainers.image.revision=$APP_REVISION

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]