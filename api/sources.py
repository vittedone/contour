import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from rq import Queue

from dispatch_analysis import dispatch_analysis

router = APIRouter()
uploads = Path("/data/uploads")
max_pdf = int(os.getenv("MAX_PDF_MB", "16")) * 1024**2


class Question(BaseModel):
    question: str = Field(max_length=2000)


class Link(BaseModel):
    url: str = Field(max_length=4096)


def database():
    return psycopg.connect(connect_timeout=5, row_factory=dict_row)


def require_research(db, research_id):
    if not db.execute("SELECT 1 FROM research WHERE id=%s", (research_id,)).fetchone():
        raise HTTPException(404, "Исследование не найдено.")


@router.post("/research", status_code=201)
def create_research(data: Question):
    question = data.question.strip()
    if not question or "\x00" in question:
        raise HTTPException(422, "Введите исследовательский вопрос.")
    with database() as db:
        return db.execute(
            "INSERT INTO research (question) VALUES (%s) RETURNING id, question", (question,)
        ).fetchone()


@router.get("/research")
def list_research():
    with database() as db:
        return db.execute("SELECT id, question, is_demo FROM research ORDER BY is_demo, created_at DESC").fetchall()


@router.get("/research/{research_id}/sources")
def list_sources(research_id: UUID):
    with database() as db:
        require_research(db, research_id)
        return db.execute(
            "SELECT id, kind, name, status, error FROM source WHERE research_id=%s "
            "ORDER BY created_at DESC", (research_id,)
        ).fetchall()


@router.post("/research/{research_id}/links", status_code=202)
def add_link(research_id: UUID, data: Link):
    url = data.url.strip()
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or
                parts.username is not None or parts.password is not None or parts.port == 0 or
                "\\" in url or any(ord(c) < 32 for c in url)):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Введите HTTP- или HTTPS-ссылку без логина и пароля.")
    with database() as db:
        require_research(db, research_id)
        return db.execute(
            "INSERT INTO source (research_id, kind, name, url) VALUES (%s,'web',%s,%s) "
            "RETURNING id, status", (research_id, url, url)
        ).fetchone()


@router.post("/research/{research_id}/pdf", status_code=202)
async def add_pdf(research_id: UUID, name: str, request: Request):
    if (not name.lower().endswith(".pdf") or len(name) > 255 or "\x00" in name or
            request.headers.get("content-type", "").split(";")[0] != "application/pdf"):
        raise HTTPException(415, "Выберите документ в формате PDF.")
    with database() as db:
        require_research(db, research_id)
    source_id = uuid4()
    path = uploads / str(source_id)
    size = 0
    try:
        with path.open("xb+") as output:
            async for block in request.stream():
                size += len(block)
                if size > max_pdf:
                    raise HTTPException(413, f"Размер PDF превышает {max_pdf // 1024**2} МБ.")
                output.write(block)
            output.seek(0)
            if output.read(5) != b"%PDF-":
                raise HTTPException(415, "Содержимое файла не соответствует формату PDF.")
        with database() as db:
            db.execute(
                "INSERT INTO source (id,research_id,kind,name) VALUES (%s,%s,'pdf',%s)",
                (source_id, research_id, name)
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"id": source_id, "status": "queued"}


def dispatch(queue):
    # PostgreSQL is the durable outbox. A lost Redis delivery is retried.
    with database() as db:
        rows = db.execute(
            "SELECT id, attempts FROM source WHERE status IN ('queued','processing') "
            "AND next_dispatch <= now() ORDER BY next_dispatch LIMIT 16 FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for row in rows:
            if row["attempts"] >= 3:
                db.execute("UPDATE source SET status='error', error=%s WHERE id=%s",
                           ("Обработка несколько раз прервалась. Проверьте документ.", row["id"]))
                continue
            queue.enqueue("tasks.process", str(row["id"]), job_timeout=120, ttl=180, result_ttl=0)
            db.execute("UPDATE source SET status='queued', next_dispatch=now()+interval '3 minutes' "
                       "WHERE id=%s", (row["id"],))

        dispatch_analysis(db, queue)


async def dispatch_loop(redis):
    queue = Queue("contour", connection=redis)
    while True:
        try:
            await asyncio.to_thread(dispatch, queue)
        except Exception:
            logging.exception("Failed to enqueue pending jobs")
        await asyncio.sleep(2)

@router.get("/research/{research_id}/sources/{source_id}/fragments")
def fragments(research_id: UUID, source_id: UUID, offset: int = Query(0, ge=0)):
    with database() as db:
        source = db.execute("SELECT resolved_url FROM source WHERE id=%s AND research_id=%s",
                            (source_id, research_id)).fetchone()
        if source is None:
            raise HTTPException(404, "Источник не найден.")
        items = db.execute(
            "SELECT s.ordinal, s.page, s.heading, f.start_offset, f.end_offset, "
            "substring(s.body FROM f.start_offset+1 FOR f.end_offset-f.start_offset) AS body "
            "FROM source_section s JOIN fragment f ON f.section_id=s.id WHERE s.source_id=%s "
            "ORDER BY s.ordinal, f.start_offset LIMIT 11 OFFSET %s", (source_id, offset)
        ).fetchall()
        return {"items": items[:10], "more": len(items) > 10, "url": source["resolved_url"]}
