from fastapi import FastAPI

from cocina_control.api.health import router as health_router

app = FastAPI(
    title="Cocina Control API",
    version="0.1.0",
    description="Dark-kitchen inventory system API",
)

app.include_router(health_router)
