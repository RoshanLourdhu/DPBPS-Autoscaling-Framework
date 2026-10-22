# backend/services/product_service/router.py
"""Router for Product Service.
Provides product catalog and optional health endpoints.
"""
from fastapi import APIRouter, HTTPException
from backend.common.models import Product
from backend.common.db import connection_context, DB_BACKEND

router = APIRouter()

PLACEHOLDER = "?" if DB_BACKEND == "sqlite" else "%s"


@router.get("/products", response_model=list[Product])
async def list_products():
    # Fetch all products from SQLite DB
    with connection_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, price, inventory FROM product")
        rows = cur.fetchall()
        products = [Product(id=row[0], name=row[1], description=row[2], price=row[3], inventory=row[4]) for row in rows]
    return products

# Optional individual product lookup
@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    with connection_context() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT id, name, description, price, inventory FROM product WHERE id = {PLACEHOLDER}", (product_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        return Product(id=row[0], name=row[1], description=row[2], price=row[3], inventory=row[4])
