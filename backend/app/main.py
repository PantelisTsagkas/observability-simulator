import asyncio
import random
import time

import structlog
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from app.logging_config import setup_logging
from app.metrics import router as metrics_router
from app.middleware import RequestIDMiddleware

setup_logging()
logger = structlog.get_logger()

app = FastAPI(title="System Behaviour Simulator", version="1.0.0")
app.add_middleware(RequestIDMiddleware)
app.include_router(metrics_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/simulate/success")
async def simulate_success():
    await logger.ainfo("simulate_success", detail="Request completed normally")
    return {"status": "success", "message": "Everything is fine"}


@app.get("/simulate/error")
async def simulate_error():
    await logger.aerror("simulate_error", detail="Intentional server error triggered")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error (simulated)"},
    )


@app.get("/simulate/slow")
async def simulate_slow(delay: float = Query(default=3.0, ge=0.1, le=30.0)):
    await logger.awarning("simulate_slow", detail=f"Sleeping for {delay}s")
    await asyncio.sleep(delay)
    return {"status": "success", "message": f"Responded after {delay}s delay"}


@app.get("/simulate/cpu")
async def simulate_cpu():
    await logger.awarning("simulate_cpu", detail="Starting CPU-intensive task")
    start = time.perf_counter()
    # Burn CPU for ~1-2 seconds
    total = 0
    for i in range(5_000_000):
        total += i * i
    duration = round(time.perf_counter() - start, 3)
    return {"status": "success", "message": f"CPU task completed in {duration}s"}


@app.get("/simulate/random")
async def simulate_random():
    """Randomly succeeds or fails to simulate unpredictable behaviour."""
    if random.random() < 0.4:
        await logger.aerror("simulate_random", outcome="failure")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Random failure occurred"},
        )
    delay = random.uniform(0.05, 0.5)
    await asyncio.sleep(delay)
    await logger.ainfo("simulate_random", outcome="success", latency=round(delay, 3))
    return {"status": "success", "message": f"Random success after {round(delay, 3)}s"}
