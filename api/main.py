import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException
from redis import Redis
from redis.exceptions import RedisError

from analysis import router as analysis_router
from demo import install_demo
from reports import router as report_router
from sources import dispatch_loop, router


def migrate():
    with psycopg.connect(connect_timeout=5) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(18432001)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for migration in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            if migration.name in applied:
                continue
            connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,)
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    install_demo()
    with Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2) as queue:
        queue.ping()
        app.state.queue = queue
        dispatcher = asyncio.create_task(dispatch_loop(queue))
        try:
            yield
        finally:
            dispatcher.cancel()
            with suppress(asyncio.CancelledError):
                await dispatcher


app = FastAPI(title="Контур", lifespan=lifespan)


app.include_router(router)
app.include_router(analysis_router)
app.include_router(report_router)


@app.get("/health")
def health():
    try:
        with psycopg.connect(connect_timeout=2) as connection:
            connection.execute("SELECT 1")
        app.state.queue.ping()
    except (psycopg.Error, RedisError):
        raise HTTPException(status_code=503, detail="Хранилище временно недоступно")
    return {"status": "ok"}
