export function Sparkline({ values, label }: { values: number[]; label: string }) {
  if (values.length === 0) return <span className="muted-value">—</span>;
  const width = 120;
  const height = 32;
  const peak = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : 2 + index * (width - 4) / (values.length - 1);
    const y = height - 3 - value / peak * (height - 6);
    return `${x},${y}`;
  }).join(" ");
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
    <polyline points={points} /><circle cx={points.split(" ").at(-1)?.split(",")[0]} cy={points.split(" ").at(-1)?.split(",")[1]} r="3" />
  </svg>;
}
