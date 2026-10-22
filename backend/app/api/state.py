import uuid
import asyncio
import time
import os
from typing import Dict, List
import httpx
from .models import (
    Product,
    Cart,
    CartItem,
    WorkloadInfo,
    WorkloadResult,
    WorkloadStatus,
    WorkloadProfile,
    WorkloadRequest,
)

# ---------- Demo data ----------
_demo_products: List[Product] = [
    Product(name="Widget A", description="Simple widget", price=9.99, inventory=100),
    Product(name="Gadget B", description="Fancy gadget", price=19.99, inventory=50),
    Product(name="Doohickey C", description="Mysterious doohickey", price=4.99, inventory=200),
]

# carts keyed by user_id
_carts: Dict[str, Cart] = {}

# ---------- Workload management ----------
_workload_store: Dict[str, WorkloadInfo] = {}
_workload_lock = asyncio.Lock()
# Limit concurrent HTTP requests across all workloads (global semaphore)
_concurrent_semaphore = asyncio.Semaphore(50)
# Limit concurrent running workloads (to avoid overload)
_max_running_workloads = 5
_running_workload_semaphore = asyncio.Semaphore(_max_running_workloads)
# Retention: keep at most 100 completed workloads in memory
_MAX_COMPLETED = 100
# Track asyncio Tasks for cancellation
_task_store: Dict[str, asyncio.Task] = {}

def get_product_catalog() -> List[Product]:
    return list(_demo_products)

def get_cart(user_id: str) -> Cart:
    return _carts.get(user_id, Cart(user_id=user_id, items=[]))

def add_to_cart(user_id: str, item: CartItem) -> Cart:
    cart = _carts.setdefault(user_id, Cart(user_id=user_id, items=[]))
    for existing in cart.items:
        if existing.product_id == item.product_id:
            existing.quantity += item.quantity
            break
    else:
        cart.items.append(item)
    return cart

def clear_cart(user_id: str) -> None:
    _carts.pop(user_id, None)

# ---------- Internal helper ----------
async def _record_workload(info: WorkloadInfo):
    async with _workload_lock:
        _workload_store[info.workload_id] = info
        # enforce retention of completed workloads
        completed = [wid for wid, w in _workload_store.items() if w.status == WorkloadStatus.COMPLETED]
        if len(completed) > _MAX_COMPLETED:
            for wid in completed[: len(completed) - _MAX_COMPLETED]:
                _workload_store.pop(wid, None)

# ---------- Execution engine ----------
async def _execute_workload(workload_id: str, req: WorkloadRequest):
    profile = req.profile
    duration = req.duration_seconds
    rate = req.request_rate
    target = req.target_service

    interval = 1.0 / rate  # seconds between requests (target RPS)
    total_expected = duration * rate

    start_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    latencies: List[float] = []
    status_counts: Dict[int, int] = {}
    successes = 0
    failures = 0

    base_url = os.getenv("SIMULATION_TARGET_BASE_URL", "http://127.0.0.1:8000")
    endpoint_map = {
        "product": "/api/v1/simulation/products",
        "cart": "/api/v1/simulation/cart/demo_user",
        "checkout": "/api/v1/simulation/checkout",
        "recommendation": "/api/v1/simulation/recommendations/demo_user",
    }
    url = base_url + endpoint_map[target]

    async with httpx.AsyncClient(timeout=10.0) as client:
        next_time = time.monotonic()
        for _ in range(total_expected):
            now = time.monotonic()
            if now < next_time:
                await asyncio.sleep(next_time - now)
            next_time += interval

            async with _concurrent_semaphore:
                try:
                    if target == "checkout":
                        user_id = "workload_user"
                        prod = _demo_products[0]
                        add_to_cart(user_id, CartItem(product_id=prod.id, quantity=1))
                        payload = {
                            "user_id": user_id,
                            "payment_method": "credit_card",
                            "address": "123 Demo St",
                        }
                        resp = await client.post(url, json=payload)
                    else:
                        resp = await client.get(url)
                    elapsed_ms = (time.monotonic() - now) * 1000.0
                    latencies.append(elapsed_ms)
                    status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
                    if 200 <= resp.status_code < 300:
                        successes += 1
                    else:
                        failures += 1
                except Exception:
                    failures += 1
                    status_counts[0] = status_counts.get(0, 0) + 1

    end_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if latencies:
        avg = sum(latencies) / len(latencies)
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.5)]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
    else:
        avg = p50 = p95 = p99 = 0.0

    result = WorkloadResult(
        total_requests=total_expected,
        successful_requests=successes,
        failed_requests=failures,
        avg_latency_ms=avg,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        status_code_counts={str(k): v for k, v in status_counts.items()},
        failure_categories={},
        achieved_rps=successes / duration if duration else 0.0,
    )
    info = WorkloadInfo(workload_id=workload_id, status=WorkloadStatus.COMPLETED, result=result)
    await _record_workload(info)

async def start_workload(req: WorkloadRequest) -> str:
    wl_id = str(uuid.uuid4())
    # Acquire semaphore to limit concurrent running workloads
    await _running_workload_semaphore.acquire()
    info = WorkloadInfo(workload_id=wl_id, status=WorkloadStatus.RUNNING, result=None)
    await _record_workload(info)
    task = asyncio.create_task(_execute_workload(wl_id, req))
    _task_store[wl_id] = task
    # When the task finishes, release the running semaphore and cleanup the task store
    def _done_callback(t: asyncio.Task):
        _running_workload_semaphore.release()
        _task_store.pop(wl_id, None)
    task.add_done_callback(_done_callback)
    return wl_id

async def get_workload_status(workload_id: str) -> WorkloadInfo | None:
    async with _workload_lock:
        return _workload_store.get(workload_id)

async def cancel_workload(workload_id: str) -> bool:
    """Attempt to cancel a running workload. Returns True if cancelled, False otherwise."""
    task = _task_store.get(workload_id)
    if task and not task.done():
        task.cancel()
        # Update status to CANCELLED
        info = WorkloadInfo(workload_id=workload_id, status=WorkloadStatus.CANCELLED, result=None)
        await _record_workload(info)
        return True
    return False
