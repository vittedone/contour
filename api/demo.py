import json
from html import escape
from pathlib import Path

from reports import save_report
from sources import database


def install_demo():
    materials = json.loads(Path(__file__).with_name("demo_materials.json").read_text(encoding="utf-8"))
    with database() as db:
        new = db.execute("""
            INSERT INTO research (question, is_demo) VALUES (%s, true)
            ON CONFLICT (is_demo) WHERE is_demo DO NOTHING RETURNING id
        """, (materials["question"],)).fetchone()
        if not new:
            return
        research_id = new["id"]
        db.execute("INSERT INTO analysis (research_id,status) VALUES (%s,'ready')", (research_id,))
        for rank, note in enumerate(materials["sources"], 1):
            body = note["body"]
            heading = note["heading"]
            snapshot = f"<html lang='ru'><meta charset='utf-8'><h1>{escape(heading)}</h1><p>{escape(body)}</p></html>"
            source = db.execute("""
                INSERT INTO source (research_id,kind,name,status,html_snapshot)
                VALUES (%s,'web',%s,'ready',%s) RETURNING id
            """, (research_id, note["name"], snapshot.encode())).fetchone()
            section = db.execute("""
                INSERT INTO source_section (source_id,ordinal,heading,body)
                VALUES (%s,1,%s,%s) RETURNING id
            """, (source["id"], heading, body)).fetchone()
            db.execute("INSERT INTO fragment (section_id,start_offset,end_offset) VALUES (%s,0,%s)",
                       (section["id"], len(body)))
            db.execute("""
                INSERT INTO search_hit (research_id,rank,section_id,fragment_start,similarity,claim_start,claim_end)
                VALUES (%s,%s,%s,0,%s,%s,%s)
            """, (research_id, rank, section["id"], note["similarity"], note["claim_start"], note["claim_end"]))
        save_report(db, research_id)
