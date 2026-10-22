from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import v1_router

app = FastAPI(title="DPBPS Platform Backend", version="0.1.0")

# CORS configuration for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(v1_router, prefix="/api/v1")

@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Return basic health information for the backend service."""
    return {"status": "ok", "service": "dpbps-backend", "version": "0.1.0"}
