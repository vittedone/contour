import json
import logging
import os
import re

import psycopg
from psycopg.rows import dict_row

from embeddings import Encoder

FRAGMENTS = """
    FROM fragment f JOIN source_section sec ON sec.id=f.section_id
    WHERE sec.source_id=ANY(%s::uuid[])
"""
TEXT = "substring(sec.body FROM f.start_offset+1 FOR f.end_offset-f.start_offset)"


def index_fragments(db, encoder, source_ids):
    while True:
        rows = db.execute(
            f"SELECT f.section_id, f.start_offset, {TEXT} AS body " + FRAGMENTS +
            " AND f.embedding IS NULL ORDER BY f.section_id, f.start_offset LIMIT 32", (source_ids,)
        ).fetchall()
        if not rows:
            return
        vectors = encoder.encode([row["body"] for row in rows])
        with db.transaction(), db.cursor() as cursor:
            cursor.executemany("UPDATE fragment SET embedding=%s::vector WHERE section_id=%s AND start_offset=%s",
                               [(json.dumps(v.tolist()), r["section_id"], r["start_offset"])
                                for v, r in zip(vectors, rows)])


def passages(db, source_ids, vector, threshold):
    return db.execute(f"""
        WITH ranked AS (
            SELECT f.section_id, f.start_offset, f.end_offset, f.embedding <=> %s::vector AS distance
            {FRAGMENTS} AND f.embedding IS NOT NULL
            ORDER BY distance, f.section_id, f.start_offset LIMIT 12
        )
        SELECT r.*, substring(s.body FROM r.start_offset+1 FOR r.end_offset-r.start_offset) AS body,
               right(rtrim(left(s.body,r.start_offset), E' \\r\\n\\t'),1) AS preceding,
               r.end_offset=length(s.body) AS ends_section
        FROM ranked r JOIN source_section s ON s.id=r.section_id
        WHERE 1-distance >= %s ORDER BY distance, r.section_id, r.start_offset
    """, (json.dumps(vector.tolist()), source_ids, threshold)).fetchall()


def sentences(row):
    body = row["body"]
    # Keep offsets in the immutable section; discard sentences cut by chunk boundaries.
    boundaries = [0, *(m.end() for m in re.finditer(r"(?<=[.!?…])\s+", body)), len(body)]
    for left, right in zip(boundaries, boundaries[1:]):
        if left == 0 and row["preceding"] and row["preceding"] not in ".!?…":
            continue
        raw = body[left:right]
        text = raw.strip()
        if len(text.split()) < 3 or text.endswith("?"):
            continue
        if not row["ends_section"] and right == len(body) and text[-1] not in ".!…":
            continue
        start = row["start_offset"] + left + len(raw) - len(raw.lstrip())
        yield text, start, start + len(text)


def select_claims(rows, encoder, query, threshold):
    choices = [(i, text, start, end) for i, row in enumerate(rows)
               for text, start, end in sentences(row)]
    if not choices:
        return {}
    scores = encoder.encode([item[1] for item in choices]) @ query
    result, seen = {}, set()
    for i in scores.argsort()[::-1]:
        hit, text, start, end = choices[i]
        if scores[i] < threshold or len(result) == 5:
            break
        key = " ".join(text.casefold().split())
        if key not in seen and hit not in result:
            result[hit] = (start, end)
            seen.add(key)
    return result


def analyze(research_id):
    with psycopg.connect(row_factory=dict_row, autocommit=True) as db:
        run = db.execute("""
            UPDATE analysis SET status='processing', attempts=attempts+1,
                next_dispatch=now()+interval '31 minutes'
            WHERE research_id=%s AND status='queued' RETURNING attempts
        """, (research_id,)).fetchone()
        if run is None:
            return
        attempt = run["attempts"]
        try:
            ids = [r["id"] for r in db.execute(
                "SELECT id FROM source WHERE research_id=%s AND status='ready'", (research_id,))]
            question = db.execute("SELECT question FROM research WHERE id=%s", (research_id,)).fetchone()
            encoder = Encoder()
            index_fragments(db, encoder, ids)
            vector = encoder.encode([question["question"]])[0]
            threshold = float(os.getenv("MIN_SIMILARITY", "0.30"))
            rows = passages(db, ids, vector, threshold)
            claims = select_claims(rows, encoder, vector, threshold)
            with db.transaction():
                current = db.execute("UPDATE analysis SET status='ready', error=NULL WHERE research_id=%s "
                                     "AND status='processing' AND attempts=%s RETURNING research_id",
                                     (research_id, attempt)).fetchone()
                if not current:
                    return
                db.execute("DELETE FROM search_hit WHERE research_id=%s", (research_id,))
                with db.cursor() as cursor:
                    cursor.executemany("""
                        INSERT INTO search_hit (research_id,rank,section_id,fragment_start,
                                                similarity,claim_start,claim_end)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """, [(research_id, i+1, r["section_id"], r["start_offset"], 1-r["distance"],
                           *claims.get(i, (None, None))) for i, r in enumerate(rows)])
        except Exception:
            logging.exception("Ошибка семантического поиска для исследования %s", research_id)
            db.execute("UPDATE analysis SET status='error', error=%s WHERE research_id=%s "
                       "AND status='processing' AND attempts=%s",
                       ("Поиск не завершился. Проверьте журнал worker и доступность модели, затем повторите.",
                        research_id, attempt))
