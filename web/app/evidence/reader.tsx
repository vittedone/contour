"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, explain } from "../client";

type Evidence = { name: string; resolved_url: string | null; page: number | null; ordinal: number;
  heading: string | null; start_offset: number; end_offset: number; body: string };

export default function Reader({ research, section, start, from, to }: {
  research: string; section: string; start: string; from?: string; to?: string;
}) {
  const [item, setItem] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setItem(null);
    setError("");
    const query = new URLSearchParams({ section, start });
    api<Evidence>(`/${encodeURIComponent(research)}/evidence?${query}`)
      .then(value => { if (active) setItem(value); }).catch(e => { if (active) setError(explain(e)); });
    return () => { active = false; };
  }, [research, section, start]);

  const chars = Array.from(item?.body ?? "");
  const left = Number(from) - Number(start);
  const right = Number(to) - Number(start);
  const highlight = Number.isInteger(left) && Number.isInteger(right) && left >= 0 && right > left && right <= chars.length;
  return <>
    <Link href={"/sources?id=" + encodeURIComponent(research)}>← К материалам исследования</Link>
    <h1>Фрагмент источника</h1>
    {error && <p role="alert">{error}</p>}
    {!error && !item && <p>Загрузка…</p>}
    {item && <article className="panel evidence">
      <h2>{item.name}</h2>
      <p>{item.page ? "Страница " + item.page : "Раздел " + item.ordinal + (item.heading ? " · " + item.heading : "")}
        {" · Символы "}{highlight ? Number(from) + 1 : item.start_offset + 1}–{highlight ? to : item.end_offset}</p>
      <blockquote>{highlight ? <>{chars.slice(0, left).join("")}<mark>{chars.slice(left, right).join("")}</mark>
        {chars.slice(right).join("")}</> : item.body}</blockquote>
      {item.resolved_url && <a href={item.resolved_url} target="_blank" rel="noreferrer">Открыть веб-страницу ↗</a>}
    </article>}
  </>;
}
