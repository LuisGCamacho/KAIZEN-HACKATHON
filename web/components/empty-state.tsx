export function EmptyState({ title, description, source, note, command }: {
  title: string; description: string; source: string; note: string; command?: string;
}) {
  return <section className="empty-card" aria-labelledby="empty-title">
    <div className="empty-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5h16" /><path d="M6.5 16.5v-3h4v-3h4v-3h4v-3" /><path d="M15.5 4.5h3v3" />
    </svg></div>
    <div className="empty-copy"><p className="empty-kicker">Sin datos de corrida</p><h2 className="empty-title" id="empty-title">{title}</h2>
      <p className="empty-description">{description}</p>
      <div className="source-box"><span className="source-label">Fuente de datos</span><code className="source-path">{source}</code></div>
      {command && <div className="source-box"><span className="source-label">Comando de evaluación</span><code className="source-path">{command}</code></div>}
      <p className="page-footnote">{note}</p>
    </div>
  </section>;
}
