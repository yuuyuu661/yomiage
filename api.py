from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from db import Database

app = FastAPI()

db = Database()


# =========================
# startup
# =========================

@app.on_event("startup")
async def startup():

    await db.connect()


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


# =========================
# 盤面取得API
# =========================

@app.get("/api/life/room/{room_id}")
async def get_room(room_id: str):

    rows = await db.fetch("""

    SELECT *
    FROM life_tiles
    WHERE room_id = $1
    ORDER BY tile_index ASC

    """,

        room_id
    )

    return {
        "tiles": [dict(r) for r in rows]
    }
