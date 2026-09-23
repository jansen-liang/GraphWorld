from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import auth, health, object_catalog, runs, scenes
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
    app.include_router(auth.router, prefix=settings.api_prefix, tags=["auth"])
    app.include_router(scenes.router, prefix=settings.api_prefix, tags=["scenes"])
    app.include_router(object_catalog.router, prefix=settings.api_prefix, tags=["object-catalog"])
    app.include_router(runs.router, prefix=settings.api_prefix, tags=["runs"])
    return app


app = create_app()
