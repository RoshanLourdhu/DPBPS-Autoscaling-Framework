# backend/services/checkout_service/router.py
"""Router for Checkout Service.
It communicates with Cart and Product services via HTTP to compute totals.
"""
from fastapi import APIRouter, HTTPException
from backend.common.models import CheckoutRequest, CheckoutResponse, Product, CartItem
import os
import httpx

router = APIRouter()

# Service URLs – can be overridden via env vars
CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://localhost:8002")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001")

async def _get_cart(user_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{CART_SERVICE_URL}/api/v1/cart/{user_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

async def _get_products() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PRODUCT_SERVICE_URL}/api/v1/products")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return {p["id"]: p for p in resp.json()}

@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(req: CheckoutRequest):
    # Retrieve cart
    cart = await _get_cart(req.user_id)
    items = cart.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    # Retrieve product catalog
    catalog = await _get_products()
    total = 0.0
    for item in items:
        prod_id = item.get("product_id")
        qty = item.get("quantity", 0)
        product = catalog.get(prod_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {prod_id} not found")
        total += product["price"] * qty
    # Successful checkout – return response (no state change needed here)
    return CheckoutResponse(status="SUCCESS", total_amount=total)
