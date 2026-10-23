# One image for both Fly apps: the real map (fly.toml) and the public demo (fly.demo.toml).
# Fly builds it remotely with `fly deploy`; Docker isn't needed on this PC.

# 1. Build the map.
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2. The server: FastAPI serves the API and the built map on one port.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FOOD_MAP_FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8080
# Fly's proxy terminates https and forwards plain http.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
