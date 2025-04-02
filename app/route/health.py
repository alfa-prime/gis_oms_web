from fastapi import APIRouter

from app.core import get_settings, HTTPXClient

settings = get_settings()

router = APIRouter(prefix="/health", tags=["Health check"])


@router.get("/ping")
def pong():
    return {"answer": "pong"}


@router.get("/httpx-client-test")
async def test():
    url = "https://mkb-10.com/script/seachc.php"
    data = {"scode": "I11.9"}
    response = await HTTPXClient.fetch(url=url, metohd="POST", data=data)
    return [response["text"]]
