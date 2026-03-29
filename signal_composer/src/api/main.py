"""FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import auth, strategies, performance, trades
from src.db.connection import init_db


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment."""
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in origins.split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="SignalComposer API",
    description="Trading strategy management and backtesting",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(strategies.router)
app.include_router(performance.router)
app.include_router(trades.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
