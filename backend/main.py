import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from services.runtime_policy import RuntimeSafetyError, require_legacy_simulation

# Refuse BEFORE importing database (which constructs an engine), routes or
# scheduler. There is deliberately no boolean "v6 ready" bypass.
settings = get_settings()
require_legacy_simulation(settings)

from database import init_db  # noqa: E402
from routers import assets, avatars, brands, health, personas, sources, videos, workspaces  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("contentos")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    require_legacy_simulation(get_settings())
    init_db()  # Legacy create_all is confined to explicit non-production simulation.
    # No in-process global scheduler, including in simulation. Durable workers
    # need separate integration; HTTP workspace keys are not worker authority.
    logger.warning("Content OS LEGACY SIMULATION ready; no live spend or publication")
    yield


app = FastAPI(
    title="Content OS — Legacy Simulation",
    version="0.1.0",
    description="Development/test fixtures only. Published states and usage are simulated, not live outcomes.",
    lifespan=lifespan,
)


@app.middleware("http")
async def runtime_boundary(request: Request, call_next):
    # Protect ASGI clients which skip lifespan and settings changed after import,
    # before any route or dependency can mutate data.
    try:
        require_legacy_simulation(get_settings())
    except RuntimeSafetyError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    response = await call_next(request)
    response.headers["X-ContentOS-Mode"] = "simulation"
    response.headers["X-ContentOS-Usage"] = "simulation-not-provider-spend"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-ContentOS-Mode", "X-ContentOS-Usage"],
)

app.include_router(health.router)
app.include_router(workspaces.router)
app.include_router(brands.router)
app.include_router(personas.router)
app.include_router(sources.router)
app.include_router(videos.router)
app.include_router(avatars.router)
app.include_router(assets.router)
