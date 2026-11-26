"use client";

import { useEffect, useState } from "react";
import { api, explain } from "../client";

type Fragment = { ordinal: number; page: number | null; heading: string | null;
  start_offset: number; end_offset: number; body: string };
type Batch = { items: Fragment[]; url: string | null; more: boolean };

export default function Excerpts({ researchId, sourceId }: { researchId: string; sourceId: string }) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Batch | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let active = true;
    setData(null);
    setError("");
    api<Batch>(`/${researchId}/sources/${sourceId}/fragments?offset=${offset}`)
      .then(batch => { if (active) setData(batch); })
      .catch(e => { if (active) setError(explain(e)); });
    return () => { active = false; };
  }, [researchId, sourceId, offset, open]);
  return <div className="excerpts">
    <button aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Скрыть текст" : "Открыть текст"}</button>
    {open && <>
      {error && <p role="alert">{error}</p>}
      {!error && !data && <p>Загрузка текста…</p>}
      {data?.url && <a href={data.url} target="_blank" rel="noreferrer">Исходная веб-страница ↗</a>}
      {data?.items.map(f => <figure key={f.ordinal + "-" + f.start_offset}>
        <figcaption>{f.page ? "Страница " + f.page : "Раздел " + f.ordinal + (f.heading ? " · " + f.heading : "")}
          {" · Символы "}{f.start_offset + 1}–{f.end_offset}</figcaption>
        <blockquote>{f.body}</blockquote>
      </figure>)}
      {data && <div className="paging">
        {offset > 0 && <button onClick={() => setOffset(offset - 10)}>Предыдущие фрагменты</button>}
        {data.more && <button onClick={() => setOffset(offset + 10)}>Следующие фрагменты</button>}
      </div>}
    </>}
  </div>;
}
