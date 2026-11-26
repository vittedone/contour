def dispatch_analysis(db, queue):
    rows = db.execute("""
        SELECT research_id, attempts FROM analysis WHERE status IN ('queued','processing')
        AND next_dispatch <= now() ORDER BY next_dispatch LIMIT 2 FOR UPDATE SKIP LOCKED
    """).fetchall()
    for row in rows:
        rid = row["research_id"]
        if row["attempts"] >= 3:
            db.execute("UPDATE analysis SET status='error', error=%s WHERE research_id=%s",
                       ("Поиск несколько раз прерывался. Запустите его ещё раз.", rid))
            continue
        queue.enqueue("semantic.analyze", str(rid), job_timeout=1800, ttl=180, result_ttl=0)
        db.execute("UPDATE analysis SET status='queued', next_dispatch=now()+interval '3 minutes' "
                   "WHERE research_id=%s", (rid,))
