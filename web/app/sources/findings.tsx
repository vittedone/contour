"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, explain } from "../client";

type Hit = {
  rank: number; name: string; section_id: string; page: number | null; ordinal: number;
  heading: string | null; start_offset: number; end_offset: number;
  claim: string | null; claim_start: number | null; claim_end: number | null; body: string;
};
type Results = { status: "idle" | "queued" | "processing" | "ready" | "error"; error: string | null; hits: Hit[] };

function citation(research: string, h: Hit, claim: boolean) {
  const query = new URLSearchParams({ research, section: h.section_id, start: String(h.start_offset) });
  if (claim && h.claim_start !== null && h.claim_end !== null) {
    query.set("from", String(h.claim_start));
    query.set("to", String(h.claim_end));
  }
  const place = h.page ? "Страница " + h.page : "Раздел " + h.ordinal + (h.heading ? " · " + h.heading : "");
  return <Link href={"/evidence?" + query}>{h.name} · {place} →</Link>;
}

export default function Findings({ researchId, hasSources }: { researchId: string; hasSources: boolean }) {
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState("");
  const [posting, setPosting] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await api<Results>(`/${researchId}/analysis`);
        if (!active) return;
        setData(next);
        setError("");
        if (next.status === "processing" || next.status === "queued") timer = setTimeout(refresh, 2500);
      } catch (e) {
        if (active) { setError(explain(e)); timer = setTimeout(refresh, 5000); }
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [researchId, revision]);

  async function search() {
    setPosting(true);
    try {
      const next = await api<Pick<Results, "status">>(`/${researchId}/analysis`, { method: "POST" });
      setData(old => ({ hits: old?.hits ?? [], error: null, status: next.status }));
      setError("");
      setRevision(value => value + 1);
    } catch (e) {
      setError(explain(e));
    } finally {
      setPosting(false);
    }
  }

  const running = data?.status === "queued" || data?.status === "processing";
  const claims = data?.hits.filter(h => h.claim !== null) ?? [];
  return <section className="panel findings">
    <h2>Поиск по вопросу исследования</h2>
    <p>{hasSources ? "Найдите близкие по смыслу фрагменты и черновые тезисы в готовых источниках."
      : "Поиск станет доступен, когда будет готов первый источник."}</p>
    <button disabled={!hasSources || posting || running} onClick={search}>
      {data?.status === "ready" ? "Обновить результаты" : "Найти фрагменты и тезисы"}
    </button>
    <p role="status">{data?.status === "queued" ? "Поиск в очереди." :
      data?.status === "processing" ? "Строим векторы и подбираем свидетельства…" : ""}</p>
    {(error || data?.error) && <p role="alert">{error || data?.error}</p>}
    {data?.status === "ready" && !data.hits.length && <p>В готовых источниках не найдено достаточно близких по смыслу фрагментов.</p>}
    <p><Link className="action" href={"/report?id=" + researchId}>Отчёт исследования →</Link></p>
    {Boolean(data?.hits.length) && <>
      <h3>Черновые тезисы</h3>
      {claims.length ? <ol>{claims.map(h => <li key={h.rank}>
        <blockquote>{h.claim}</blockquote>{citation(researchId, h, true)}
      </li>)}</ol> : <p>В найденных фрагментах не удалось выделить тезис с достаточным сходством.</p>}
      <details><summary>Релевантные фрагменты ({data?.hits.length})</summary>
        <ol>{data?.hits.map(h => <li key={h.rank}>
          <p>{h.body}</p>{citation(researchId, h, false)}
        </li>)}</ol>
      </details>
    </>}
  </section>;
}
