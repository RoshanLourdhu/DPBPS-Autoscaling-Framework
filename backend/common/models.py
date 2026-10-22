# backend/common/models.py
"""Pydantic models shared across service applications.
These are duplicated from the original monolith for simplicity.
"""
from __future__ import annotations
import uuid
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, validator

# ---------- Domain models ----------
class Product(BaseModel):
    id: str = Field(default_factory=lambda: "prod-" + uuid.uuid4().hex[:8])
    name: str
    description: Optional[str] = None
    price: float
    inventory: int = 0

class CartItem(BaseModel):
    product_id: str
    quantity: int = 1

class Cart(BaseModel):
    user_id: str = Field(default_factory=lambda: "user-" + uuid.uuid4().hex[:8])
    items: List[CartItem] = []

class CheckoutRequest(BaseModel):
    user_id: str
    payment_method: Literal["credit_card", "debit_card", "paypal"]
    address: str

    @validator("address")
    def non_empty(cls, v):
        if not v.strip():
            raise ValueError("address must not be empty")
        return v

class CheckoutResponse(BaseModel):
    order_id: str = Field(default_factory=lambda: "order-" + uuid.uuid4().hex[:8])
    status: Literal["SUCCESS", "FAILED"]
    total_amount: float
    message: Optional[str] = None

class Recommendation(BaseModel):
    product_id: str
    score: float

# ---------- Workload models (kept for compatibility) ----------
import enum
class WorkloadProfile(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SPIKE = "spike"

class WorkloadRequest(BaseModel):
    profile: WorkloadProfile
    duration_seconds: int = Field(..., gt=0, le=300)
    target_service: Literal["product", "cart", "checkout", "recommendation"]
    request_rate: int = Field(..., gt=0, le=1000)

class WorkloadResult(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: Optional[float] = None
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    start_timestamp: str
    end_timestamp: str
    status_code_counts: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    achieved_rps: float

class WorkloadStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class WorkloadInfo(BaseModel):
    workload_id: str
    status: WorkloadStatus
    result: Optional[WorkloadResult] = None
