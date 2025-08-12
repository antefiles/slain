import asyncio
import logging
from os import environ
from contextlib import contextmanager, suppress
from pathlib import Path
import shutil

import asyncpg
from dotenv import load_dotenv
from rich.logging import RichHandler
from bot.core import Bot
from bot.core.rate_limiter import DynamicRateLimiter

load_dotenv()

@contextmanager
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True, 
    )
    yield

async def initialize_database() -> asyncpg.Pool:
    keys = ("USER", "PASSWORD", "NAME", "HOST", "PORT")
    if not all(environ.get(f"DATABASE_{key}") for key in keys):
        raise RuntimeError("Database environment variables are not set.")

    pool = await asyncpg.create_pool(
        user=environ["DATABASE_USER"],
        password=environ["DATABASE_PASSWORD"],
        host=environ["DATABASE_HOST"],
        port=int(environ["DATABASE_PORT"]),
        database=environ["DATABASE_NAME"],
    )

    if not pool:
        raise Exception("Failed to connect to the database.")

    try:
        with open("schema.sql") as file:
            await pool.execute(file.read())
    except Exception as exc:
        raise RuntimeError("Failed to write schema to database") from exc

    return pool


async def cleanup_pycache():
    await asyncio.sleep(15)
    
    with suppress(Exception):
        for pycache_dir in Path(".").rglob("__pycache__"):
            if pycache_dir.is_dir():
                shutil.rmtree(pycache_dir, ignore_errors=True)


async def main():
    async with Bot() as bot:
        bot.pool = await initialize_database()
        bot.rate_limiter = DynamicRateLimiter(bot.pool)
        
        asyncio.create_task(cleanup_pycache())
        
        await bot.start("")

if __name__ == "__main__":
    with setup_logging(), suppress(KeyboardInterrupt, ProcessLookupError):
        asyncio.run(main())