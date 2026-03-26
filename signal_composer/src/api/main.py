"""FastAPI application."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import auth


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment."""
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in origins.split(",")]


app = FastAPI(
    title="SignalComposer API",
    description="Trading strategy management and backtesting",
    version="0.1.0",
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
