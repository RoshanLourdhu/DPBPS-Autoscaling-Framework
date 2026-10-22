# backend/services/recommendation_service/main.py
"""Recommendation Service – independent FastAPI application.
Provides static recommendations based on product catalog.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .router import router as recommendation_router
from backend.common.db import init_db

app = FastAPI(title="Recommendation Service", version="0.1.0")

# CORS – allow all for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_db()

# Simple health endpoint
@app.get("/health", tags=["health"]) 
async def health():
    return {"status": "ok", "service": "recommendation", "version": "0.1.0"}

app.include_router(recommendation_router, prefix="/api/v1")
