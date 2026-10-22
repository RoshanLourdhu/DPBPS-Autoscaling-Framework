# backend/Dockerfile
# -------------------------------------------------------------------
# Builder stage – install Python dependencies
# -------------------------------------------------------------------
FROM python:3.11-slim AS builder
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# -------------------------------------------------------------------
# Runtime stage – copy code and run appropriate FastAPI app
# -------------------------------------------------------------------
FROM python:3.11-slim
WORKDIR /app
ARG SERVICE_MODULE=backend.app.main:app
ENV SERVICE_MODULE=${SERVICE_MODULE}

# Install curl (used by health checks) and clean up apt lists
RUN apt-get update && apt-get install -y curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Create non‑root user
# User will be created after installing packages to ensure correct permissions
# USER appuser (moved later)

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy source code (only needed directories)
COPY backend/ ./backend/
# Create non‑root user and ensure permissions
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && chmod -R a+rx /usr/local/lib/python3.11/site-packages /usr/local/bin
USER appuser

# Environment variables – can be overridden at runtime
ENV DB_PATH=/app/data/dev.db \
    PRODUCT_SERVICE_URL=http://product-service:8000 \
    CART_SERVICE_URL=http://cart-service:8000 \
    CHECKOUT_SERVICE_URL=http://checkout-service:8000 \
    RECOMMENDATION_SERVICE_URL=http://recommendation-service:8000 \
    SERVICE_MODULE=backend.app.main:app

# Expose the FastAPI port (internal to the container)
EXPOSE 8000

# Entry point – use shell form so the env variable SERVICE_MODULE is expanded
CMD ["/bin/sh","-c","python -m uvicorn ${SERVICE_MODULE} --host 0.0.0.0 --port 8000"]
