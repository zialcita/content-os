import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from routers import assets, avatars, brands, health, personas, sources, videos, workspaces
from services.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("contentos")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    task = asyncio.create_task(scheduler_loop())
    logger.info("Content OS API ready")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


settings = get_settings()
app = FastAPI(
    title="Content OS",
    version="0.1.0",
    description="YouTube pillar pipeline MVP — script → HeyGen → B-roll → Shotstack → clips → YouTube",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(workspaces.router)
app.include_router(brands.router)
app.include_router(personas.router)
app.include_router(sources.router)
app.include_router(videos.router)
app.include_router(avatars.router)
app.include_router(assets.router)
