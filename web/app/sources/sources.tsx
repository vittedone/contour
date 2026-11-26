"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, explain, type Research } from "../client";

import Findings from "./findings";
import Excerpts from "./excerpts";

const labels = { queued: "Ожидает обработки", processing: "Обрабатывается", ready: "Готов", error: "Ошибка" };
type Source = { id: string; name: string; kind: string; status: keyof typeof labels; error: string | null };

function Materials({ id }: { id: string }) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const items = await api<Source[]>(`/${id}/sources`);
        if (active) { setSources(items); setLoadError(""); }
      } catch (e) {
        if (active) setLoadError(explain(e));
      } finally {
        if (active) timer = setTimeout(refresh, 2500);
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [id, revision]);

  async function submit(event: FormEvent<HTMLFormElement>, kind: "pdf" | "links") {
    event.preventDefault();
    const form = event.currentTarget;
    const value = new FormData(form).get("source");
    setBusy(true);
    setSubmitError("");
    try {
      if (kind === "pdf" && value instanceof File) {
        await api(`/${id}/pdf?name=${encodeURIComponent(value.name)}`, {
          method: "POST", headers: { "Content-Type": "application/pdf" }, body: value,
        });
      } else {
        await api(`/${id}/links`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: value }) });
      }
      form.reset();
      setRevision(n => n + 1);
    } catch (e) {
      setSubmitError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  return <>
    <div className="entry-grid">
      <form className="panel" onSubmit={e => submit(e, "pdf")}>
        <label htmlFor="pdf">PDF-документ</label>
        <input id="pdf" name="source" type="file" accept=".pdf,application/pdf" required />
        <button disabled={busy}>Загрузить PDF</button>
      </form>
      <form className="panel" onSubmit={e => submit(e, "links")}>
        <label htmlFor="url">Веб-страница</label>
        <input id="url" name="source" type="url" placeholder="https://…" required maxLength={4096} />
        <button disabled={busy}>Добавить ссылку</button>
      </form>
    </div>
    {submitError && <p role="alert">{submitError}</p>}
    <section className="panel">
      <h2>Материалы исследования</h2>
      {loadError && <p role="alert">{loadError}</p>}
      {!sources && !loadError && <p>Загрузка…</p>}
      {sources?.length === 0 && <p>Источников пока нет. Загрузите документ или добавьте ссылку.</p>}
      <ul aria-live="polite">{sources?.map(s => <li key={s.id}>
        <div className="source-row"><strong>{s.name}</strong><span className={"state " + s.status}>{labels[s.status]}</span></div>
        {s.error && <p>{s.error}</p>}
        {s.status === "ready" && <Excerpts researchId={id} sourceId={s.id} />}
      </li>)}</ul>
    </section>
    <Findings researchId={id} hasSources={Boolean(sources?.some(s => s.status === "ready"))} />
  </>;
}

export default function Sources({ selected }: { selected?: string }) {
  const router = useRouter();
  const [items, setItems] = useState<Research[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Research[]>("").then(setItems).catch(e => setError(explain(e)));
  }, []);
  const current = selected ? items?.find(i => i.id === selected) : items?.[0];
  return <>
    <h1>Источники</h1>
    {error && <p role="alert">{error}</p>}
    {!items && !error && <p>Загрузка исследований…</p>}
    {items && items.length > 0 && <label>Исследование
      <select value={current?.id ?? ""} onChange={e => router.push("/sources?id=" + e.target.value)}>
        {!current && <option value="">Выберите исследование</option>}
        {items.map(i => <option value={i.id} key={i.id}>{i.is_demo ? "Учебный пример · " : ""}{i.question}</option>)}
      </select>
    </label>}
    {current && <Materials key={current.id} id={current.id} />}
    {items && !current && <section className="panel">
      <p>{selected ? "Исследование не найдено." : "Чтобы добавить источники, сначала создайте исследование."}</p>
      <Link className="action" href="/">Перейти к обзору</Link>
    </section>}
  </>;
}
