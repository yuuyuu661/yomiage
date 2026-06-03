from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get("/")
async def root():

    return {
        "status": "ok"
    }


# =========================
# 人生ゲームルーム
# =========================

@app.get("/life/{room_id}")
async def life_room(
    room_id: str,
    session: str = None
):

    return HTMLResponse(f"""

    <html>

    <head>
        <title>人生ゲーム</title>
    </head>

    <body style="background:#111;color:white;font-family:sans-serif;">

        <h1>🎲 人生ゲーム</h1>

        <p>ROOM ID: {room_id}</p>

        <p>SESSION: {session}</p>

    </body>

    </html>

    """)
