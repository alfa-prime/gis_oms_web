from fastapi import APIRouter, Depends

from app.core import get_settings, HTTPXClient, get_httpx_client

settings = get_settings()

router = APIRouter(prefix="/health", tags=["Health check"])


@router.get("/ping")
def pong():
    return {"answer": "pong"}


@router.get("/httpx-client-test")
async def test(httpx_client: HTTPXClient = Depends(get_httpx_client)):
    url = "https://mkb-10.com/script/seachc.php"
    data = {"scode": "I11.9"}
    response = await httpx_client.fetch(url=url, metohd="POST", data=data)
    return [response["text"]]
