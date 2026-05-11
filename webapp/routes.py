from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home():

    return """
    <html>
    <head>
        <title>Городская Пауза</title>
    </head>

    <body style="font-family:Arial;padding:40px">

        <h1>🏠 Городская Пауза</h1>

        <h2>Календарь подключается...</h2>

    </body>
    </html>
    """