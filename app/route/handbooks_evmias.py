from fastapi import APIRouter, Depends, HTTPException

from app.services.cookies.cookies import set_cookies
from app.core.logger import logger
from app.core.httpx_client import HTTPXClient
from app.core.config import get_settings
from app.services.tools.tools import save_handbook

settings = get_settings()

# Базовые настройки для запросов
BASE_URL = settings.BASE_URL
HEADERS = {
    "Origin": settings.BASE_HEADERS_ORIGIN_URL,
    "Referer": settings.BASE_HEADERS_REFERER_URL,
}
HANDBOOKS_DIR = settings.HANDBOOKS_DIR

# ID организации (ММЦ Пирогова)
LPU_ID = settings.LPU_ID

router = APIRouter(prefix="/evmias_handbooks", tags=["Справочники ЕВМИАС"])


@router.get("/referred_by")
async def get_referred_by_handbook(cookies: dict = Depends(set_cookies)):
    """Получаем справочник с типами кто направил пациента (другая МО и прочее)"""
    try:
        logger.debug("Запрос справочника 'referred_by' начат")
        url = BASE_URL
        headers = HEADERS
        params = {
            "c": "MongoDBWork",
            "m": "getData",
            "object": "SFPrehospDirect",  # noqau
            "SFPrehospDirect_id": "",
            "SFPrehospDirect_Code": "",
            "SFPrehospDirect_Name": "",
            "SFPrehospDirect_SysNick": "",
            "remove": "",
            "intersection": "",
            "object": "SFPrehospDirect"  # noqau
        }

        response = await HTTPXClient.fetch(url=url, method="POST", cookies=cookies, params=params, headers=headers)

        result = {}
        for entry in response['json']:
            id = entry.get("SFPrehospDirect_id", "")
            name = entry.get("SFPrehospDirect_Name", "")
            code = entry.get("SFPrehospDirect_Code", "")
            nick = entry.get("SFPrehospDirect_SysNick", "")

            if id:
                result[id] = {
                    "code": code,
                    "name": name,
                    "nick": nick
                }

        await save_handbook(result, "referred_by.json")
        logger.info(f"Справочник 'referred_by' сохранен в {HANDBOOKS_DIR}/referred_by.json")
        return result

    except Exception as e:
        logger.error(f"Ошибка в get_referred_by_handbook: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения справочника 'referred_by': {e}")


@router.get("/lpu_departments")
async def get_lpu_departments_handbook(cookies: dict = Depends(set_cookies)):
    """Получаем справочник отделений МО"""
    try:
        logger.debug("Запрос справочника 'lpu_departments' начат")
        url = BASE_URL
        headers = HEADERS
        params = {"c": "Common", "m": "loadLpuSectionList"}
        data = {
            "Lpu_id": LPU_ID,
        }
        response = await HTTPXClient.fetch(url=url, method="POST", cookies=cookies, params=params, data=data,
                                           headers=headers)

        result = {}
        for entry in response['json']:
            result[entry["LpuSection_id"]] = {
                "name": entry["LpuSection_Name"]
            }

        await save_handbook(result, "referred_lpu_departments.json")
        logger.info(f"Справочник 'lpu_departments' сохранен в {HANDBOOKS_DIR}/referred_lpu_departments.json")
        return {"resutl": result}

    except Exception as e:
        logger.error(f"Ошибка в get_lpu_departments_handbook: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения справочника 'lpu_departments': {e}")


@router.get("/referred_organizations")
async def get_referred_organizations_handbook(cookies: dict = Depends(set_cookies)):
    """Получаем справочник организаций, которые направляли пациента"""
    try:
        logger.debug("Запрос справочника 'referred_organizations' начат")
        url = BASE_URL
        headers = HEADERS
        params = {"c": "Org", "m": "getOrgList"}
        data = {
            "Org_id": "",
            "object": "Org",
            "onlyActual": "2",
            "OrgServed_Type": "1",
            "OrgType": "lpu",
            "Org_IsNotForSystem": "1",
            "onlyFromDictionary": "false",
            "needOrgType": "1",
            "closedOrgs": "0",
        }
        response = await HTTPXClient.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
            timeout=300
        )

        result = {}
        for entry in response['json']:
            result[entry["Org_id"]] = {
                "code": entry["Org_Code"],
                "nick": entry["Org_Nick"],
                "name": entry["Org_Name"]
            }

        await save_handbook(result, "referred_organizations.json")
        logger.info(f"Справочник 'referred_organizations' сохранен в {HANDBOOKS_DIR}/referred_organizations.json")
        return result

    except Exception as e:
        logger.error(f"Ошибка в get_referred_organizations_handbook: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения справочника организаций: {e}")
