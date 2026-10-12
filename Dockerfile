# All-in-one image: website + API in one container, for single-service hosts
# such as Render (see render.yaml and docs/DEPLOY_FREE.md).
# The docker-compose setup uses backend/Dockerfile and frontend/Dockerfile instead.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist ./static

RUN useradd --create-home appuser && chown appuser /app
USER appuser

EXPOSE 8000
# Hosts like Render tell the app which port to use through $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
