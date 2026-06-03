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

@app.get("/api/life/me/{room_id}")
async def get_me(
    room_id: str,
    session: str
):

    session_row = await db.fetchrow("""

    SELECT *
    FROM life_sessions
    WHERE session_token = $1

    """,

        session
    )

    if not session_row:
        return {
            "error": "invalid session"
        }

    user_id = session_row["user_id"]

    progress = await db.fetchrow("""

    SELECT *
    FROM life_user_progress
    WHERE user_id = $1
    AND room_id = $2

    """,

        user_id,
        room_id
    )

    if not progress:

        await db.execute("""

        INSERT INTO life_user_progress (

            user_id,
            room_id,
            dice_count,
            position

        )

        VALUES ($1, $2, $3, $4)

        """,

            user_id,
            room_id,
            0,
            0
        )

        position = 0
        dice_count = 0

    else:

        position = progress["position"]
        dice_count = progress["dice_count"]

    return {

        "user_id": user_id,
        "position": position,
        "dice_count": dice_count

    }

@app.get("/")
async def root():

    print("ROOT ACCESS")

    return {
        "status": "ok"
    }

@app.get("/life/{room_id}")
async def life_room(
    room_id: str,
    session: str = None
):

    print(
        f"LIFE ROOM ACCESS "
        f"room={room_id} "
        f"session={session}"
    )
