from fastapi import APIRouter, Depends

from app.core import HTTPXClient, get_http_service
from app.services import fetch_and_process_handbook, process_insurance_file, process_rf_subjects_file

router = APIRouter(prefix="/nsi_handbooks", tags=["Справочники НСИ"])


@router.get("/get_ensurance_companies")
async def get_ensurance_companies(
    http_service: HTTPXClient = Depends(get_http_service)
):
    """Получаем справочник с данными страховых компаний. Для получения кода страховой организации (СМО)"""
    params = {
        "identifier": "1.2.643.5.1.13.13.99.2.722",
        "version": "3.2",
        "format": "JSON",
    }
    return await fetch_and_process_handbook(
        http_service=http_service,
        params=params,
        save_file_name="ias_ensurance_medical_organizations.zip",
        process_func=process_insurance_file,
        output_filename="ensurance_companies.json"
    )


@router.get("/get_rf_subjects")
async def get_rf_subjects(
    http_service: HTTPXClient = Depends(get_http_service)
):
    """Получаем справочник с данными регионов РФ. Для получения кода территории страхования (5-значного ОКАТО)"""
    params = {
        "identifier": "1.2.643.5.1.13.13.99.2.206",
        "version": "6.5",
        "format": "JSON",
    }
    return await fetch_and_process_handbook(
        http_service=http_service,
        params=params,
        save_file_name="rf_subjects.zip",
        process_func=process_rf_subjects_file,
        output_filename="rf_subjects.json"
    )
