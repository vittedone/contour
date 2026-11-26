import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from psycopg.types.json import Jsonb

from sources import database, require_research

router = APIRouter(prefix="/research/{research_id}/reports")

# Compare one change in otherwise matching wording. Keep qualifiers and word order.
OPPOSITES = {frozenset(pair.split()) for pair in (
    "повышает снижает", "повышают снижают", "увеличивает уменьшает", "увеличивают уменьшают",
    "увеличивается уменьшается", "увеличиваются уменьшаются", "растёт падает", "растут падают",
    "выше ниже", "больше меньше", "увеличился уменьшился", "увеличилась уменьшилась",
)}
UNITS = {"%", "мг", "кг", "г", "м", "км", "мм", "мл", "л", "°c", "°с", "процентов", "процента"}


def words(text):
    return re.findall(r"\d+(?:[.,]\d+)?|°[cс]|[^\W\d_]+|[^\w\s]", text.casefold().rstrip(".!?… "))


def difference(a, b):
    if len(a) > len(b):
        a, b = b, a
    if len(b) == len(a) + 1:
        for i, word in enumerate(b[:-1]):
            if word == "не" and b[i+1] in {"только", "менее", "более"}:
                continue
            if word == "не" and b[:i] + b[i+1:] == a:
                return "Один источник прямо отрицает утверждение другого."
    if len(a) != len(b):
        return None
    changed = [i for i in range(len(a)) if a[i] != b[i]]
    if len(changed) != 1:
        return None
    i = changed[0]
    if frozenset((a[i], b[i])) in OPPOSITES:
        return "Источники указывают противоположные направления изменения."
    number = r"\d+(?:[.,]\d+)?"
    if (i+1 < len(a) and a[i+1] in UNITS and re.fullmatch(number, a[i])
            and re.fullmatch(number, b[i]) and float(a[i].replace(",", ".")) != float(b[i].replace(",", "."))):
        return "При одинаковой формулировке указаны разные значения. Проверьте условия измерения."
    return None


def citation(row, start, end):
    return {"source": str(row["source_id"]), "name": row["name"], "section": str(row["section_id"]),
            "ordinal": row["ordinal"], "page": row["page"], "heading": row["heading"],
            "start": row["fragment_start"], "from": start, "to": end,
            "quote": row["body"][start-row["fragment_start"]:end-row["fragment_start"]]}


def build_report(question, rows):
    evidence = []
    claims = []
    for row in rows:
        if row["claim_start"] is not None:
            claims.append(citation(row, row["claim_start"], row["claim_end"]))
        # Only complete sentences have enough context for an automatic comparison.
        for match in re.finditer(r"\S.*?(?:[.!?…](?=\s|$)|$)", row["body"], re.S):
            if match.start() == len(row["body"]) - len(row["body"].lstrip()) and row["preceding"] not in ("", ".", "!", "?", "…"):
                continue
            if match.end() == len(row["body"]) and not row["ends_section"] and match[0][-1] not in ".!…":
                continue
            if match[0].endswith("?") or len(match[0].split()) < 3:
                continue
            start = row["fragment_start"] + match.start()
            item = citation(row, start, row["fragment_start"] + match.end())
            evidence.append((words(item["quote"]), item))

    findings, conflicts, pairs = [], [], set()
    for claim in claims:
        tokens = words(claim["quote"])
        supporting = [claim]
        sources = {claim["source"]}
        disputed = False
        for other_tokens, other in evidence:
            if other["source"] == claim["source"]:
                continue
            if tokens == other_tokens and other["source"] not in sources:
                supporting.append(other)
                sources.add(other["source"])
            reason = difference(tokens, other_tokens)
            if reason:
                disputed = True
                key = tuple(sorted((tuple(tokens), tuple(other_tokens))))
                if key not in pairs:
                    conflicts.append({"reason": reason, "left": claim, "right": other})
                    pairs.add(key)
        findings.append({"citations": supporting, "disputed": disputed})

    gaps = []
    if not findings:
        gaps.append("В найденных фрагментах нет тезиса с проверяемой цитатой для ответа на вопрос.")
    elif len({r["source_id"] for r in rows}) == 1:
        gaps.append("В подборке представлен один источник. Сопоставить его выводы с другими материалами пока нельзя.")
    elif any(len(f["citations"]) == 1 for f in findings):
        gaps.append("Для части тезисов в подборке найдено только одно прямое свидетельство.")
    if conflicts:
        gaps.append("Для разрешения расхождений нужно сверить контекст, периоды и условия в исходных материалах.")
    return {"question": question, "findings": findings, "conflicts": conflicts, "gaps": gaps,
            "fragments": len(rows), "sources": len({r["source_id"] for r in rows})}


@router.post("")
def generate(research_id: UUID):
    with database() as db:
        return save_report(db, research_id)


def save_report(db, research_id):
    require_research(db, research_id)
    state = db.execute("SELECT status FROM analysis WHERE research_id=%s FOR UPDATE",
                       (research_id,)).fetchone()
    if not state or state["status"] != "ready":
        raise HTTPException(409, "Для отчёта нужен завершённый поиск по вопросу исследования.")
    question = db.execute("SELECT question FROM research WHERE id=%s", (research_id,)).fetchone()["question"]
    rows = db.execute("""
        SELECT h.section_id, h.fragment_start, h.claim_start, h.claim_end, s.id AS source_id, s.name,
            sec.ordinal, sec.page, sec.heading,
            substring(sec.body FROM f.start_offset+1 FOR f.end_offset-f.start_offset) AS body,
            right(rtrim(left(sec.body,f.start_offset), E' \\r\\n\\t'),1) AS preceding,
            f.end_offset=length(sec.body) AS ends_section
        FROM search_hit h JOIN fragment f ON (f.section_id,f.start_offset)=(h.section_id,h.fragment_start)
        JOIN source_section sec ON sec.id=f.section_id JOIN source s ON s.id=sec.source_id
        WHERE h.research_id=%s AND s.research_id=%s ORDER BY h.rank
    """, (research_id, research_id)).fetchall()
    content = build_report(question, rows)
    previous = db.execute("SELECT version, content FROM report WHERE research_id=%s ORDER BY version DESC LIMIT 1",
                          (research_id,)).fetchone()
    if previous and previous["content"] == content:
        return {"version": previous["version"]}
    version = previous["version"] + 1 if previous else 1
    db.execute("INSERT INTO report (research_id,version,content) VALUES (%s,%s,%s)",
               (research_id, version, Jsonb(content)))
    return {"version": version}


@router.get("")
def read_report(research_id: UUID, version: int | None = Query(None, ge=1)):
    with database() as db:
        require_research(db, research_id)
        versions = [r["version"] for r in db.execute(
            "SELECT version FROM report WHERE research_id=%s ORDER BY version DESC", (research_id,))]
        if version is not None and version not in versions:
            raise HTTPException(404, "Версия отчёта не найдена.")
        selected = db.execute("SELECT version,created_at,content FROM report WHERE research_id=%s AND version=%s",
                              (research_id, version or versions[0])).fetchone() if versions else None
        ready = db.execute("SELECT 1 FROM analysis WHERE research_id=%s AND status='ready'", (research_id,)).fetchone()
        demo = db.execute("SELECT is_demo FROM research WHERE id=%s", (research_id,)).fetchone()["is_demo"]
        return {"versions": versions, "report": selected, "ready": bool(ready), "is_demo": demo}
