import asyncpg
import os

from dotenv import load_dotenv

load_dotenv()


class Database:

    def __init__(self):

        self.pool = None

    async def connect(self):

        self.pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL")
        )

    async def execute(self, query, *args):

        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query, *args):

        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query, *args):

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def init_db(self):

        await self.execute("""
        CREATE TABLE IF NOT EXISTS life_rooms (
            room_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        
        await self.execute("""
        CREATE TABLE IF NOT EXISTS life_user_progress (
            user_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            dice_count INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_id, room_id)
        )
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS life_panels (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS life_history (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            message TEXT NOT NULL,
            memo TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        # =========================
        # 人生ゲーム session
        # =========================

        await self.execute("""
        CREATE TABLE IF NOT EXISTS life_sessions (
            id SERIAL PRIMARY KEY,
            session_token TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """)

