# backend/app/api/simulation.py
"""Simulation router that proxies calls to independent microservices.
It maintains the original workload creation/cancellation endpoints.
"""
from fastapi import APIRouter, HTTPException
from backend.common.models import (
    Product,
    Cart,
    CartItem,
    CheckoutRequest,
    CheckoutResponse,
    Recommendation,
    WorkloadRequest,
    WorkloadInfo,
)
from backend.app.api.state import (
    start_workload,
    get_workload_status,
    cancel_workload,
)
import os
import httpx

router = APIRouter()

# Service URLs – can be overridden via environment variables for local dev
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001")
CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://localhost:8002")
CHECKOUT_SERVICE_URL = os.getenv("CHECKOUT_SERVICE_URL", "http://localhost:8003")
RECOMMENDATION_SERVICE_URL = os.getenv("RECOMMENDATION_SERVICE_URL", "http://localhost:8004")

async def _service_get(path: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(path)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

async def _service_post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(path, json=payload)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

async def _service_delete(path: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.delete(path)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

@router.get("/services", response_model=list[str])
async def list_services():
    return ["product", "cart", "checkout", "recommendation"]

@router.get("/products", response_model=list[Product])
async def list_products():
    data = await _service_get(f"{PRODUCT_SERVICE_URL}/api/v1/products")
    return [Product(**p) for p in data]

@router.get("/cart/{user_id}", response_model=Cart)
async def get_user_cart(user_id: str):
    data = await _service_get(f"{CART_SERVICE_URL}/api/v1/cart/{user_id}")
    return Cart(**data)

@router.post("/cart/{user_id}/add", response_model=Cart)
async def add_item(user_id: str, item: CartItem):
    data = await _service_post(f"{CART_SERVICE_URL}/api/v1/cart/{user_id}/add", item.dict())
    return Cart(**data)

@router.delete("/cart/{user_id}")
async def delete_cart(user_id: str):
    await _service_delete(f"{CART_SERVICE_URL}/api/v1/cart/{user_id}")
    return {"detail": "cart cleared"}

@router.post("/checkout", response_model=CheckoutResponse)
async def do_checkout(req: CheckoutRequest):
    data = await _service_post(f"{CHECKOUT_SERVICE_URL}/api/v1/checkout", req.dict())
    return CheckoutResponse(**data)

@router.get("/recommendations/{user_id}", response_model=list[Recommendation])
async def get_reco(user_id: str):
    data = await _service_get(f"{RECOMMENDATION_SERVICE_URL}/api/v1/recommendations/{user_id}")
    return [Recommendation(**r) for r in data]

@router.post("/workload", response_model=dict)
async def launch_workload(req: WorkloadRequest):
    wl_id = await start_workload(req)
    return {"workload_id": wl_id, "status": "RUNNING"}

@router.post("/workload/{workload_id}/cancel", response_model=dict)
async def cancel_workload_endpoint(workload_id: str):
    cancelled = await cancel_workload(workload_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Workload not found or already completed")
    return {"workload_id": workload_id, "status": "CANCELLED"}

@router.get("/workload/{workload_id}", response_model=WorkloadInfo)
async def workload_status(workload_id: str):
    info = await get_workload_status(workload_id)
    if not info:
        raise HTTPException(status_code=404, detail="Workload not found")
    return info
