from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import Settings, get_settings
from .modules.auth.router import router as auth_router
from .modules.health.router import router as health_router
from .modules.planning.router import router as planning_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs_enabled = settings.app_env != "production"
    app = FastAPI(
        title="VIDEO-SAAS API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(planning_router)
    return app


app = create_app()
