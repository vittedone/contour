"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, explain, type Research } from "./client";

export default function Workspace() {
  const router = useRouter();
  const [items, setItems] = useState<Research[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    api<Research[]>("").then(setItems).catch(e => setError(explain(e)));
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const item = await api<Research>("", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      router.push("/sources?id=" + item.id);
    } catch (e) {
      setError(explain(e));
      setBusy(false);
    }
  }

  const demo = items?.find(item => item.is_demo);
  const own = items?.filter(item => !item.is_demo);
  return <>
    <h1>Рабочее пространство</h1>
    {demo && <section className="demo-study">
      <div>
        <p className="label">Демонстрационное исследование</p>
        <h2>{demo.question}</h2>
        <p>Три учебных источника дают две оценки экономии времени. Откройте отчёт и сравните, как диспетчер и пассажиры измеряли поездку.</p>
      </div>
      <div className="demo-links">
        <Link className="action" href={"/report?id=" + demo.id + "&version=1"}>Открыть демоотчёт →</Link>
        <Link href={"/sources?id=" + demo.id}>Посмотреть источники</Link>
      </div>
    </section>}
    <section className="question">
      <div className="copy">
        <h2>Новое исследование</h2>
        <form onSubmit={create}>
          <label htmlFor="question">Исследовательский вопрос</label>
          <textarea id="question" rows={2} required maxLength={2000}
            value={question} onChange={e => setQuestion(e.target.value)} />
          <button disabled={busy || !question.trim()}>Создать исследование</button>
        </form>
      </div>
      <div className="terrain" aria-hidden="true">{Array.from({ length: 15 }, (_, i) =>
        <i key={i} style={{ width: 80 + i * 30, height: 62 + i * 22 }} />)}</div>
    </section>
    {error && <p role="alert">{error}</p>}
    <section className="panel">
      <h2>Мои исследования</h2>
      {items === null && !error && <p>Загрузка…</p>}
      {own?.length === 0 && <p>Исследований пока нет. Введите вопрос выше, чтобы начать.</p>}
      <ul>{own?.map(item => <li key={item.id}>
        <Link href={"/sources?id=" + item.id}>{item.question} →</Link>
      </li>)}</ul>
    </section>
  </>;
}
