import type { ReactNode } from "react";
import Link from "next/link";
import { RunButton, SidebarBudget } from "./sidebar-status";

const navigation = [
  { href: "/", label: "Evolución", icon: "chart" },
  { href: "/live", label: "En vivo", icon: "pulse" },
  { href: "/autopsia", label: "Autopsia", icon: "cluster" },
  { href: "/herramientas", label: "Herramientas", icon: "code" },
  { href: "/linaje", label: "Linaje", icon: "branch" },
  { href: "/trazas", label: "Trazas", icon: "trace" },
] as const;
type IconName = (typeof navigation)[number]["icon"];

function Icon({ name }: { name: IconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, viewBox: "0 0 20 20", "aria-hidden": true as const };
  const paths: Record<IconName, ReactNode> = {
    chart: <><path d="M3 16.5h14" /><path d="M4.5 13.5 8 10l3 2 5-6" /><path d="M13.5 6H16v2.5" /></>,
    pulse: <><circle cx="10" cy="10" r="8" /><path d="M2.5 10h3l2-5 4 10 2-5h4" /></>,
    cluster: <><circle cx="10" cy="4" r="2" /><circle cx="5" cy="15" r="2" /><circle cx="15" cy="15" r="2" /><path d="M9 6 6 13m5-7 3 7M7 15h6" /></>,
    code: <><path d="m7 5-5 5 5 5M13 5l5 5-5 5M11.5 3l-3 14" /></>,
    branch: <><circle cx="6" cy="4" r="2" /><circle cx="14" cy="16" r="2" /><circle cx="14" cy="5" r="2" /><path d="M6 6v7a3 3 0 0 0 3 3h3M8 5h4" /></>,
    trace: <><path d="M4 3h9l3 3v11H4z" /><path d="M12 3v4h4M7 10h6M7 13h6" /></>,
  };
  return <svg className="nav-icon" {...common}>{paths[name]}</svg>;
}
function BrandMark() {
  return <svg className="brand-mark" viewBox="0 0 24 24" role="img" aria-label="KAIZEN">
    <rect x="1" y="1" width="22" height="22" rx="6" fill="var(--ink)" />
    <path d="M5.5 17.5h4v-4h4v-4h4v-4" fill="none" stroke="var(--bg)" strokeWidth="2" strokeLinecap="square" />
  </svg>;
}
export function AppShell({ active, title, description, section, children }: {
  active: string; title: string; description: string; section: string; children: ReactNode;
}) {
  return <div className="app-frame">
    <aside className="sidebar" aria-label="Navegación principal">
      <Link className="brand" href="/" aria-label="KAIZEN, ir a Evolución">
        <BrandMark /><span className="brand-name">KAIZEN</span><span className="brand-descriptor">Agent factory</span>
      </Link>
      <RunButton />
      <p className="sidebar-caption">Vistas</p>
      <nav className="primary-nav" aria-label="Vistas">
        {navigation.map(item => <Link className="nav-link" href={item.href} key={item.href} aria-current={active === item.href ? "page" : undefined}>
          <Icon name={item.icon} /><span>{item.label}</span>
        </Link>)}
      </nav>
      <div className="sidebar-spacer" />
      <SidebarBudget />
      <p className="sidebar-footnote">El consumo y los resultados aparecerán con datos exportados por el backend.</p>
    </aside>
    <main className="main-area"><div className="page-content">
      <header className="page-header"><div>
        <p className="eyebrow">{section}</p><h1 className="page-title">{title}</h1><p className="page-description">{description}</p>
      </div></header>
      {children}
    </div></main>
  </div>;
}
