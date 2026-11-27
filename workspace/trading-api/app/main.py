from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import Base, engine
from .routes import admin, llm, orders, portfolio

# Create tables eagerly so TestClient (no lifespan) also has a schema.
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)   # idempotent, re-runs at real startup
    yield


app = FastAPI(title="Trading212 × OpenClaw bridge", version="0.1.0", lifespan=lifespan)


@app.get("/api/healthz", tags=["meta"])
def healthz():
    return {"ok": True}


app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(llm.router)
app.include_router(admin.router)
