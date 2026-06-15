from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from db import Database

app = FastAPI()
app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "https://jinseigame-production.up.railway.app"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]

)

db = Database()


# =========================
# startup
# =========================

@app.on_event("startup")
async def startup():

    print("API STARTUP")

    await db.connect()

    print("DB CONNECTED")


# =========================
# root
# =========================

@app.get("/")
async def root():

    print("ROOT ACCESS")

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

    print(
        f"LIFE ROOM ACCESS "
        f"room={room_id} "
        f"session={session}"
    )

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

    print(f"GET ROOM {room_id}")

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


# =========================
# 自分情報取得
# =========================

@app.get("/api/life/me/{room_id}")
async def get_me(
    room_id: str,
    session: str
):

    print(
        f"GET ME "
        f"room={room_id} "
        f"session={session}"
    )

    session_row = await db.fetchrow("""

    SELECT *
    FROM life_sessions
    WHERE session_token = $1

    """,

        session
    )

    if not session_row:

        print("INVALID SESSION")

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

        print("CREATE NEW PROGRESS")

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
@app.post("/api/life/roll/{room_id}")
async def roll_dice(
    room_id: str,
    session: str
):

    import random

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

        return {
            "error": "no progress"
        }

    current_position = progress["position"]
    current_dice = progress["dice_count"]
    if current_dice <= 0:

        return {
            "error": "no dice"
        }

    dice = random.randint(1, 6)

    new_position = min(
        current_position + dice,
        99
    )



    tile = await db.fetchrow("""

    SELECT *
    FROM life_tiles
    WHERE room_id = $1
    AND tile_index = $2

    """,

        room_id,
        new_position
    )
    original_tile = tile

    # =========================
    # 特殊マス処理
    # =========================

    if tile["tile_text"] == "1マス進む":

        new_position = min(
            new_position + 1,
            99
        )

        tile = await db.fetchrow("""

        SELECT *
        FROM life_tiles
        WHERE room_id = $1
        AND tile_index = $2

        """,

            room_id,
            new_position
        )

    elif tile["tile_text"] == "2マス戻る":

        new_position = max(
            new_position - 2,
            0
        )

        tile = await db.fetchrow("""

        SELECT *
        FROM life_tiles
        WHERE room_id = $1
        AND tile_index = $2

        """,

            room_id,
            new_position
        )

        await db.execute("""

        INSERT INTO life_history (

            user_id,
            room_id,
            action_type,
            message

        )

        VALUES ($1, $2, $3, $4)

        """,

            user_id,
            room_id,
            "roll",
            f"出目:{dice} / 停止マス:{tile['tile_text']}"

        )

        return {

            "dice": dice,
            "position": new_position,
            "tile": dict(tile),
            "dice_count": current_dice - 1

        }








