"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Обзор" },
  { href: "/sources", label: "Источники" },
];

export default function Navigation() {
  const path = usePathname();
  return (
    <nav aria-label="Разделы исследования">
      {links.map(({ href, label }) => (
        <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
