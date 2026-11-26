from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from sources import database, require_research

router = APIRouter(prefix="/research/{research_id}")


@router.post("/analysis", status_code=202)
def start_analysis(research_id: UUID):
    with database() as db:
        require_research(db, research_id)
        if not db.execute("SELECT 1 FROM source WHERE research_id=%s AND status='ready' LIMIT 1",
                          (research_id,)).fetchone():
            raise HTTPException(409, "Сначала дождитесь готовности хотя бы одного источника.")
        db.execute("""
            INSERT INTO analysis (research_id, status) VALUES (%s, 'queued')
            ON CONFLICT (research_id) DO UPDATE SET status='queued', attempts=0,
                next_dispatch=now(), error=NULL WHERE analysis.status IN ('ready','error')
        """, (research_id,))
        return {"status": db.execute("SELECT status FROM analysis WHERE research_id=%s",
                                     (research_id,)).fetchone()["status"]}


@router.get("/analysis")
def results(research_id: UUID):
    with database() as db:
        require_research(db, research_id)
        state = db.execute("SELECT status,error FROM analysis WHERE research_id=%s",
                           (research_id,)).fetchone()
        hits = db.execute("""
            SELECT h.rank, s.name, sec.id::text AS section_id, sec.page, sec.ordinal, sec.heading,
                   f.start_offset, f.end_offset, h.claim_start, h.claim_end,
                   substring(sec.body FROM h.claim_start+1 FOR h.claim_end-h.claim_start) AS claim,
                   substring(sec.body FROM f.start_offset+1 FOR f.end_offset-f.start_offset) AS body
            FROM search_hit h JOIN fragment f ON (f.section_id,f.start_offset)=(h.section_id,h.fragment_start)
            JOIN source_section sec ON sec.id=f.section_id JOIN source s ON s.id=sec.source_id
            WHERE h.research_id=%s AND s.research_id=%s ORDER BY h.rank
        """, (research_id, research_id)).fetchall()
        return {**(state or {"status": "idle", "error": None}), "hits": hits}


@router.get("/evidence")
def evidence(research_id: UUID, section: int = Query(gt=0), start: int = Query(ge=0)):
    with database() as db:
        row = db.execute("""
            SELECT s.name, s.resolved_url, sec.ordinal, sec.page, sec.heading, f.start_offset, f.end_offset,
                   substring(sec.body FROM f.start_offset+1 FOR f.end_offset-f.start_offset) AS body
            FROM fragment f JOIN source_section sec ON sec.id=f.section_id JOIN source s ON s.id=sec.source_id
            WHERE s.research_id=%s AND f.section_id=%s AND f.start_offset=%s
        """, (research_id, section, start)).fetchone()
        if row is None:
            raise HTTPException(404, "Фрагмент в этом исследовании не найден.")
        return row
