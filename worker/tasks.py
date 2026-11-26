import logging

import psycopg
from psycopg.rows import dict_row
from rq.timeouts import JobTimeoutException

from extract import EXTRACTORS, SourceError


def fragment_ranges(text):
    start = 0
    while start < len(text):
        end = min(start + 1200, len(text))
        if end < len(text):
            boundary = max(text.rfind(" ", start + 600, end), text.rfind("\n", start + 600, end))
            if boundary >= 0:
                end = boundary + 1
        yield start, end
        start = end


def process(source_id):
    with psycopg.connect(row_factory=dict_row) as db:
        source = db.execute(
            "UPDATE source SET status='processing', attempts=attempts+1, "
            "next_dispatch=now()+interval '3 minutes' WHERE id=%s AND status='queued' "
            "RETURNING id, kind, url, attempts", (source_id,)
        ).fetchone()
    if source is None:
        return
    try:
        sections, url, snapshot = EXTRACTORS[source["kind"]](source)
        if not sections:
            if source["kind"] == "pdf":
                raise SourceError("В PDF нет извлекаемого текста. Для скана нужен PDF с текстовым слоем.")
            raise SourceError("На странице нет текста, доступного без JavaScript.")
        with psycopg.connect() as db:
            claimed = db.execute(
                "UPDATE source SET status='ready', resolved_url=%s, html_snapshot=%s "
                "WHERE id=%s AND attempts=%s AND status='processing' RETURNING id",
                (url, snapshot, source_id, source["attempts"])
            ).fetchone()
            if not claimed:
                return
            for ordinal, (page, heading, body) in enumerate(sections, start=1):
                body = body.replace("\x00", "\ufffd")
                section_id, = db.execute(
                    "INSERT INTO source_section (source_id,ordinal,page,heading,body) "
                    "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (source_id, ordinal, page, heading.replace("\x00", "") if heading else None, body)
                ).fetchone()
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO fragment (section_id,start_offset,end_offset) VALUES (%s,%s,%s)",
                        ((section_id, start, end) for start, end in fragment_ranges(body))
                    )
    except Exception as exc:
        if isinstance(exc, SourceError):
            message = str(exc)
        elif isinstance(exc, JobTimeoutException):
            message = "Источник обрабатывался слишком долго. Попробуйте документ меньшего размера."
        else:
            logging.exception("Failed to process source %s", source_id)
            message = "Не удалось обработать содержимое источника. Проверьте файл или ссылку."
        with psycopg.connect() as db:
            db.execute("UPDATE source SET status='error', error=%s "
                       "WHERE id=%s AND attempts=%s AND status='processing'",
                       (message, source_id, source["attempts"]))
