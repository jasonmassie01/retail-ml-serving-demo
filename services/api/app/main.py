from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.emulator import build_emulator_service
from app.models import EventRequest, EventResponse, ServeRequest, ServeResponse
from app.serving import RetailServingService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    service = _build_service(config)
    app = FastAPI(title="Retail ML Serving Demo API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok" if service else "missing_config", **config.api_status()}

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return config.api_status()

    @app.post("/api/serve", response_model=ServeResponse, response_model_by_alias=True)
    def serve(request: ServeRequest) -> ServeResponse:
        if service is None:
            raise HTTPException(status_code=503, detail=config.api_status())
        try:
            return service.serve(request)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/events", response_model=EventResponse, response_model_by_alias=True)
    def publish_event(request: EventRequest) -> EventResponse:
        if service is None:
            raise HTTPException(status_code=503, detail=config.api_status())
        try:
            return service.publish_event(
                request.product_id,
                request.event_type,
                request.occurred_at,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


def _build_service(settings: Settings) -> RetailServingService | None:
    if settings.serving_mode != "live":
        return build_emulator_service(settings)
    if settings.missing_live_fields():
        return None

    from app.gcp_clients import build_live_service

    return build_live_service(settings)


app = create_app()
