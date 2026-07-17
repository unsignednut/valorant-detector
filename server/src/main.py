from fastapi import FastAPI

from server.src.app.api import media, observations, sessions


def create_app() -> FastAPI:
    app = FastAPI(
        title="Valorant Detector",
        description="VALORANT video and screenshot analysis service",
        version="0.1.0",
    )

    app.include_router(sessions.router)
    app.include_router(media.router)
    app.include_router(observations.router)
    app.include_router(media.legacy_router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "status": "ok",
            "message": "Valorant Detector is running",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "version": "0.1.0",
        }

    return app


app = create_app()
