import type { Metadata } from "next";
import Navigation from "./navigation";
import "./style.css";

export const metadata: Metadata = {
  title: "Контур · Рабочее пространство",
  description: "Рабочее пространство исследования",
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <header>
          <div className="bar">
            <a className="brand" href="/" aria-label="Контур — обзор">
              <span className="mark" aria-hidden="true">◎</span> Контур
            </a>
            <Navigation />
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
