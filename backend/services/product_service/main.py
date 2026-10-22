# backend/services/product_service/main.py
"""Product Service – independent FastAPI application.
Provides product catalog and health endpoint.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .router import router as product_router
from backend.common.db import init_db

app = FastAPI(title="Product Service", version="0.1.0")

# CORS – allow all for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise shared SQLite DB on startup
@app.on_event("startup")
async def startup_event():
    init_db()

app.include_router(product_router, prefix="/api/v1")

# Simple health endpoint
@app.get("/health", tags=["health"]) 
async def health():
    return {"status": "ok", "service": "product", "version": "0.1.0"}
