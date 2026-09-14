"""Minimal same-origin development workbench; no fixture login or production bypass."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from secure_api.app import create_app
from .router import create_router


def create_workbench_router():
    ui=APIRouter()
    @ui.get('/api/v6/workflow',response_class=HTMLResponse,include_in_schema=False)
    def workbench():
        return HTMLResponse(Path(__file__).with_name('workbench.html').read_text(),headers={'Cache-Control':'no-store'})
    return ui


def build_workflow_app(settings,runtime_engine,authentication_engine,store,*,oidc_transport=None):
    return create_app(settings,runtime_engine,authentication_engine,oidc_transport=oidc_transport,
                      feature_routers=[create_router(store),create_workbench_router()])
