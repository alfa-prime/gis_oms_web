from fastapi import APIRouter, Depends

from app.core import get_settings, HTTPXClient, get_http_service

settings = get_settings()

router = APIRouter(prefix="/health", tags=["Health check"])


@router.get("/ping")
def pong():
    return {"answer": "pong"}


@router.get("/httpx-client-test")
async def test(http_service: HTTPXClient = Depends(get_http_service)):
    url = "https://mkb-10.com/script/seachc.php"
    data = {"scode": "I11.9"}
    response = await http_service.fetch(url=url, method="POST", data=data)
    return [response["text"]]
