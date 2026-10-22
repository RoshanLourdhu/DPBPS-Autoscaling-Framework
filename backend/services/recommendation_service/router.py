# backend/services/recommendation_service/router.py
"""Router for Recommendation Service.
Provides simple static recommendations based on the product catalog.
"""
from fastapi import APIRouter, HTTPException
from backend.common.models import Recommendation, Product
from backend.common.db import connection_context

router = APIRouter()

@router.get("/recommendations/{user_id}", response_model=list[Recommendation])
async def get_recommendations(user_id: str):
    # For this prototype we ignore the user_id and return top‑2 products.
    with connection_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, price, inventory FROM product LIMIT 2")
        rows = cur.fetchall()
        products = [Product(id=row[0], name=row[1], description=row[2], price=row[3], inventory=row[4]) for row in rows]
        # Simple static recommendation scores
        recommendations = [
            Recommendation(product_id=p.id, score=0.9 if i == 0 else 0.75)
            for i, p in enumerate(products)
        ]
        return recommendations
