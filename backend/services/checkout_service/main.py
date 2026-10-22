# backend/services/checkout_service/main.py
"""Checkout Service – independent FastAPI application.
Provides checkout processing by communicating with Cart and Product services via HTTP.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .router import router as checkout_router

app = FastAPI(title="Checkout Service", version="0.1.0")

# CORS – allow all for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple health endpoint
@app.get("/health", tags=["health"]) 
async def health():
    return {"status": "ok", "service": "checkout", "version": "0.1.0"}

# Include checkout router under /api/v1
app.include_router(checkout_router, prefix="/api/v1")
