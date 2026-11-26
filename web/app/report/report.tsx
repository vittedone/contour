"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, explain } from "../client";

type Citation = { section: string; source: string; name: string; page: number | null;
  ordinal: number; heading: string | null; start: number; from: number; to: number; quote: string };
type Finding = { citations: Citation[]; disputed: boolean };
type Content = { question: string; findings: Finding[]; conflicts: { reason: string; left: Citation; right: Citation }[];
  fragments: number; sources: number; gaps: string[] };
type Saved = { version: number; created_at: string; content: Content };
type Response = { versions: number[]; report: Saved | null; ready: boolean; is_demo: boolean };

function Reference({ id, item }: { id: string; item: Citation }) {
  const params = new URLSearchParams({ research: id, section: item.section, start: String(item.start),
    from: String(item.from), to: String(item.to) });
  const location = item.page ? "страница " + item.page : "раздел " + item.ordinal + (item.heading ? " · " + item.heading : "");
  return <Link href={"/evidence?" + params}>{item.name} · {location} →</Link>;
}

function Quote({ id, item }: { id: string; item: Citation }) {
  return <figure><blockquote>{item.quote}</blockquote><figcaption><Reference id={id} item={item} /></figcaption></figure>;
}

function Contents({ id, content }: { id: string; content: Content }) {
  const { findings, conflicts, gaps } = content;
  const lead = findings.find(f => !f.disputed) ?? findings[0];
  return <>
    <section className="panel">
      <p className="report-label">Исследовательский вопрос</p><h2>{content.question}</h2>
      <h3>Краткий ответ по материалам</h3>
      {lead ? <>
        <p>{lead.disputed ? "Источники расходятся. Одна из позиций приведена ниже." : "Один из выводов подборки приводится в формулировке источника."}</p>
        <Quote id={id} item={lead.citations[0]} />
        {conflicts.length > 0 && <a href="#disagreements">Сопоставить позиции источников ↓</a>}
      </> : <p>Собранных свидетельств недостаточно для ответа.</p>}
      <p className="report-label">Фрагментов в подборке — {content.fragments}. Источников — {content.sources}.</p>
    </section>
    {findings.length > 0 && <section className="panel"><h2>Тезисы и свидетельства</h2>
      <ol>{findings.map((f, index) => <li key={index}><blockquote>{f.citations[0].quote}</blockquote>
        {f.citations.map(c => <p key={c.source}><Reference id={id} item={c} /></p>)}
        {f.disputed && <a href="#disagreements">Есть расхождение ↓</a>}
      </li>)}</ol></section>}
    <section className="panel" id="disagreements"><h2>Возможные противоречия</h2>
      {conflicts.length ? conflicts.map((pair, i) => <div className="report-pair" key={i}>
        <h3>{pair.reason}</h3>
        <div className="positions"><Quote id={id} item={pair.left} /><Quote id={id} item={pair.right} /></div>
      </div>) : <p>{content.sources < 2 ? "Для сравнения нужны фрагменты из разных источников." :
        "В отобранных фрагментах не обнаружено прямых расхождений по правилам сравнения."}</p>}
    </section>
    <section className="panel"><h2>Пробелы и ограничения</h2>
      {gaps.map(gap => <p key={gap}>{gap}</p>)}
      <p>Отчёт охватывает только найденные фрагменты. Автоматическое сравнение может пропустить различия в контексте и перефразированные утверждения.</p>
    </section>
  </>;
}

export default function Report({ id, version }: { id: string; version?: string }) {
  const router = useRouter();
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const endpoint = "/" + encodeURIComponent(id) + "/reports";
  useEffect(() => {
    let active = true;
    setError("");
    setData(null);
    api<Response>(endpoint + (version ? "?version=" + encodeURIComponent(version) : ""))
      .then(value => { if (active) setData(value); }).catch(e => { if (active) setError(explain(e)); });
    return () => { active = false; };
  }, [endpoint, version, reload]);

  function openVersion(n: number) {
    router.push("/report?" + new URLSearchParams({ id, version: String(n) }));
  }
  async function generate() {
    setBusy(true);
    setError("");
    try {
      const next = await api<{ version: number }>(endpoint, { method: "POST" });
      openVersion(next.version);
      setReload(n => n + 1);
    } catch (e) { setError(explain(e)); }
    finally { setBusy(false); }
  }

  return <div className="research-report">
    <Link href={"/sources?id=" + encodeURIComponent(id)}>← К материалам исследования</Link>
    <h1>{data?.is_demo ? "Отчёт учебного исследования" : "Отчёт исследования"}</h1>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Загрузка отчёта…</p>}
    {data && <>
      <div className="report-tools">
        {data.ready && <button onClick={generate} disabled={busy}>{busy ? "Формирование…" :
          data.report ? "Обновить по результатам поиска" : "Сформировать отчёт"}</button>}
        {data.report && <label>Версия<select value={data.report.version} onChange={e => openVersion(Number(e.target.value))}>
          {data.versions.map(n => <option key={n} value={n}>{n}</option>)}
        </select></label>}
      </div>
      {!data.ready && <p>Для нового отчёта завершите поиск по вопросу на странице источников.</p>}
      {data.report ? <Contents id={id} content={data.report.content} /> :
        data.ready && <p>Отчёт будет собран из последней завершённой подборки фрагментов.</p>}
    </>}
  </div>;
}
