from fastapi import APIRouter

from .gis_oms import router as gis_oms_web_router
from .handbooks_evmias import router as evmias_router
# from .handbooks_nsi import router as nsi_router
from .handbooks_nsi_foms import router as nsi_forms_router
from .health import router as health_router
from .frontend import router as frontend_router
from .test_area import router as test_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(gis_oms_web_router)
# api_router.include_router(nsi_router)
api_router.include_router(nsi_forms_router)
api_router.include_router(evmias_router)
api_router.include_router(test_router)

web_router = APIRouter(prefix="/web")
web_router.include_router(frontend_router)


__all__ = [
    "api_router",
    "web_router"
]
