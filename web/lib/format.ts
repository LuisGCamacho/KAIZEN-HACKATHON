export function pct(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "—"
    : `${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })}%`;
}
export function signedPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })} pts`;
}
export function num(value: number | null | undefined, digits = 1): string {
  return value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("es-MX", { maximumFractionDigits: digits });
}
export function usd(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat("es-MX", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}
