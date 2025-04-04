from fastapi import APIRouter

from .gis_oms_person import router as gis_oms_web_router
from .handbooks_evmias import router as evmias_router
from .handbooks_nsi import router as nsi_router
from .handbooks_nsi_foms import router as nsi_forms_router
from .health import router as health_router

router = APIRouter(prefix="/api")
router.include_router(health_router)
router.include_router(gis_oms_web_router)
router.include_router(nsi_router)
router.include_router(nsi_forms_router)
router.include_router(evmias_router)
