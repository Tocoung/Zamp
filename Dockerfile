# ==========================================
# STAGE 1: Build Frontend SPA
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
# Build production assets to /app/frontend/dist
RUN npm run build

# ==========================================
# STAGE 2: Python Backend & Production Server
# ==========================================
FROM python:3.11-slim

# Install system dependencies for OCR and PDF rasterization
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY backend/ ./backend/

# Copy built frontend assets from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY frontend/static ./frontend/static

# Ensure persistent runtime directories exist
RUN mkdir -p /app/data/documents /app/storage

# Environment configuration
ENV PYTHONPATH=/app/backend
ENV ENVIRONMENT=production
ENV DEBUG=False
ENV BACKEND_HOST=0.0.0.0
ENV BACKEND_PORT=8000
ENV DOCUMENT_STORAGE_DIR=/app/data/documents
ENV DATABASE_URL=sqlite:////app/data/vendor_onboarding.db

EXPOSE 8000

# Mount static frontend files via FastAPI and run with Uvicorn (binds to Render's dynamic $PORT or 8000)
CMD ["sh", "-c", "python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
