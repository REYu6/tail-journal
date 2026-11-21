FROM node:24-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 \
    PET_DATA_DIR=/var/lib/pet-studio \
    PET_WEB_DIR=/app/web/dist
WORKDIR /app
COPY requirements.txt requirements-providers.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 studio \
    && useradd --uid 10001 --gid studio --no-create-home --shell /usr/sbin/nologin studio \
    && install -d -o studio -g studio -m 0700 /var/lib/pet-studio
COPY server/ ./server/
COPY --from=frontend /build/web/dist /app/web/dist
USER studio
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=6s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).close()"]
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
