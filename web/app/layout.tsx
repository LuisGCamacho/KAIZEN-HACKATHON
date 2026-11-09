import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "KAIZEN — Agent factory", template: "%s · KAIZEN" },
  description: "Panel de observación para la fábrica de agentes KAIZEN.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
