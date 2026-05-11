from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <html>
        <head>
            <title>ONE APART</title>
        </head>

        <body style="font-family:Arial;padding:40px;">

            <h1>🏠 ONE APART</h1>

            <p>Сайт работает</p>

        </body>
    </html>
    """