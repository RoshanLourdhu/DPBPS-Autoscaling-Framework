# backend/services/cart_service/main.py
"""Cart Service – independent FastAPI application.
Provides cart CRUD endpoints and health check.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .router import router as cart_router
from backend.common.db import init_db

app = FastAPI(title="Cart Service", version="0.1.0")

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

app.include_router(cart_router, prefix="/api/v1")

@app.get("/health", tags=["health"]) 
async def health():
    return {"status": "ok", "service": "cart", "version": "0.1.0"}
