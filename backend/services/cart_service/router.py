# backend/services/cart_service/router.py
"""Router for Cart Service.
Provides cart retrieval, add item, and clear operations.
"""
from fastapi import APIRouter, HTTPException
from backend.common.models import Cart, CartItem
from backend.common.db import connection_context, PLACEHOLDER

router = APIRouter()


@router.get("/cart/{user_id}", response_model=Cart)
async def get_cart(user_id: str):
    with connection_context() as conn:
        cur = conn.cursor()
        # Ensure cart exists
        cur.execute(f"SELECT user_id FROM cart WHERE user_id = {PLACEHOLDER}", (user_id,))
        if not cur.fetchone():
            # create empty cart
            cur.execute(f"INSERT INTO cart (user_id) VALUES ({PLACEHOLDER})", (user_id,))
            conn.commit()
        # fetch items
        cur.execute(
            f"SELECT product_id, quantity FROM cart_item WHERE cart_user_id = {PLACEHOLDER}",
            (user_id,)
        )
        rows = cur.fetchall()
        items = [CartItem(product_id=row[0], quantity=row[1]) for row in rows]
        return Cart(user_id=user_id, items=items)

@router.post("/cart/{user_id}/add", response_model=Cart)
async def add_to_cart(user_id: str, item: CartItem):
    with connection_context() as conn:
        cur = conn.cursor()
        # Ensure cart exists
        cur.execute(f"SELECT user_id FROM cart WHERE user_id = {PLACEHOLDER}", (user_id,))
        if not cur.fetchone():
            cur.execute(f"INSERT INTO cart (user_id) VALUES ({PLACEHOLDER})", (user_id,))
        # Upsert cart_item
        cur.execute(
            f"INSERT INTO cart_item (cart_user_id, product_id, quantity) VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}) ON CONFLICT(cart_user_id, product_id) DO UPDATE SET quantity = cart_item.quantity + excluded.quantity"
            (user_id, item.product_id, item.quantity),
        )
        conn.commit()
        # Return updated cart
        cur.execute(
            f"SELECT product_id, quantity FROM cart_item WHERE cart_user_id = {PLACEHOLDER}",
            (user_id,)
        )
        rows = cur.fetchall()
        items = [CartItem(product_id=row[0], quantity=row[1]) for row in rows]
        return Cart(user_id=user_id, items=items)

@router.delete("/cart/{user_id}")
async def clear_cart(user_id: str):
    with connection_context() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM cart_item WHERE cart_user_id = {PLACEHOLDER}", (user_id,))
        cur.execute(f"DELETE FROM cart WHERE user_id = {PLACEHOLDER}", (user_id,))
        conn.commit()
    return {"detail": "cart cleared"}
