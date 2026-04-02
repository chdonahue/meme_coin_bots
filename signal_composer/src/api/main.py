"""FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import (
    auth,
    strategies,
    performance,
    trades,
    paper_trading,
    live_trading,
)
from src.api.dependencies import set_paper_trading_manager
from src.db.connection import init_db, get_session
from src.paper_trading import PaperTradingManager


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment."""
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in origins.split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and paper trading manager on startup."""
    await init_db()

    # Initialize paper trading manager
    async def session_factory():
        return get_session()

    manager = PaperTradingManager(
        db_session_factory=session_factory,
        default_polling_interval=int(os.getenv("PAPER_TRADING_INTERVAL", "60")),
    )
    set_paper_trading_manager(manager)

    # Load any active sessions from database
    loaded = await manager.load_active_sessions()
    if loaded > 0:
        print(f"Loaded {loaded} active paper trading sessions")

    # Start the polling loop
    await manager.start_polling()

    yield

    # Cleanup on shutdown
    await manager.close()


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
app.include_router(paper_trading.router)
app.include_router(live_trading.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
